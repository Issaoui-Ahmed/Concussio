"""ARCHIVED 2026-07-31 — extracted from ``api/chat.py``.

Everything the /api/chat endpoint carried to support OpenAI and the OpenAI-vs-Fuel IX compare
mode. Retired when the app moved to Fuel IX only.

Two behaviour notes on what changed in the live endpoint:

* ``_resolve_provider_mode`` used to default to ``"openai"``. Callers that send no
  ``provider_mode`` — ``components/BatchInterface.tsx`` was the only one — therefore ran on
  OpenAI. They now run on Fuel IX. ``ChatRequest`` no longer accepts ``compare_providers`` or
  ``provider_mode`` at all.
* The ``"both"`` branch deliberately dropped conversation history and sent the current user
  query alone to each provider, so speed and quality were judged on the same single-turn
  prompt. That is why it passed ``history=[]`` and ``force_single_turn=True``.

Not imported by anything. Depends on ``core.generator.generate_answer`` (see
``generator_openai.py`` in this folder) and on ``build_generator_prompt``, both of which were
removed from the live tree. See ../README.md.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from core.generator import generate_answer  # archived: see generator_openai.py
from core.prompts import build_generator_prompt, format_history  # build_generator_prompt removed


def _build_openai_prompt(
    user_text: str,
    history: List[Dict[str, str]],
    user_type: str,
    *,
    force_single_turn: bool = False,
    lang: Optional[str] = None,
) -> str:
    started = (len(history) > 1) and not force_single_turn
    if not started:
        return build_generator_prompt(user_text, user_type, lang)

    transcript = format_history(history)
    return (
        "You are a helpful assistant in an ongoing conversation.\n"
        "Use the conversation history for context and continuity.\n\n"
        f"Conversation history:\n{transcript}\n\n"
        f"User: {user_text}\n"
        "Assistant:"
    )


def _generate_openai_answer_with_meta(prompt: str) -> Dict[str, Any]:
    started = time.perf_counter()
    answer = generate_answer(prompt, tools=True, papers=True)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {"answer": answer, "elapsed_ms": elapsed_ms}


def _resolve_provider_mode(request) -> str:
    raw = (request.provider_mode or "").strip().lower()
    if request.compare_providers:
        return "both"
    if raw in {"openai", "fuelix", "both"}:
        return raw
    return "openai"


def compare_branch(user_text, user_type, lang, generate_fuelix_answer, _provider_error_payload):
    """The ``provider_mode == "both"`` branch of the old chat_endpoint."""
    # Compare mode intentionally sends the current user query only to both providers
    # so speed/quality can be evaluated on the same single-turn prompt.
    openai_prompt = _build_openai_prompt(
        user_text=user_text,
        history=[],
        user_type=user_type,
        force_single_turn=True,
        lang=lang,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        openai_future = executor.submit(_generate_openai_answer_with_meta, openai_prompt)
        fuelix_future = executor.submit(generate_fuelix_answer, user_text, user_type, lang)

        try:
            openai_raw = openai_future.result()
            openai_result: Dict[str, Any] = {
                "ok": True,
                "answer": openai_raw.get("answer", ""),
                "elapsed_ms": openai_raw.get("elapsed_ms"),
            }
        except Exception as exc:
            openai_result = _provider_error_payload(exc)

        try:
            fuelix_raw = fuelix_future.result()
            fuelix_result = {
                "ok": True,
                "answer": fuelix_raw.get("answer", ""),
                "elapsed_ms": fuelix_raw.get("elapsed_ms"),
                "assistant_id": fuelix_raw.get("assistant_id"),
                "thread_id": fuelix_raw.get("thread_id"),
                "run_id": fuelix_raw.get("run_id"),
                "run_status": fuelix_raw.get("run_status"),
            }
        except Exception as exc:
            fuelix_result = _provider_error_payload(exc)

    if not openai_result["ok"] and not fuelix_result["ok"]:
        raise RuntimeError(
            f"Both providers failed. OpenAI: {openai_result['error']} | Fuel IX: {fuelix_result['error']}"
        )

    primary_answer = openai_result["answer"] if openai_result["ok"] else fuelix_result["answer"]
    return {
        "answer": primary_answer,
        "mode": "both",
        "answers": {
            "openai": openai_result,
            "fuelix": fuelix_result,
        },
    }
