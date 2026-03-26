import os
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()

DEFAULT_FUELIX_BASE_URL = "https://api.fuelix.ai/v1"
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "expired", "incomplete"}

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
        raise RuntimeError(f"Fuel IX error ({response.status_code}): {detail}")

    return payload


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


def _poll_terminal_run(
    thread_id: str,
    run_id: str,
    *,
    timeout_seconds: int = 240,
    poll_interval_seconds: float = 1.5,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    while (time.perf_counter() - started_at) < timeout_seconds:
        payload = _request_fuelix("GET", f"/threads/{thread_id}/runs/{run_id}")
        status = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(status, str) and status in TERMINAL_RUN_STATES:
            return payload
        time.sleep(poll_interval_seconds)
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


def generate_fuelix_answer(
    user_query: str,
    user_type: Optional[str],
) -> Dict[str, Any]:
    started = time.perf_counter()
    assistant_id = resolve_assistant_id(user_type)

    run_payload = _request_fuelix(
        "POST",
        "/threads/runs",
        json_payload={
            "assistant_id": assistant_id,
            "thread": {"messages": [{"role": "user", "content": user_query}]},
        },
    )

    run_id = run_payload.get("id") if isinstance(run_payload, dict) else None
    thread_id = run_payload.get("thread_id") if isinstance(run_payload, dict) else None
    if not isinstance(run_id, str) or not isinstance(thread_id, str):
        raise RuntimeError("Fuel IX run response did not include id/thread_id.")

    run_timeout_seconds = int(os.getenv("FUELIX_RUN_TIMEOUT_SECONDS", "240"))
    final_run = _poll_terminal_run(thread_id, run_id, timeout_seconds=run_timeout_seconds)
    run_status = final_run.get("status") if isinstance(final_run, dict) else None

    messages_payload = _request_fuelix(
        "GET",
        f"/threads/{thread_id}/messages",
        params={"limit": 30, "order": "desc"},
    )
    answer = _extract_assistant_text(messages_payload)
    if not answer:
        raise RuntimeError("Fuel IX did not return assistant text in thread messages.")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "answer": answer,
        "elapsed_ms": elapsed_ms,
        "assistant_id": assistant_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "run_status": run_status,
    }
