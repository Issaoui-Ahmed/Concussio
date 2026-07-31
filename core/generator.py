"""Follow-up question suggestions, generated through Fuel IX.

This module also held ``generate_answer()``, the OpenAI Responses API path that produced the
main chat answer. Answers come from ``core.fuelix_chat.generate_fuelix_answer`` now; the old
implementation is kept at ``archive/openai/generator_openai.py``.
"""

from dotenv import load_dotenv
import os
import json
import re
from typing import List

from core.fuelix_chat import fuelix_chat_completion



load_dotenv()

# An OpenAI-branded model id, but served through Fuel IX's OpenAI-compatible API.
FOLLOWUP_MODEL = os.getenv("FUELIX_FOLLOWUP_MODEL", "gpt-4.1-mini")

FALLBACK_FOLLOW_UPS_BY_LANG = {
    "en": [
        "Can you explain that in simpler terms?",
        "What should I do first?",
        "What warning signs mean I should seek urgent care?",
    ],
    "fr": [
        "Pouvez-vous expliquer cela plus simplement ?",
        "Que dois-je faire en premier ?",
        "Quels signes d'alerte doivent m'amener à consulter d'urgence ?",
    ],
}

# Kept for backwards compatibility with existing callers.
FALLBACK_FOLLOW_UPS = FALLBACK_FOLLOW_UPS_BY_LANG["en"]


def _fallback_follow_ups(lang):
    return list(FALLBACK_FOLLOW_UPS_BY_LANG.get(lang or "en", FALLBACK_FOLLOW_UPS_BY_LANG["en"]))


def _clean_follow_up(text: str) -> str:
    cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", (text or "").strip())
    cleaned = cleaned.strip('"').strip("'").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned and cleaned[-1] not in "?!":
        cleaned = cleaned.rstrip(".;:") + "?"
    return cleaned


def _extract_follow_ups(raw_output: str, lang: str = "en") -> List[str]:
    raw = (raw_output or "").strip()
    candidates: List[str] = []

    def assign_candidates(parsed: object) -> bool:
        nonlocal candidates
        if isinstance(parsed, dict) and isinstance(parsed.get("follow_ups"), list):
            candidates = [str(item) for item in parsed["follow_ups"]]
            return True
        if isinstance(parsed, list):
            candidates = [str(item) for item in parsed]
            return True
        return False

    if raw:
        try:
            if not assign_candidates(json.loads(raw)):
                json_match = re.search(r"\{[\s\S]*\}", raw)
                if json_match:
                    assign_candidates(json.loads(json_match.group(0)))
        except json.JSONDecodeError:
            pass

    if not candidates and raw:
        for line in raw.splitlines():
            cleaned_line = line.strip()
            if not cleaned_line:
                continue
            bullet_free = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned_line)
            if bullet_free:
                candidates.append(bullet_free)

    cleaned_follow_ups: List[str] = []
    seen = set()
    for item in candidates:
        cleaned = _clean_follow_up(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_follow_ups.append(cleaned)
        if len(cleaned_follow_ups) == 3:
            break

    for fallback in _fallback_follow_ups(lang):
        if len(cleaned_follow_ups) == 3:
            break
        key = fallback.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_follow_ups.append(fallback)

    return cleaned_follow_ups[:3]


def generate_follow_ups(
    user_message: str,
    assistant_answer: str,
    user_type: str = "patient",
    lang: str = "en",
) -> List[str]:
    resolved_lang = lang if lang in FALLBACK_FOLLOW_UPS_BY_LANG else "en"
    language_name = "French" if resolved_lang == "fr" else "English"

    prompt = f"""
You create follow-up question suggestions for a healthcare chatbot.

Audience: {user_type}
User question: {user_message}
Assistant answer: {assistant_answer}

Task:
- Generate exactly 3 concise follow-up questions the user might ask next.
- Write every question in {language_name}. This is required even if the question or answer above is in another language.
- Keep each question under 14 words.
- Make each question specific to the assistant answer.
- Avoid repeating the original user question.
- Return JSON only in this exact shape:
{{"follow_ups":["question 1","question 2","question 3"]}}
""".strip()

    try:
        raw_output = fuelix_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=FOLLOWUP_MODEL,
        )
        return _extract_follow_ups(raw_output, resolved_lang)
    except Exception:
        return _fallback_follow_ups(resolved_lang)

