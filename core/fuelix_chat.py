import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from core.audience import is_community_audience, scrub_clinician_resources
from core.prompts import build_fuelix_user_prompt


load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_FUELIX_BASE_URL = "https://api.fuelix.ai/v1"
DEFAULT_REASONING_EFFORT = "low"
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "expired", "incomplete"}
# Terminal, but not success. A run can land here and still return an empty message list, which
# is how the "no assistant text" failure presents.
FAILED_RUN_STATES = TERMINAL_RUN_STATES - {"completed"}

# Reading the thread straight after the run goes terminal occasionally comes back with no
# assistant message yet. Re-reading is nearly free, so try that before concluding the whole run
# produced nothing.
MESSAGE_READ_ATTEMPTS = 3
MESSAGE_READ_BACKOFF_SECONDS = 1.0

# One question is allowed a second run when the first produces no text at all. Measured at
# roughly 1 in 79 runs; the same question then succeeded immediately, so the failure is
# transient and a retry is the difference between an answer and a 500.
MAX_ANSWER_ATTEMPTS = 2
# Total wall-clock ceiling for all attempts. Vercel kills the function at 300s (see
# vercel.json), so a naive retry of a 240s run would be cut off mid-flight and cost the user
# more than the failure it was meant to fix.
ANSWER_BUDGET_SECONDS = int(os.getenv("FUELIX_ANSWER_BUDGET_SECONDS", "270"))
# Do not start a retry that cannot plausibly finish; observed runs take 10-65s.
MIN_SECONDS_TO_START_RETRY = 70
# Fuel IX enforces a per-minute request quota, so polling has to stay modest even though a
# faster first poll is what makes short runs feel quick.
RATE_LIMIT_BACKOFF_SECONDS = 10.0
FUELIX_CITATION_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[*_]{1,3})?\s*(?:<<\s*)?copilot(?:\s*>>)?\s+knowledge\s+base\s+citations\s*(?:[*_]{1,3})?\s*:?\s*$",
    re.IGNORECASE,
)
FUELIX_CITATION_ENTRY_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[\d+\]\s+.+$")
FUELIX_INLINE_CITATION_RE = re.compile(
    r"[^\S\n]*(?:[*_]{1,3})?[^\S\n]*(?:<<[^\S\n]*)?copilot(?:[^\S\n]*>>)?[^\S\n]+knowledge[^\S\n]+base[^\S\n]+citations[^\S\n]*(?:[*_]{1,3})?[^\S\n]*:?[^\S\n]*(?:[-*+][^\S\n]*)?(?:\[\d+\][^\S\n]+[^;\n]+(?:;[^\S\n]*)?)*",
    re.IGNORECASE,
)

CANONICAL_USER_TYPES = {
    "patient": "patient",
    "healthcare professional": "Healthcare Professional",
    "doctor": "Healthcare Professional",
    "parent or caregiver": "Parent or Caregiver",
    "parent": "Parent or Caregiver",
    "caregiver": "Parent or Caregiver",
    "youth": "Youth",
    "teacher": "Teacher",
    "coach": "Coach",
}

DEFAULT_ASSISTANT_NAME_BY_USER_TYPE = {
    "patient": "ConcussCare Patient",
    "Healthcare Professional": "ConcussCare Healthcare Professional",
    "Parent or Caregiver": "ConcussCare Parent or Caregiver",
    "Youth": "ConcussCare Youth",
    "Teacher": "ConcussCare Teacher",
    "Coach": "ConcussCare Coach",
}

ASSISTANT_ENV_BY_USER_TYPE = {
    "patient": "FUELIX_ASSISTANT_ID_PATIENT",
    "Healthcare Professional": "FUELIX_ASSISTANT_ID_HEALTHCARE_PROFESSIONAL",
    "Parent or Caregiver": "FUELIX_ASSISTANT_ID_PARENT_OR_CAREGIVER",
    "Youth": "FUELIX_ASSISTANT_ID_YOUTH",
    "Teacher": "FUELIX_ASSISTANT_ID_TEACHER",
    "Coach": "FUELIX_ASSISTANT_ID_COACH",
}


