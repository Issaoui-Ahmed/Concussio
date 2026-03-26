import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.prompts import build_generator_prompt


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", "https://api.fuelix.ai/v1").rstrip("/")


def _headers() -> Dict[str, str]:
    token = os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY")
    if not token:
        raise RuntimeError("Missing Fuel IX API key in environment.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _request(
    method: str,
    path: str,
    *,
    params: Dict[str, Any] | None = None,
    json_body: Dict[str, Any] | None = None,
) -> Any:
    url = f"{_base_url()}{path}"
    response = requests.request(
        method=method,
        url=url,
        headers=_headers(),
        params=params,
        json=json_body,
        timeout=120,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {payload}")
    return payload


def _list_all(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    after: str | None = None
    while True:
        params: Dict[str, Any] = {"limit": 100, "order": "desc"}
        if after:
            params["after"] = after
        payload = _request("GET", path, params=params)
        chunk = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(chunk, list) or not chunk:
            break
        for item in chunk:
            if isinstance(item, dict):
                items.append(item)

        has_more = bool(payload.get("has_more")) if isinstance(payload, dict) else False
        last_id = payload.get("last_id") if isinstance(payload, dict) else None
        if not has_more or not isinstance(last_id, str) or not last_id:
            break
        after = last_id
    return items


def _delete_all_assistants() -> Tuple[int, List[str]]:
    assistants = _list_all("/assistants")
    deleted_ids: List[str] = []
    for assistant in assistants:
        assistant_id = assistant.get("id")
        if not isinstance(assistant_id, str) or not assistant_id:
            continue
        _request("DELETE", f"/assistants/{assistant_id}")
        deleted_ids.append(assistant_id)
    return len(deleted_ids), deleted_ids


def _delete_all_vector_stores() -> Tuple[int, List[str]]:
    vector_stores = _list_all("/vector_stores")
    deleted_ids: List[str] = []
    for store in vector_stores:
        store_id = store.get("id")
        if not isinstance(store_id, str) or not store_id:
            continue
        _request("DELETE", f"/vector_stores/{store_id}")
        deleted_ids.append(store_id)
    return len(deleted_ids), deleted_ids


def _create_vector_stores() -> Dict[str, str]:
    stores_to_create = [
        ("living_guideline_tools", "Living guideline tools"),
        ("key_papers_to_include", "Key papers to include"),
    ]
    created: Dict[str, str] = {}
    for key, name in stores_to_create:
        payload = _request(
            "POST",
            "/vector_stores",
            json_body={"name": name, "metadata": {"purpose": key}},
        )
        store_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(store_id, str) or not store_id:
            raise RuntimeError(f"Vector store '{name}' created without id: {payload}")
        created[key] = store_id
    return created


def _create_assistants(vector_store_ids: List[str]) -> Dict[str, str]:
    assistant_specs = [
        ("patient", "ConcussCare Patient"),
        ("Healthcare Professional", "ConcussCare Healthcare Professional"),
        ("Parent or Caregiver", "ConcussCare Parent or Caregiver"),
        ("Youth", "ConcussCare Youth"),
        ("Teacher", "ConcussCare Teacher"),
        ("Coach", "ConcussCare Coach"),
    ]

    if not vector_store_ids:
        raise RuntimeError("No vector store ids available for assistant creation.")

    primary_store_id = vector_store_ids[0]
    secondary_store_ids = vector_store_ids[1:]

    created: Dict[str, str] = {}
    for user_type, name in assistant_specs:
        instructions = build_generator_prompt("{{USER_QUERY}}", user_type)
        metadata: Dict[str, Any] = {"user_type": user_type}
        if secondary_store_ids:
            metadata["additional_vector_store_ids"] = secondary_store_ids

        payload = _request(
            "POST",
            "/assistants",
            json_body={
                "name": name,
                "description": f"ConcussCare assistant for {user_type}.",
                "model": "claude-sonnet-4-5",
                "instructions": instructions,
                "tools": [],
                "tool_resources": {"file_search": {"vector_store_ids": [primary_store_id]}},
                "metadata": metadata,
            },
        )
        assistant_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(assistant_id, str) or not assistant_id:
            raise RuntimeError(f"Assistant '{name}' created without id: {payload}")
        created[user_type] = assistant_id
    return created


def main() -> int:
    _load_env()

    deleted_assistants_count, deleted_assistant_ids = _delete_all_assistants()
    deleted_stores_count, deleted_store_ids = _delete_all_vector_stores()

    created_stores = _create_vector_stores()
    vector_store_ids = list(created_stores.values())
    created_assistants = _create_assistants(vector_store_ids)

    summary = {
        "deleted_assistants_count": deleted_assistants_count,
        "deleted_assistant_ids": deleted_assistant_ids,
        "deleted_vector_stores_count": deleted_stores_count,
        "deleted_vector_store_ids": deleted_store_ids,
        "created_vector_stores": created_stores,
        "created_assistants": created_assistants,
    }

    output_path = PROJECT_ROOT / "api" / "fuelix_rag_bootstrap_summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nSummary written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
