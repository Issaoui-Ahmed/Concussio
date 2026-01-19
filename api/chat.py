from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.generator import generate_answer
from core.prompts import build_generator_prompt

app = FastAPI()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    user_type: Optional[str] = "patient" # Default to patient

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

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    try:
        user_text = request.message
        history = [{"role": m.role, "content": m.content} for m in request.history]

        started = len(history) > 1
        
        if not started:
            user_type = request.user_type or "patient"
            prompt = build_generator_prompt(user_text, user_type)
            
            # The unified prompt structure requests literature info for all users, 
            # so we enable papers=True to ensure the model has access to the vector store.
            answer = generate_answer(prompt, tools=True, papers=True)
            print(answer)
            return {"answer": answer}
        else:
            # Format history into a string prompt
            transcript = format_history(history)
            prompt = (
                "You are a helpful assistant in an ongoing conversation.\n"
                "Use the conversation history for context and continuity.\n\n"
                f"Conversation history:\n{transcript}\n\n"
                f"User: {user_text}\n"
                "Assistant:"
            )
            answer = generate_answer(prompt, tools=True, papers=True)
            return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
