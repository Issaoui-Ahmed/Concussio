from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import time
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.generator import generate_answer
from core.fuelix_chat import generate_fuelix_answer
from core.prompts import build_generator_prompt

app = FastAPI()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    user_type: Optional[str] = "patient" # Default to patient
    compare_providers: Optional[bool] = False
    provider_mode: Optional[str] = None

def format_history(messages: List[Dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    return "\n".join(lines).strip()


def _build_openai_prompt(
    user_text: str,
    history: List[Dict[str, str]],
    user_type: str,
    *,
    force_single_turn: bool = False,
) -> str:
    started = (len(history) > 1) and not force_single_turn
    if not started:
        return build_generator_prompt(user_text, user_type)

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


def _provider_error_payload(exc: Exception) -> Dict[str, Any]:
    return {
        "ok": False,
        "answer": "",
        "elapsed_ms": None,
        "error": str(exc),
    }


def _resolve_provider_mode(request: ChatRequest) -> str:
    raw = (request.provider_mode or "").strip().lower()
    if request.compare_providers:
        return "both"
    if raw in {"openai", "fuelix", "both"}:
        return raw
    return "openai"


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    try:
        user_text = request.message
        history = [{"role": m.role, "content": m.content} for m in request.history]
        user_type = request.user_type or "patient"
        provider_mode = _resolve_provider_mode(request)

        if provider_mode == "both":
            # Compare mode intentionally sends the current user query only to both providers
            # so speed/quality can be evaluated on the same single-turn prompt.
            openai_prompt = _build_openai_prompt(
                user_text=user_text,
                history=[],
                user_type=user_type,
                force_single_turn=True,
            )

            with ThreadPoolExecutor(max_workers=2) as executor:
                openai_future = executor.submit(_generate_openai_answer_with_meta, openai_prompt)
                fuelix_future = executor.submit(generate_fuelix_answer, user_text, user_type)

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

        if provider_mode == "fuelix":
            fuelix_raw = generate_fuelix_answer(user_text, user_type)
            fuelix_result = {
                "ok": True,
                "answer": fuelix_raw.get("answer", ""),
                "elapsed_ms": fuelix_raw.get("elapsed_ms"),
                "assistant_id": fuelix_raw.get("assistant_id"),
                "thread_id": fuelix_raw.get("thread_id"),
                "run_id": fuelix_raw.get("run_id"),
                "run_status": fuelix_raw.get("run_status"),
            }
            return {
                "answer": fuelix_result["answer"],
                "mode": "fuelix",
                "answers": {"fuelix": fuelix_result},
            }

        prompt = _build_openai_prompt(
            user_text=user_text,
            history=history,
            user_type=user_type,
            force_single_turn=False,
        )
        answer = generate_answer(prompt, tools=True, papers=True)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
