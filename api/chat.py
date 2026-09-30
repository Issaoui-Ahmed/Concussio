from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import admin_access
from core import research_log
from core.fuelix_chat import generate_fuelix_answer, normalize_user_type
from core.routing import (
    CANNED_INTENTS,
    canned_reply,
    detect_simple_intent,
    generate_smalltalk_reply,
)

app = FastAPI()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    user_type: Optional[str] = "patient" # Default to patient
    lang: Optional[Literal["en", "fr"]] = None
    # The conversation's random research-log ID (core/research_log.py). The browser makes one
    # per chat, so every exchange of a conversation is filed under the same ID.
    session_id: Optional[str] = None
    # False keeps this exchange out of the research log. Sent by the /admin batch tool, and only
    # honoured with the admin cookie -- see _kept_out_of_log.
    log: bool = True

def _prior_turns(history: List[Dict[str, str]], user_text: str) -> List[Dict[str, str]]:
    """Everything before the current message.

    The frontend appends the message being sent to the end of `history`, so it has to be
    dropped before the rest is used as context.
    """
    if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
        return history[:-1]
    return history


def _answer(request: ChatRequest) -> Dict[str, Any]:
    user_text = request.message
    history: List[Dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in request.history
    ]
    user_type = request.user_type or "patient"
    # None means "let the model detect it" — the admin batch tool never sends a lang.
    lang = request.lang

    prior_turns = _prior_turns(history, user_text)

    # Greetings, thanks, and "what can you do?" don't need the assistant run that
    # carries the whole recommendations corpus and does RAG. Answer them here.
    # Anything the router is unsure about returns None and falls through.
    intent = detect_simple_intent(user_text, prior_turns)
    if intent in CANNED_INTENTS:
        return {
            "answer": canned_reply(intent, lang, user_type),
            "mode": "fuelix",
            "routed": intent,
        }
    if intent == "smalltalk":
        smalltalk_answer = generate_smalltalk_reply(user_text, user_type, lang)
        if smalltalk_answer:
            return {
                "answer": smalltalk_answer,
                "mode": "fuelix",
                "routed": "smalltalk",
            }

    fuelix_raw = generate_fuelix_answer(user_text, user_type, lang, prior_turns)
    fuelix_result = {
        "ok": True,
        "answer": fuelix_raw.get("answer", ""),
        "elapsed_ms": fuelix_raw.get("elapsed_ms"),
        "assistant_id": fuelix_raw.get("assistant_id"),
        "thread_id": fuelix_raw.get("thread_id"),
        "run_id": fuelix_raw.get("run_id"),
        "run_status": fuelix_raw.get("run_status"),
        # What the Rule 3 backstop removed on this turn, if anything. Not rendered by the
        # chat UI; it is here so /admin/batch runs show whether the community prompts are
        # holding on their own or leaning on the scrub.
        "scrubbed_resources": fuelix_raw.get("scrubbed_resources") or [],
    }
    return {
        "answer": fuelix_result["answer"],
        "mode": "fuelix",
        "answers": {"fuelix": fuelix_result},
    }


def _kept_out_of_log(request: ChatRequest, http_request: Request) -> bool:
    """The batch tool's test questions are not participant data; a participant's questions are.
    So opting out takes the admin cookie, and nobody drops their own exchanges from the study by
    editing one field of a request."""
    return not request.log and admin_access.is_admin(
        http_request.cookies.get(admin_access.COOKIE_NAME)
    )


def _log(
    request: ChatRequest, http_request: Request, received_at: datetime, answer: Optional[str]
) -> None:
    if _kept_out_of_log(request, http_request):
        return
    research_log.log_exchange(
        session_id=request.session_id,
        received_at=received_at,
        # The canonical type the answer was tailored to, not whatever string the request held.
        user_type=normalize_user_type(request.user_type),
        question=request.message,
        answer=answer,
    )


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest, http_request: Request):
    received_at = datetime.now(timezone.utc)
    try:
        response = _answer(request)
    except Exception as e:
        # A question that got no answer is still an exchange the study sees.
        _log(request, http_request, received_at, answer=None)
        raise HTTPException(status_code=500, detail=str(e))
    _log(request, http_request, received_at, answer=response["answer"])
    return response
