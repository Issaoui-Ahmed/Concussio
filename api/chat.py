import asyncio
from contextlib import suppress
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.generator import generate_answer, generate_follow_ups
from core.prompts import build_generator_prompt
from core.scraper import ScrapingCache

app = FastAPI()
scraping_cache = ScrapingCache(refresh_interval_seconds=60)
scraping_loop_task: Optional[asyncio.Task[Any]] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    user_type: Optional[str] = "patient" # Default to patient

class FollowUpRequest(BaseModel):
    message: str
    answer: str
    user_type: Optional[str] = "patient"

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


async def scraping_refresh_loop() -> None:
    while True:
        await asyncio.sleep(scraping_cache.refresh_interval_seconds)
        await asyncio.to_thread(scraping_cache.refresh, True)


@app.on_event("startup")
async def startup_scraping_cache() -> None:
    global scraping_loop_task
    await asyncio.to_thread(scraping_cache.refresh, True)
    scraping_loop_task = asyncio.create_task(scraping_refresh_loop())


@app.on_event("shutdown")
async def shutdown_scraping_cache() -> None:
    global scraping_loop_task
    if scraping_loop_task is None:
        return

    scraping_loop_task.cancel()
    with suppress(asyncio.CancelledError):
        await scraping_loop_task
    scraping_loop_task = None

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


@app.post("/api/followups")
def followups_endpoint(request: FollowUpRequest):
    try:
        follow_ups = generate_follow_ups(
            user_message=request.message,
            assistant_answer=request.answer,
            user_type=request.user_type or "patient",
        )
        return {"follow_ups": follow_ups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scraping")
async def scraping_endpoint(force: bool = False):
    await asyncio.to_thread(scraping_cache.refresh, force)
    return scraping_cache.snapshot()




