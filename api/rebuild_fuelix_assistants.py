import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.prompts import build_fuelix_assistant_instructions


DEFAULT_FUELIX_BASE_URL = "https://api.fuelix.ai/v1"
DEFAULT_MODEL = "gpt-5.2"
DEFAULT_REASONING_EFFORT = "low"

# The single store all six assistants read. It holds both groups of documents: the Living
# Guideline Tools (kept in step by scripts/content_pipeline/vector_store.py) and the research
# papers, which are curated by hand and have no upstream link.
#
# There used to be two source stores combined into a third. That structure is gone -- the
# sources were deleted on 2026-08-02 once the combined store was confirmed to hold every one of
# their files by shared id. This script's names were wrong even before that: it looked for
# "Key papers to include" and "ConcussCare Combined Knowledge", neither of which ever existed.
# Running it would have raised on the missing sources; had that guard been bypassed it would
# have built a fresh empty store and repointed all six production assistants at it.
KNOWLEDGE_STORE_NAME = "ConcussCare Coach Knowledge Base"

ASSISTANT_SPECS = [
    ("patient", "ConcussCare Patient"),
    ("Healthcare Professional", "ConcussCare Healthcare Professional"),
    ("Parent or Caregiver", "ConcussCare Parent or Caregiver"),
    ("Youth", "ConcussCare Youth"),
    ("Teacher", "ConcussCare Teacher"),
    ("Coach", "ConcussCare Coach"),
]


@dataclass
class AssistantRebuildResult:
    user_type: str
    name: str
    assistant_id: Optional[str] = None
    action: str = ""
    ok: bool = False
    error: str = ""


class FuelIxRebuildError(RuntimeError):
    pass


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", DEFAULT_FUELIX_BASE_URL).rstrip("/")


