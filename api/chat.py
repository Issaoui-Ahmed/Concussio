from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Literal, Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fuelix_chat import generate_fuelix_answer
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

def _prior_turns(history: List[Dict[str, str]], user_text: str) -> List[Dict[str, str]]:
    """Everything before the current message.

    The frontend appends the message being sent to the end of `history`, so it has to be
    dropped before the rest is used as context.
    """
    if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
        return history[:-1]
    return history


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    try:
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
        }
        return {
            "answer": fuelix_result["answer"],
            "mode": "fuelix",
            "answers": {"fuelix": fuelix_result},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
