from dotenv import load_dotenv
import os
import json
import re
from typing import List
from openai import OpenAI



load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FOLLOWUP_MODEL = os.getenv("OPENAI_FOLLOWUP_MODEL", "gpt-4.1-mini")

client = OpenAI(api_key=OPENAI_API_KEY)

FALLBACK_FOLLOW_UPS = [
    "Can you explain that in simpler terms?",
    "What should I do first?",
    "What warning signs mean I should seek urgent care?",
]
    
def generate_answer(query, tools = False, papers = False):
    vector_store_ids = []
    if tools:
        vector_store_ids.append("vs_690f8e0dc12c8191b4e662b7d94b7377")
    if papers:
        vector_store_ids.append("vs_68e5590288048191946069efcdfe8f52")
    if len(vector_store_ids) == 0:
            response = client.responses.create(
            model="gpt-5.2",
            input=query,
            reasoning={"effort": "low"},
            text={
            "verbosity": "medium",  
        })
    else:
        response = client.responses.create(
            model="gpt-5.2",
            input=query,
            reasoning={"effort": "low"},
            text={
            "verbosity": "medium",  
        },
            tools=[{
            "type": "file_search",
            "vector_store_ids": vector_store_ids
        }])
    
    return response.output_text


def _clean_follow_up(text: str) -> str:
    cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", (text or "").strip())
    cleaned = cleaned.strip('"').strip("'").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned and cleaned[-1] not in "?!":
        cleaned = cleaned.rstrip(".;:") + "?"
    return cleaned


def _extract_follow_ups(raw_output: str) -> List[str]:
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

    for fallback in FALLBACK_FOLLOW_UPS:
        if len(cleaned_follow_ups) == 3:
            break
        key = fallback.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_follow_ups.append(fallback)

    return cleaned_follow_ups[:3]


def generate_follow_ups(user_message: str, assistant_answer: str, user_type: str = "patient") -> List[str]:
    prompt = f"""
You create follow-up question suggestions for a healthcare chatbot.

Audience: {user_type}
User question: {user_message}
Assistant answer: {assistant_answer}

Task:
- Generate exactly 3 concise follow-up questions the user might ask next.
- Keep each question under 14 words.
- Make each question specific to the assistant answer.
- Avoid repeating the original user question.
- Return JSON only in this exact shape:
{{"follow_ups":["question 1","question 2","question 3"]}}
""".strip()

    try:
        response = client.responses.create(
            model=FOLLOWUP_MODEL,
            input=prompt,
        )
        return _extract_follow_ups(response.output_text)
    except Exception:
        return FALLBACK_FOLLOW_UPS.copy()



if __name__ == "__main__":
    query = "If an adolescent presents with suspected concussion but is also under the influence of alcohol or cannabis does this chance my examination?"
    rec_markdown = """jj"""
    print(generate_answer(query))