def normalize_user_type(user_type: Optional[str]) -> str:
    key = (user_type or "patient").strip().lower()
    return CANONICAL_USER_TYPES.get(key, "patient")


def _get_fuelix_api_key() -> str:
    api_key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Fuel IX API key is missing. Set FUELIX_API_KEY in your environment.")
    return api_key


def _get_fuelix_base_url() -> str:
    return (os.getenv("FUELIX_API_BASE_URL") or DEFAULT_FUELIX_BASE_URL).rstrip("/")


def _get_fuelix_product_id() -> Optional[str]:
    value = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    return value or None


class FuelIXHTTPError(RuntimeError):
    """A non-2xx response from Fuel IX.

    Subclasses RuntimeError so existing ``except Exception`` / ``except RuntimeError``
    handlers keep working, while callers that care can branch on ``status_code``.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _request_fuelix(
    method: str,
    endpoint_path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 90,
) -> Any:
    url = f"{_get_fuelix_base_url()}{endpoint_path}"
    headers: Dict[str, str] = {"Authorization": f"Bearer {_get_fuelix_api_key()}"}
    product_id = _get_fuelix_product_id()
    if product_id:
        headers["product-id"] = product_id
    if json_payload is not None:
        headers["Content-Type"] = "application/json"

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Fuel IX request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}

    if response.status_code >= 400:
        detail: Any = payload
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message") or payload.get("detail") or payload
        raise FuelIXHTTPError(
            f"Fuel IX error ({response.status_code}): {detail}",
            status_code=response.status_code,
        )

    return payload


def _extract_chat_completion_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            return "".join(parts).strip()
    text = first.get("text")
    return text.strip() if isinstance(text, str) else ""


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _extract_assistant_text(messages_payload: Any) -> str:
    for item in _extract_items(messages_payload):
        if item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text_obj = block.get("text")
            if not isinstance(text_obj, dict):
                continue
            value = text_obj.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _strip_fuelix_citation_blocks(answer: str) -> str:
    lines = answer.splitlines()
    cleaned: List[str] = []
    index = 0

    while index < len(lines):
        if not FUELIX_CITATION_HEADING_RE.match(lines[index]):
            cleaned.append(lines[index])
            index += 1
            continue

        index += 1
        while index < len(lines):
            line = lines[index]
            if not line.strip() or FUELIX_CITATION_ENTRY_RE.match(line):
                index += 1
                continue
            break

        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        if index < len(lines) and cleaned and lines[index].strip():
            cleaned.append("")

    cleaned_text = "\n".join(cleaned)
    cleaned_text = FUELIX_INLINE_CITATION_RE.sub("", cleaned_text)
    cleaned_text = "\n".join(
        line
        for line in cleaned_text.splitlines()
        if not FUELIX_CITATION_ENTRY_RE.match(line) and not re.match(r"^\s*[-*+]\s*$", line)
    )
    cleaned_text = re.sub(r"[ \t]+\n", "\n", cleaned_text)
    return re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()


def _poll_terminal_run(
    thread_id: str,
    run_id: str,
    *,
    timeout_seconds: int = 240,
    initial_poll_seconds: float = 0.5,
    max_poll_seconds: float = 1.5,
) -> Dict[str, Any]:
    """Poll until the run reaches a terminal state.

    Backs off from ``initial_poll_seconds`` to ``max_poll_seconds`` rather than sleeping a
    flat 1.5s: short runs finish well under a second, and a flat interval spent up to that
    long waiting after the answer was already ready.

    A 429 here is NOT fatal. The run keeps executing on Fuel IX regardless of whether we
    manage to poll it, so being briefly rate-limited means "ask again later", not "the
    request failed" — previously it aborted an answer that was already being generated.
    """
    started_at = time.perf_counter()
    interval = initial_poll_seconds
    while (time.perf_counter() - started_at) < timeout_seconds:
        try:
            payload = _request_fuelix("GET", f"/threads/{thread_id}/runs/{run_id}")
        except FuelIXHTTPError as exc:
            if exc.status_code != 429:
                raise
            # Quota window is per-minute; wait out a chunk of it rather than hammering.
            time.sleep(max(interval, RATE_LIMIT_BACKOFF_SECONDS))
            interval = max_poll_seconds
            continue

        status = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(status, str) and status in TERMINAL_RUN_STATES:
            return payload
        time.sleep(interval)
        interval = min(interval * 1.6, max_poll_seconds)
    raise RuntimeError("Fuel IX run polling timed out.")


def resolve_assistant_id(user_type: Optional[str]) -> str:
    normalized = normalize_user_type(user_type)

    env_for_role = ASSISTANT_ENV_BY_USER_TYPE.get(normalized)
    if env_for_role:
        value = os.getenv(env_for_role, "").strip()
        if value:
            return value

    generic = os.getenv("FUELIX_ASSISTANT_ID", "").strip()
    if generic:
        return generic

    list_payload = _request_fuelix("GET", "/assistants", params={"limit": 100, "order": "desc"})
    assistants = _extract_items(list_payload)
    if not assistants:
        raise RuntimeError("No Fuel IX assistants were found.")

    target_name = DEFAULT_ASSISTANT_NAME_BY_USER_TYPE.get(normalized)
    if target_name:
        for item in assistants:
            name = item.get("name")
            assistant_id = item.get("id")
            if isinstance(name, str) and isinstance(assistant_id, str) and name.strip() == target_name:
                return assistant_id

    for item in assistants:
        assistant_id = item.get("id")
        if isinstance(assistant_id, str) and assistant_id.strip():
            return assistant_id

    raise RuntimeError("Unable to resolve a valid Fuel IX assistant id.")


def fuelix_chat_completion(
    messages: List[Dict[str, Any]],
    *,
    model: str,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 90,
) -> str:
    """Run a single stateless chat completion through Fuel IX's OpenAI-compatible API.

    Unlike ``generate_fuelix_answer``, this does not create an assistant/thread/run
    and does no RAG/citation handling. It is meant for lightweight auxiliary calls
    such as follow-up question generation and translation.
    """
    json_payload: Dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        json_payload["temperature"] = temperature
    if reasoning_effort:
        json_payload["reasoning_effort"] = reasoning_effort
    if response_format is not None:
        json_payload["response_format"] = response_format

    payload = _request_fuelix(
        "POST",
        "/chat/completions",
        json_payload=json_payload,
        timeout_seconds=timeout_seconds,
    )

    text = _extract_chat_completion_text(payload)
    if not text:
        raise RuntimeError("Fuel IX chat completion did not include message content.")
    return text


def _read_assistant_text(thread_id: str) -> str:
    """Read the assistant's reply, re-reading briefly when the thread looks empty.

    A run can reach a terminal state a moment before its message is readable. Re-reading costs
    one cheap GET, so exhaust that before concluding the run produced nothing.
    """
    for attempt in range(MESSAGE_READ_ATTEMPTS):
        messages_payload = _request_fuelix(
            "GET",
            f"/threads/{thread_id}/messages",
            params={"limit": 30, "order": "desc"},
        )
        answer = _extract_assistant_text(messages_payload)
        if answer:
            return answer
        if attempt < MESSAGE_READ_ATTEMPTS - 1:
            time.sleep(MESSAGE_READ_BACKOFF_SECONDS * (attempt + 1))
    return ""


def _attempt_fuelix_answer(
    assistant_id: str, user_prompt: str, *, timeout_seconds: int
) -> Dict[str, Any]:
    """One create-run / poll / read cycle. Returns an empty ``answer`` rather than raising."""
    run_payload = _request_fuelix(
        "POST",
        "/threads/runs",
        json_payload={
            "assistant_id": assistant_id,
            "thread": {"messages": [{"role": "user", "content": user_prompt}]},
            "reasoning": {"effort": DEFAULT_REASONING_EFFORT},
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
        },
    )

    run_id = run_payload.get("id") if isinstance(run_payload, dict) else None
    thread_id = run_payload.get("thread_id") if isinstance(run_payload, dict) else None
    if not isinstance(run_id, str) or not isinstance(thread_id, str):
        raise RuntimeError("Fuel IX run response did not include id/thread_id.")

    final_run = _poll_terminal_run(thread_id, run_id, timeout_seconds=timeout_seconds)
    run_status = final_run.get("status") if isinstance(final_run, dict) else None

    # A run that ended in a failure state has no text to wait for.
    answer = "" if run_status in FAILED_RUN_STATES else _read_assistant_text(thread_id)
    return {"answer": answer, "thread_id": thread_id, "run_id": run_id, "run_status": run_status}


def generate_fuelix_answer(
    user_query: str,
    user_type: Optional[str],
    lang: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Run one question through the assistant.

    ``history`` is the conversation BEFORE ``user_query``; it is folded into the seeded user
    message so follow-ups like "and for children?" resolve. Each call still creates a fresh
    thread — no thread reuse across turns.

    A run that comes back with no assistant text is retried once, within a wall-clock budget.
    """
    started = time.perf_counter()
    normalized_user_type = normalize_user_type(user_type)
    assistant_id = resolve_assistant_id(normalized_user_type)
    user_prompt = build_fuelix_user_prompt(user_query, normalized_user_type, lang, history)

    run_timeout_seconds = int(os.getenv("FUELIX_RUN_TIMEOUT_SECONDS", "240"))

    attempt = 0
    result: Dict[str, Any] = {}
    while True:
        attempt += 1
        remaining = ANSWER_BUDGET_SECONDS - (time.perf_counter() - started)
        result = _attempt_fuelix_answer(
            assistant_id,
            user_prompt,
            timeout_seconds=max(1, int(min(run_timeout_seconds, remaining))),
        )
        if result["answer"]:
            break

        remaining_after = ANSWER_BUDGET_SECONDS - (time.perf_counter() - started)
        can_retry = (
            attempt < MAX_ANSWER_ATTEMPTS and remaining_after >= MIN_SECONDS_TO_START_RETRY
        )
        logger.warning(
            "Fuel IX returned no assistant text for a %s question (run %s, status %s, "
            "attempt %d/%d, %.0fs of budget left). %s",
            normalized_user_type, result["run_id"], result["run_status"],
            attempt, MAX_ANSWER_ATTEMPTS, max(0.0, remaining_after),
            "Retrying." if can_retry else "Giving up.",
        )
        if not can_retry:
            # Name the run status: the old message said only "did not return assistant text",
            # which gave a reader nothing to diagnose with.
            raise RuntimeError(
                "Fuel IX did not return assistant text after %d attempt(s) "
                "(last run status: %s)." % (attempt, result["run_status"])
            )

    thread_id = result["thread_id"]
    run_id = result["run_id"]
    run_status = result["run_status"]
    answer = _strip_fuelix_citation_blocks(result["answer"])

    # Rule 3's backstop. The community assistants are told not to name clinician tools, but
    # they read a corpus that lists SCAT6/SCOAT6/PECARN/CATCH2 under the recommendations a
    # parent or coach asks about most, so some get through. Removals are logged rather than
    # swallowed: the count is how we tell whether the prompt is holding.
    scrubbed_resources: List[str] = []
    if is_community_audience(normalized_user_type):
        answer, scrubbed_resources = scrub_clinician_resources(answer)
        if scrubbed_resources:
            logger.info(
                "Scrubbed %d clinician-only resource(s) from a %s answer: %s",
                len(scrubbed_resources),
                normalized_user_type,
                " | ".join(item[:120] for item in scrubbed_resources),
            )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "answer": answer,
        "elapsed_ms": elapsed_ms,
        "assistant_id": assistant_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "run_status": run_status,
        "scrubbed_resources": scrubbed_resources,
        # >1 means the first run came back empty and was retried. Worth surfacing: if this
        # starts appearing often, the upstream problem is no longer occasional.
        "attempts": attempt,
    }
