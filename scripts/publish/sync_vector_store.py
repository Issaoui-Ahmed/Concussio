"""Sync the Living Guideline Tools vector store with the current tool set.

Idempotent by content hash: a document is re-uploaded only when its bytes changed. Without
that, every run would churn the whole store and invalidate its index for no reason.

    python -m scripts.publish.sync_vector_store              # dry run (default)
    python -m scripts.publish.sync_vector_store --execute    # apply

⚠️ UNVERIFIED AGAINST THE LIVE API. The upload/attach/detach calls follow the shapes proven by
the old `api/migrate_openai_vector_stores_to_fuelix.py` (deleted with the OpenAI cleanup — see
`archive/README.md`; recoverable from git history), but this script has never been run against
Fuel IX — doing so means mutating the production store. Run it with the default dry run first
and read the plan it prints before ever passing --execute.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from core.scraper import DEFAULT_HEADERS
from scripts.content_pipeline.fetch import fetch_english_tools

load_dotenv()

DEFAULT_BASE_URL = "https://api.fuelix.ai/v1"
STORE_NAME = "Living guideline tools"

# Filename marker so pipeline-managed files are distinguishable from anything uploaded by
# hand. The sync only ever detaches files carrying this marker — a human-uploaded document is
# never removed by automation.
MANAGED_PREFIX = "lgt__"


@dataclass
class RemoteFile:
    file_id: str
    filename: str

    @property
    def is_managed(self) -> bool:
        return self.filename.startswith(MANAGED_PREFIX)

    @property
    def content_hash(self) -> Optional[str]:
        """Hash embedded in the managed filename: lgt__<hash>__<slug>.pdf"""
        parts = self.filename.split("__")
        return parts[1] if self.is_managed and len(parts) >= 3 else None


def _api_key() -> str:
    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        raise SystemExit("FUELIX_API_KEY is not set.")
    return key


def _base_url() -> str:
    return (os.getenv("FUELIX_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _headers(json_content: bool = False) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {_api_key()}"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _request(method: str, path: str, **kwargs) -> object:
    response = requests.request(
        method, f"{_base_url()}{path}", headers=_headers(kwargs.pop("json_content", False)),
        timeout=120, **kwargs
    )
    if response.status_code >= 400:
        raise SystemExit(f"Fuel IX {method} {path} -> {response.status_code}: {response.text[:400]}")
    try:
        return response.json()
    except ValueError:
        return {}


def _items(payload: object) -> List[Dict[str, object]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    return []


def resolve_store_id() -> str:
    configured = (os.getenv("FUELIX_TOOLS_VECTOR_STORE_ID") or "").strip()
    if configured:
        return configured
    for store in _items(_request("GET", "/vector_stores", params={"limit": 100})):
        if str(store.get("name", "")).strip().lower() == STORE_NAME.lower():
            return str(store["id"])
    raise SystemExit(f'Vector store "{STORE_NAME}" not found and FUELIX_TOOLS_VECTOR_STORE_ID is unset.')


def list_store_files(store_id: str) -> List[RemoteFile]:
    files: List[RemoteFile] = []
    for entry in _items(_request("GET", f"/vector_stores/{store_id}/files", params={"limit": 100})):
        file_id = str(entry.get("id", ""))
        metadata = _request("GET", f"/files/{file_id}")
        filename = str(metadata.get("filename", "")) if isinstance(metadata, dict) else ""
        files.append(RemoteFile(file_id=file_id, filename=filename))
    return files


def _slug(value: str) -> str:
    keep = [ch if ch.isalnum() else "-" for ch in value.lower()]
    return "".join(keep).strip("-")[:60] or "tool"


def download(url: str) -> Optional[bytes]:
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=120)
        response.raise_for_status()
        return response.content
    except Exception as exc:
        print(f"  ! download failed: {url} ({type(exc).__name__}: {exc})")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply changes. Defaults to dry run.")
    args = parser.parse_args()
    dry_run = not args.execute

    print(f"Vector store sync ({'DRY RUN' if dry_run else 'EXECUTE'})")

    tools, errors = fetch_english_tools()
    for error in errors:
        print(f"  fetch error: {error}")
    if not tools:
        print("No tools fetched — refusing to sync an empty set.")
        return 1
    print(f"  {len(tools)} tools listed upstream")

    store_id = resolve_store_id()
    existing = list_store_files(store_id)
    managed = {file.content_hash: file for file in existing if file.is_managed}
    print(f"  store {store_id}: {len(existing)} files ({len(managed)} pipeline-managed)")

    desired: Dict[str, tuple[str, bytes]] = {}
    for tool in tools:
        content = download(tool.url)
        if content is None:
            continue
        digest = hashlib.sha256(content).hexdigest()[:16]
        desired[digest] = (f"{MANAGED_PREFIX}{digest}__{_slug(tool.title)}.pdf", content)

    to_upload = [digest for digest in desired if digest not in managed]
    to_detach = [file for digest, file in managed.items() if digest not in desired]

    print(f"\n  upload: {len(to_upload)}   detach: {len(to_detach)}   "
          f"unchanged: {len(set(desired) & set(managed))}")
    for digest in to_upload:
        print(f"    + {desired[digest][0]}")
    for file in to_detach:
        print(f"    - {file.filename}")

    if dry_run:
        print("\nDRY RUN — nothing changed. Re-run with --execute to apply.")
        return 0

    for digest in to_upload:
        filename, content = desired[digest]
        uploaded = _request(
            "POST", "/files",
            files={"file": (filename, content, "application/pdf"), "purpose": (None, "assistants")},
        )
        file_id = str(uploaded.get("id", "")) if isinstance(uploaded, dict) else ""
        if not file_id:
            print(f"    ! upload returned no id for {filename}")
            continue
        _request("POST", f"/vector_stores/{store_id}/files",
                 json={"file_id": file_id}, json_content=True)
        print(f"    uploaded {filename}")

    for file in to_detach:
        _request("DELETE", f"/vector_stores/{store_id}/files/{file.file_id}")
        print(f"    detached {file.filename}")

    print("\nSync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