def _headers() -> Dict[str, str]:
    token = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not token:
        raise FuelIxRebuildError("Missing FUELIX_API_KEY in environment.")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _error_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        fault = payload.get("fault")
        if isinstance(fault, dict) and isinstance(fault.get("faultstring"), str):
            return fault["faultstring"]
        for key in ("error", "message", "detail", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                return "; ".join(str(item) for item in value)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
    return str(payload)


def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 120,
    max_retries: int = 4,
) -> Any:
    url = f"{_base_url()}{path}"
    for attempt in range(max_retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=_headers(),
                params=params,
                json=json_body,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            raise FuelIxRebuildError(f"{method} {path} request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text}

        if response.status_code == 429 and attempt < max_retries:
            retry_after = response.headers.get("retry-after")
            try:
                sleep_seconds = min(65.0, max(1.0, float(retry_after))) if retry_after else 65.0
            except ValueError:
                sleep_seconds = 65.0
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 400:
            raise FuelIxRebuildError(f"{method} {path} failed ({response.status_code}): {_error_detail(payload)}")
        return payload

    raise FuelIxRebuildError(f"{method} {path} failed after retrying rate limits.")


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _paginated_items(path: str, *, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    cursor_param = "after"
    while True:
        request_params = {"limit": 100}
        if params:
            request_params.update(params)
        if cursor:
            request_params[cursor_param] = cursor

        payload = _request("GET", path, params=request_params)
        items.extend(_extract_items(payload))

        if not isinstance(payload, dict) or not payload.get("has_more"):
            break
        next_page = payload.get("next_page")
        last_id = payload.get("last_id")
        if isinstance(next_page, str) and next_page:
            cursor = next_page
            cursor_param = "page"
            continue
        if isinstance(last_id, str) and last_id:
            cursor = last_id
            cursor_param = "after"
            continue
        raise FuelIxRebuildError(f"Paginated response for {path} had has_more=true but no cursor.")
    return items


def _find_by_name(items: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get("name") == name:
            return item
    return None


def _resolve_knowledge_store_id() -> str:
    """Find the store the assistants read. Never creates one.

    Refusing to create is the whole safety property here. A missing store means something is
    wrong with the account or the name, and the harmful response to that is to helpfully make an
    empty one -- every assistant would then be wired to a knowledge base with nothing in it, and
    the failure would show up as bad answers rather than an error.
    """
    stores = _paginated_items("/vector_stores", params={"order": "desc"})
    store = _find_by_name(stores, KNOWLEDGE_STORE_NAME)
    store_id = store.get("id") if isinstance(store, dict) else None
    if not isinstance(store_id, str) or not store_id:
        available = ", ".join(
            str(item.get("name")) for item in stores if isinstance(item, dict)
        ) or "(none)"
        raise FuelIxRebuildError(
            f'Vector store "{KNOWLEDGE_STORE_NAME}" not found, and this script will not create '
            f"one -- pointing the assistants at an empty store is worse than failing. "
            f"Available stores: {available}"
        )
    return store_id


def _vector_store_file_ids(vector_store_id: str) -> List[str]:
    ids: List[str] = []
    for item in _paginated_items(f"/vector_stores/{vector_store_id}/files", params={"order": "desc"}):
        file_id = item.get("id")
        if isinstance(file_id, str) and file_id:
            ids.append(file_id)
    return ids


def _published_corpus() -> str:
    """The recommendations corpus as actually published, read from Supabase.

    NOT `all_rec_markdown.md`. Nothing writes that file any more -- the nightly refresh runs on
    Vercel, where the filesystem is read-only, so it publishes from a live scrape and records
    what it sent in `content_state`. The committed file is a local-dev convenience that drifts
    the moment the site changes.

    That drift matters here specifically: this script rewrites the instructions of all six
    production assistants. Building them from a stale file would quietly roll the guideline back
    to whenever the file was last refreshed by hand.
    """
    from scripts.content_pipeline.state import load_corpus_state

    state = load_corpus_state()
    if state.error:
        raise FuelIxRebuildError(
            f"Could not read the published corpus from Supabase: {state.error}. "
            f"Refusing to rebuild assistants from a possibly stale local file."
        )
    if not state.found or not state.content:
        raise FuelIxRebuildError(
            "No corpus has been published yet (content_state is empty). Run the refresh first: "
            "python -m scripts.content_pipeline.cli refresh --corpus"
        )
    return state.content


def _inspect_knowledge_store() -> tuple[str, List[str]]:
    """Resolve the store and read its contents. Read-only.

    This script's job is assistants, not knowledge. It used to copy file ids between stores to
    assemble a combined one; that is now the content pipeline's business
    (`scripts/content_pipeline/vector_store.py`), which keeps the tool documents in step with
    the live listing and leaves the hand-curated papers alone. Duplicating any of that here
    would give two things permission to mutate the same store on different rules.
    """
    store_id = _resolve_knowledge_store_id()
    file_ids = _vector_store_file_ids(store_id)
    if not file_ids:
        raise FuelIxRebuildError(
            f'Vector store "{KNOWLEDGE_STORE_NAME}" ({store_id}) is empty. Refusing to wire the '
            f"assistants to a knowledge base with no documents."
        )
    return store_id, file_ids


def _assistant_payload(
    user_type: str, name: str, vector_store_ids: List[str], model: str, corpus: str
) -> Dict[str, Any]:
    return {
        "name": name,
        "description": f"ConcussCare assistant for {user_type}.",
        "model": model,
        "instructions": build_fuelix_assistant_instructions(
            user_type, recommendations_markdown=corpus
        ),
        "tools": [{"type": "reasoning"}],
        "reasoning": {"effort": DEFAULT_REASONING_EFFORT},
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "tool_resources": {"file_search": {"vector_store_ids": vector_store_ids}},
        "metadata": {
            "user_type": user_type,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
            "vector_store_names": [KNOWLEDGE_STORE_NAME],
            "rebuild_source": "api/rebuild_fuelix_assistants.py",
        },
    }


def rebuild_assistant(
    user_type: str,
    name: str,
    *,
    vector_store_ids: List[str],
    existing_assistants: List[Dict[str, Any]],
    model: str,
    dry_run: bool,
    corpus: str,
) -> AssistantRebuildResult:
    result = AssistantRebuildResult(user_type=user_type, name=name)
    existing = _find_by_name(existing_assistants, name)
    existing_id = existing.get("id") if isinstance(existing, dict) else None
    payload = _assistant_payload(user_type, name, vector_store_ids, model, corpus)

    try:
        if isinstance(existing_id, str) and existing_id:
            result.assistant_id = existing_id
            result.action = "would_update" if dry_run else "updated"
            if not dry_run:
                updated = _request("POST", f"/assistants/{existing_id}", json_body=payload)
                updated_id = updated.get("id") if isinstance(updated, dict) else None
                if isinstance(updated_id, str) and updated_id:
                    result.assistant_id = updated_id
            result.ok = True
            return result

        result.action = "would_create" if dry_run else "created"
        if dry_run:
            result.ok = True
            return result

        created = _request("POST", "/assistants", json_body=payload)
        created_id = created.get("id") if isinstance(created, dict) else None
        if not isinstance(created_id, str) or not created_id:
            raise FuelIxRebuildError(f"Create assistant response did not include id: {created}")
        result.assistant_id = created_id
        result.ok = True
    except Exception as exc:
        result.error = str(exc)

    return result


def _write_summary(
    results: List[AssistantRebuildResult],
    knowledge_store_id: str,
    knowledge_store_file_ids: List[str],
    *,
    model: str,
    dry_run: bool,
) -> Path:
    output = {
        "dry_run": dry_run,
        "created_at_unix": int(time.time()),
        "fuelix_product_id": os.getenv("FUELIX_PRODUCT_ID", "core").strip() or None,
        "model": model,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "knowledge_store_id": knowledge_store_id,
        "knowledge_store_name": KNOWLEDGE_STORE_NAME,
        "knowledge_store_file_count": len(knowledge_store_file_ids),
        "assistants": [asdict(result) for result in results],
        "counts": {
            "assistants_total": len(results),
            "assistants_ok": sum(1 for result in results if result.ok),
            "assistants_failed": sum(1 for result in results if not result.ok),
        },
    }
    suffix = "dry-run" if dry_run else "executed"
    output_path = PROJECT_ROOT / "api" / f"fuelix_assistant_rebuild_{suffix}_{int(time.time())}.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update the ConcussCare Fuel IX assistants.")
    parser.add_argument("--execute", action="store_true", help="Create or update assistants. Defaults to dry-run.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Fuel IX model to use. Defaults to {DEFAULT_MODEL}.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env()
    dry_run = not args.execute

    print(f"Fuel IX assistant rebuild ({'DRY RUN' if dry_run else 'EXECUTE'})")
    print(f"Fuel IX base URL: {_base_url()}")
    print(f"Fuel IX product-id: {os.getenv('FUELIX_PRODUCT_ID', 'core').strip() or '(none)'}")
    print(f"Model: {args.model}")

    knowledge_store_id, knowledge_store_file_ids = _inspect_knowledge_store()
    print(
        f"Knowledge store: {KNOWLEDGE_STORE_NAME} ({knowledge_store_id}) "
        f"with {len(knowledge_store_file_ids)} files"
    )

    corpus = _published_corpus()
    print(f"Corpus: {len(corpus)} chars, as published (from content_state)")

    existing_assistants = _paginated_items("/assistants", params={"order": "desc"})
    results = [
        rebuild_assistant(
            user_type,
            name,
            vector_store_ids=[knowledge_store_id],
            existing_assistants=existing_assistants,
            model=args.model,
            dry_run=dry_run,
            corpus=corpus,
        )
        for user_type, name in ASSISTANT_SPECS
    ]

    for result in results:
        status = "ok" if result.ok else "failed"
        id_part = f" ({result.assistant_id})" if result.assistant_id else ""
        print(f"{status}: {result.action} {result.name}{id_part}")
        if result.error:
            print(f"  error: {result.error}")

    summary_path = _write_summary(
        results,
        knowledge_store_id,
        knowledge_store_file_ids,
        model=args.model,
        dry_run=dry_run,
    )
    print(f"summary_json: {summary_path}")

    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
