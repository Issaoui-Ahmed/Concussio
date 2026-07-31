import json
import os
import re
from typing import Any, Dict, List, Optional

from core.fuelix_chat import fuelix_chat_completion
from core.prompts import CANONICAL_HEADINGS


DEFAULT_TRANSLATE_MODEL = "gpt-5.2"
SUPPORTED_LANGS = {"en", "fr"}

# Terms that MUST be translated even though they look like proper nouns. Without this the
# model reasonably reads "Living Guideline" as a brand name and, obeying the
# preserve-proper-nouns rule below, leaves it in English inside a French heading — producing
# "Recommandations des Living Guidelines".
GLOSSARY = [
    ("Living Guidelines Recommendations", "Recommandations des lignes directrices évolutives"),
    ("Living Guideline for Pediatric Concussion", "lignes directrices évolutives sur les commotions cérébrales pédiatriques"),
    ("Living Guidelines", "lignes directrices évolutives"),
    ("Living Guideline", "lignes directrices évolutives"),
    ("Summary", "Résumé"),
    ("Information From the Literature", "Informations tirées de la littérature"),
]


def _build_glossary_block() -> str:
    pairs = "\n".join(f'  - "{en}" <-> "{fr}"' for en, fr in GLOSSARY)
    en_headings = "\n".join(f"  {item}" for item in CANONICAL_HEADINGS["en"])
    fr_headings = "\n".join(f"  {item}" for item in CANONICAL_HEADINGS["fr"])
    return (
        "GLOSSARY — these terms are ALWAYS translated. This rule OVERRIDES the "
        "preserve-proper-nouns rule above; do not treat them as brand or product names:\n"
        f"{pairs}\n"
        "FIXED SECTION HEADINGS — when an item is one of these headings (or begins with one), "
        "emit the exact counterpart below, character for character, including the space before "
        "the colon in French. Do not re-word or re-punctuate them.\n"
        "English:\n"
        f"{en_headings}\n"
        "French:\n"
        f"{fr_headings}\n"
        'NEVER produce "Recommandations des Living Guidelines" or '
        '"lignes directrices vivantes" — the only correct French form is '
        f'"{CANONICAL_HEADINGS["fr"][1]}".\n'
        "EXCEPTION — when \"Living Guideline\" is part of the TITLE of a specific named tool, "
        "protocol, or document (for example \"Living Guideline Return to Activity, Sports, and "
        "School Protocol\"), keep the title in English: it names a real English-language "
        "document that the reader will have to find under that name. The glossary applies to "
        "the section headings and to generic references to the guideline itself, not to titles "
        "of published tools."
    )


def _get_translate_model() -> str:
    value = (os.getenv("FUELIX_TRANSLATE_MODEL") or DEFAULT_TRANSLATE_MODEL).strip()
    return value or DEFAULT_TRANSLATE_MODEL


def _opposite_lang(lang: str) -> str:
    return "fr" if lang == "en" else "en"


def _build_translation_messages(texts: List[str], target_lang: Optional[str]) -> List[Dict[str, str]]:
    if target_lang in SUPPORTED_LANGS:
        target_name = "French" if target_lang == "fr" else "English"
        target_clause = (
            f'Translate every item into {target_name} (language code "{target_lang}"). '
            "If an item is already in that language, return it unchanged."
        )
    else:
        target_clause = (
            "The conversation uses English and French only. Detect the source language, "
            "then translate every item into the OTHER of those two languages."
        )

    system = (
        "You are a professional translator for a medical (concussion care) assistant. "
        "You translate only between English and French.\n"
        f"{target_clause}\n"
        "Rules:\n"
        "- Preserve Markdown structure exactly: headings, **bold**, lists, tables, blockquotes, and line breaks.\n"
        "- Keep links and URLs unchanged. Keep proper nouns, author names, in-text citation keys "
        "(e.g. (Smith et al., 2020)), and tool names unchanged — EXCEPT for the glossary terms below.\n"
        "- Translate the meaning faithfully and naturally. Do NOT add, remove, summarize, explain, or answer anything.\n"
        "- Translate each item independently and keep the same order and the same number of items.\n"
        f"{_build_glossary_block()}\n"
        'Return ONLY strict JSON (no prose, no code fences) in exactly this shape: '
        '{"source_lang":"en|fr","target_lang":"en|fr","texts":["...","..."]}. '
        '"source_lang" is the detected language of the input items; "target_lang" is the language you translated into.'
    )
    user = json.dumps({"items": texts}, ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_translation_payload(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None

    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or not isinstance(parsed.get("texts"), list):
            continue
        source = parsed.get("source_lang")
        target = parsed.get("target_lang")
        return {
            "source_lang": source if source in SUPPORTED_LANGS else None,
            "target_lang": target if target in SUPPORTED_LANGS else None,
            "texts": [str(item) for item in parsed["texts"]],
        }
    return None


def translate_texts(texts: List[str], target_lang: Optional[str] = None) -> Dict[str, Any]:
    """Translate a list of strings between English and French via Fuel IX.

    If ``target_lang`` is omitted, the source language is detected and each item is
    translated into the OTHER language. Returns
    ``{"source_lang": "en"|"fr", "target_lang": "en"|"fr", "texts": [...]}``.
    """
    normalized_target = (target_lang or "").strip().lower() or None
    if normalized_target is not None and normalized_target not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported target_lang: {target_lang!r}. Use 'en' or 'fr'.")

    items = [text if isinstance(text, str) else str(text) for text in texts]

    # Nothing meaningful to translate: echo back.
    if not any(item.strip() for item in items):
        resolved = normalized_target or "en"
        return {"source_lang": resolved, "target_lang": resolved, "texts": items}

    raw = fuelix_chat_completion(
        _build_translation_messages(items, normalized_target),
        model=_get_translate_model(),
        reasoning_effort="low",
    )

    parsed = _parse_translation_payload(raw)
    if parsed is None or len(parsed["texts"]) != len(items):
        raise RuntimeError("Fuel IX translation response could not be parsed into the expected shape.")

    target = parsed["target_lang"] or normalized_target
    source = parsed["source_lang"]
    if target is None:
        target = _opposite_lang(source) if source in SUPPORTED_LANGS else "fr"
    if source is None:
        source = _opposite_lang(target)

    return {"source_lang": source, "target_lang": target, "texts": parsed["texts"]}
