from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.generator import generate_follow_ups


app = FastAPI()


class FollowUpRequest(BaseModel):
    message: str
    answer: str
    user_type: Optional[str] = "patient"


@app.post("/")
@app.post("/api/followups")
def followups_endpoint(request: FollowUpRequest):
    try:
        follow_ups = generate_follow_ups(
            user_message=request.message,
            assistant_answer=request.answer,
            user_type=request.user_type or "patient",
        )
        return {"follow_ups": follow_ups}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
