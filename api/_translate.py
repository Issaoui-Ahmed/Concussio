from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Optional
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.translator import translate_texts


app = FastAPI()


class TranslateRequest(BaseModel):
    texts: List[str]
    target_lang: Optional[Literal["en", "fr"]] = None


@app.post("/")
@app.post("/api/translate")
def translate_endpoint(request: TranslateRequest):
    if not request.texts:
        raise HTTPException(status_code=400, detail="texts must contain at least one item.")
    try:
        return translate_texts(request.texts, request.target_lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
