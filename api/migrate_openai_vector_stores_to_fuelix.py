import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_FUELIX_BASE_URL = "https://api.fuelix.ai/v1"


@dataclass(frozen=True)
class StoreMigrationSpec:
    openai_vector_store_id: str
    fuelix_name: str
    purpose: str


@dataclass
class FileMigrationResult:
    openai_file_id: str
    filename: str = ""
    openai_vector_store_status: str = ""
    dry_run: bool = False
    content_source: str = ""
    uploaded_filename: str = ""
    fuelix_file_id: Optional[str] = None
    fuelix_vector_store_file_id: Optional[str] = None
    ok: bool = False
    skipped: bool = False
    error: str = ""


@dataclass
class StoreMigrationResult:
    openai_vector_store_id: str
    fuelix_name: str
    purpose: str
    fuelix_vector_store_id: Optional[str] = None
    reused_existing_store: bool = False
    created_store: bool = False
    dry_run: bool = True
    files: List[FileMigrationResult] = field(default_factory=list)
    error: str = ""


STORE_SPECS = [
    StoreMigrationSpec(
        openai_vector_store_id="vs_690f8e0dc12c8191b4e662b7d94b7377",
        fuelix_name="Living guideline tools",
        purpose="living_guideline_tools",
    ),
    StoreMigrationSpec(
        openai_vector_store_id="vs_68e5590288048191946069efcdfe8f52",
        fuelix_name="Key papers to include",
        purpose="key_papers_to_include",
    ),
]


class MigrationError(RuntimeError):
    pass


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _openai_base_url() -> str:
    return os.getenv("OPENAI_API_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")


def _fuelix_base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", DEFAULT_FUELIX_BASE_URL).rstrip("/")


def _openai_headers() -> Dict[str, str]:
    token = os.getenv("OPENAI_API_KEY", "").strip()
    if not token:
        raise MigrationError("Missing OPENAI_API_KEY in environment.")
    return {"Authorization": f"Bearer {token}"}


def _fuelix_headers(*, json_content: bool) -> Dict[str, str]:
    token = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not token:
        raise MigrationError("Missing FUELIX_API_KEY in environment.")

    headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
    if json_content:
        headers["Content-Type"] = "application/json"

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
            if isinstance(value, list) and value:
                return "; ".join(str(item) for item in value)
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
    return str(payload)


def _parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"message": response.text}


def _request_json(
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 120,
    max_retries: int = 4,
) -> Any:
    for attempt in range(max_retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                data=data,
                files=files,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            raise MigrationError(f"{method} {url} request failed: {exc}") from exc

        payload = _parse_json_response(response)
        if response.status_code == 429 and attempt < max_retries:
            retry_after = response.headers.get("retry-after")
            try:
                sleep_seconds = min(65.0, max(1.0, float(retry_after))) if retry_after else 65.0
            except ValueError:
                sleep_seconds = 65.0
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 400:
            raise MigrationError(f"{method} {url} failed ({response.status_code}): {_error_detail(payload)}")
        return payload

    raise MigrationError(f"{method} {url} failed after retrying rate limits.")


def _download_bytes(url: str, *, headers: Dict[str, str], timeout_seconds: int = 120) -> bytes:
    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise MigrationError(f"GET {url} request failed: {exc}") from exc

    if response.status_code >= 400:
        payload = _parse_json_response(response)
        raise MigrationError(f"GET {url} failed ({response.status_code}): {_error_detail(payload)}")

    if not response.content:
        raise MigrationError(f"GET {url} returned an empty body.")
    return response.content


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _paginated_items(base_url: str, path: str, *, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    cursor_param = "after"
    while True:
        request_params = {"limit": 100}
        if params:
            request_params.update(params)
        if cursor:
            request_params[cursor_param] = cursor

        payload = _request_json("GET", f"{base_url}{path}", headers=headers, params=request_params)
        chunk = _extract_items(payload)
        items.extend(chunk)

        if not isinstance(payload, dict):
            break
        has_more = bool(payload.get("has_more"))
        next_page = payload.get("next_page")
        last_id = payload.get("last_id")
        if not has_more:
            break
        if isinstance(next_page, str) and next_page:
            cursor = next_page
            cursor_param = "page"
            continue
        if isinstance(last_id, str) and last_id:
            cursor = last_id
            cursor_param = "after"
            continue
        raise MigrationError(f"Paginated response for {path} had has_more=true but no usable cursor.")
    return items


def _openai_vector_store_files(vector_store_id: str) -> List[Dict[str, Any]]:
    return _paginated_items(
        _openai_base_url(),
        f"/vector_stores/{vector_store_id}/files",
        headers=_openai_headers(),
        params={"order": "asc"},
    )


def _openai_file_metadata(file_id: str) -> Dict[str, Any]:
    payload = _request_json(
        "GET",
        f"{_openai_base_url()}/files/{file_id}",
        headers=_openai_headers(),
    )
    if not isinstance(payload, dict):
        raise MigrationError(f"OpenAI file metadata response for {file_id} was not an object.")
    return payload


def _openai_file_bytes(file_id: str) -> bytes:
    return _download_bytes(
        f"{_openai_base_url()}/files/{file_id}/content",
        headers=_openai_headers(),
    )


def _parsed_text_filename(filename: str, fallback_file_id: str) -> str:
    safe = _safe_filename(filename, fallback_file_id)
    if safe.lower().endswith(".txt"):
        return safe
    if "." in safe:
        return f"{safe.rsplit('.', 1)[0]}.txt"
    return f"{safe}.txt"


def _openai_vector_store_parsed_text(vector_store_id: str, file_id: str, filename: str) -> bytes:
    blocks: List[str] = [
        f"Source filename: {filename}",
        f"OpenAI file id: {file_id}",
        f"OpenAI vector store id: {vector_store_id}",
        "Content source: OpenAI parsed vector store file content",
        "",
    ]
    page_token: Optional[str] = None

    while True:
        params = {"page": page_token} if page_token else None
        payload = _request_json(
            "GET",
            f"{_openai_base_url()}/vector_stores/{vector_store_id}/files/{file_id}/content",
            headers=_openai_headers(),
            params=params,
        )
        if not isinstance(payload, dict):
            raise MigrationError(f"OpenAI parsed content response for {file_id} was not an object.")

        content_items = payload.get("data")
        if not isinstance(content_items, list):
            content_items = payload.get("content")
        if not isinstance(content_items, list):
            raise MigrationError(f"OpenAI parsed content response for {file_id} did not include content data.")

        for item in content_items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            if text.strip().startswith("<PARSED TEXT FOR PAGE:"):
                continue
            blocks.append(text.strip())

        has_more = bool(payload.get("has_more"))
        next_page = payload.get("next_page")
        if not has_more:
            break
        if not isinstance(next_page, str) or not next_page:
            raise MigrationError(f"OpenAI parsed content for {file_id} has more pages but no next_page token.")
        page_token = next_page

    parsed = "\n\n".join(blocks).strip() + "\n"
    if not parsed.strip():
        raise MigrationError(f"OpenAI parsed content for {file_id} was empty.")
    return parsed.encode("utf-8")


def _openai_file_for_upload(vector_store_id: str, file_id: str, filename: str) -> tuple[str, bytes, str, str]:
    try:
        return filename, _openai_file_bytes(file_id), "openai_file_content", (
            "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
        )
    except MigrationError as exc:
        message = str(exc)
        if "Not allowed to download files of purpose: assistants" not in message:
            raise

    parsed_filename = _parsed_text_filename(filename, file_id)
    return (
        parsed_filename,
        _openai_vector_store_parsed_text(vector_store_id, file_id, filename),
        "openai_vector_store_parsed_content",
        "text/plain",
    )


def _fuelix_vector_stores() -> List[Dict[str, Any]]:
    return _paginated_items(
        _fuelix_base_url(),
        "/vector_stores",
        headers=_fuelix_headers(json_content=True),
        params={"order": "desc"},
    )


def _find_fuelix_store_by_name(name: str) -> Optional[Dict[str, Any]]:
    for item in _fuelix_vector_stores():
        if item.get("name") == name:
            return item
    return None


def _create_fuelix_vector_store(spec: StoreMigrationSpec) -> str:
    payload = _request_json(
        "POST",
        f"{_fuelix_base_url()}/vector_stores",
        headers=_fuelix_headers(json_content=True),
        json_body={
            "name": spec.fuelix_name,
            "metadata": {"purpose": spec.purpose},
        },
    )
    store_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(store_id, str) or not store_id:
        raise MigrationError(f"Fuel IX vector store '{spec.fuelix_name}' was created without an id: {payload}")
    return store_id


def _resolve_fuelix_vector_store(spec: StoreMigrationSpec, *, dry_run: bool) -> StoreMigrationResult:
    existing = _find_fuelix_store_by_name(spec.fuelix_name)
    result = StoreMigrationResult(
        openai_vector_store_id=spec.openai_vector_store_id,
        fuelix_name=spec.fuelix_name,
        purpose=spec.purpose,
        dry_run=dry_run,
    )

    if existing:
        store_id = existing.get("id")
        if not isinstance(store_id, str) or not store_id:
            raise MigrationError(f"Existing Fuel IX store '{spec.fuelix_name}' has no usable id.")
        result.fuelix_vector_store_id = store_id
        result.reused_existing_store = True
        return result

    if dry_run:
        return result

    result.fuelix_vector_store_id = _create_fuelix_vector_store(spec)
    result.created_store = True
    return result


def _fuelix_files() -> List[Dict[str, Any]]:
    return _paginated_items(
        _fuelix_base_url(),
        "/files",
        headers=_fuelix_headers(json_content=True),
    )


def _fuelix_vector_store_files(vector_store_id: str) -> List[Dict[str, Any]]:
    return _paginated_items(
        _fuelix_base_url(),
        f"/vector_stores/{vector_store_id}/files",
        headers=_fuelix_headers(json_content=True),
        params={"order": "desc"},
    )


def _fuelix_attached_filenames(vector_store_id: Optional[str]) -> set[str]:
    if not vector_store_id:
        return set()

    attached_ids: set[str] = set()
    for item in _fuelix_vector_store_files(vector_store_id):
        file_id = item.get("id")
        if isinstance(file_id, str) and file_id:
            attached_ids.add(file_id)

    filenames: set[str] = set()
    resolved_ids: set[str] = set()
    for item in _fuelix_files():
        file_id = item.get("id")
        if not isinstance(file_id, str) or file_id not in attached_ids:
            continue
        resolved_ids.add(file_id)
        filename = item.get("filename")
        if isinstance(filename, str) and filename.strip():
            filenames.add(filename.strip())

    unresolved_ids = attached_ids - resolved_ids
    if unresolved_ids:
        raise MigrationError(
            "Unable to resolve all existing Fuel IX filenames from /files; refusing to upload because that could create duplicates. "
            + ", ".join(sorted(unresolved_ids))
        )
    return filenames


def _upload_fuelix_file(filename: str, content: bytes, content_type: str) -> str:
    files = {
        "file": (
            filename,
            content,
            content_type,
        )
    }
    payload = _request_json(
        "POST",
        f"{_fuelix_base_url()}/files",
        headers=_fuelix_headers(json_content=False),
        data={"purpose": "assistants"},
        files=files,
    )
    file_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(file_id, str) or not file_id:
        raise MigrationError(f"Fuel IX file upload for '{filename}' did not return an id: {payload}")
    return file_id


def _attach_fuelix_file(vector_store_id: str, fuelix_file_id: str) -> Optional[str]:
    payload = _request_json(
        "POST",
        f"{_fuelix_base_url()}/vector_stores/{vector_store_id}/files",
        headers=_fuelix_headers(json_content=True),
        json_body={"file_id": fuelix_file_id},
    )
    attached_id = payload.get("id") if isinstance(payload, dict) else None
    return attached_id if isinstance(attached_id, str) else None


def _delete_fuelix_file(file_id: str) -> None:
    _request_json(
        "DELETE",
        f"{_fuelix_base_url()}/files/{file_id}",
        headers=_fuelix_headers(json_content=True),
    )


def _safe_filename(filename: str, fallback: str) -> str:
    cleaned = (filename or "").strip()
    if cleaned:
        return cleaned
    return f"{fallback}.bin"


def _migrate_file(
    item: Dict[str, Any],
    openai_vector_store_id: str,
    vector_store_id: Optional[str],
    *,
    dry_run: bool,
    existing_filenames: Optional[set[str]] = None,
) -> FileMigrationResult:
    openai_file_id = str(item.get("id") or "")
    status = str(item.get("status") or "")
    result = FileMigrationResult(openai_file_id=openai_file_id, openai_vector_store_status=status, dry_run=dry_run)

    if not openai_file_id:
        result.error = f"OpenAI vector store file item has no id: {item}"
        return result

    try:
        metadata = _openai_file_metadata(openai_file_id)
        result.filename = _safe_filename(str(metadata.get("filename") or ""), openai_file_id)
        result.uploaded_filename = result.filename
        expected_parsed_filename = _parsed_text_filename(result.filename, openai_file_id)
        existing = existing_filenames or set()

        if status and status != "completed":
            result.skipped = True
            result.error = f"Skipped OpenAI file with vector store status '{status}'."
            return result

        if result.filename in existing:
            result.ok = True
            result.skipped = True
            result.content_source = "existing_fuelix_file"
            result.error = "Skipped because the original filename already exists in the target Fuel IX store."
            return result

        if expected_parsed_filename in existing:
            result.ok = True
            result.skipped = True
            result.uploaded_filename = expected_parsed_filename
            result.content_source = "existing_fuelix_file"
            result.error = "Skipped because the parsed-content filename already exists in the target Fuel IX store."
            return result

        if dry_run:
            result.ok = True
            return result

        if not vector_store_id:
            raise MigrationError("No Fuel IX vector store id is available for upload.")

        upload_filename, content, content_source, content_type = _openai_file_for_upload(
            openai_vector_store_id,
            openai_file_id,
            result.filename,
        )
        result.uploaded_filename = upload_filename
        result.content_source = content_source
        result.fuelix_file_id = _upload_fuelix_file(upload_filename, content, content_type)

        try:
            result.fuelix_vector_store_file_id = _attach_fuelix_file(vector_store_id, result.fuelix_file_id)
        except MigrationError as exc:
            if "already exists in this knowledge base" in str(exc):
                _delete_fuelix_file(result.fuelix_file_id)
                result.ok = True
                result.skipped = True
                result.error = "Skipped because Fuel IX reported this filename already exists in the target store."
                return result
            try:
                _delete_fuelix_file(result.fuelix_file_id)
            except Exception as cleanup_exc:
                result.error = f"Attachment failed, and cleanup of uploaded file failed: {cleanup_exc}"
                raise
            raise

        result.ok = True
    except Exception as exc:
        result.error = str(exc)

    return result


def migrate_store(spec: StoreMigrationSpec, *, dry_run: bool) -> StoreMigrationResult:
    result = _resolve_fuelix_vector_store(spec, dry_run=dry_run)
    existing_filenames = _fuelix_attached_filenames(result.fuelix_vector_store_id) if not dry_run else set()

    try:
        openai_files = _openai_vector_store_files(spec.openai_vector_store_id)
    except Exception as exc:
        result.error = str(exc)
        return result

    for item in openai_files:
        file_result = _migrate_file(
            item,
            spec.openai_vector_store_id,
            result.fuelix_vector_store_id,
            dry_run=dry_run,
            existing_filenames=existing_filenames,
        )
        result.files.append(file_result)
        status = "ok" if file_result.ok else "failed"
        if file_result.skipped and not dry_run:
            status = "skipped"
        print(f"[{spec.fuelix_name}] {status}: {file_result.filename or file_result.openai_file_id}")
        sys.stdout.flush()

    return result


def _summary_counts(results: Iterable[StoreMigrationResult]) -> Dict[str, int]:
    stores = list(results)
    files = [file for store in stores for file in store.files]
    return {
        "stores": len(stores),
        "created_stores": sum(1 for store in stores if store.created_store),
        "reused_stores": sum(1 for store in stores if store.reused_existing_store),
        "files_total": len(files),
        "files_ok": sum(1 for file in files if file.ok),
        "files_failed": sum(1 for file in files if file.error and not file.skipped),
        "files_skipped": sum(1 for file in files if file.skipped),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _write_summary(results: List[StoreMigrationResult], *, dry_run: bool) -> Path:
    output = {
        "dry_run": dry_run,
        "created_at_unix": int(time.time()),
        "openai_vector_stores": [spec.openai_vector_store_id for spec in STORE_SPECS],
        "fuelix_product_id": os.getenv("FUELIX_PRODUCT_ID", "core").strip() or None,
        "counts": _summary_counts(results),
        "stores": [asdict(result) for result in results],
    }
    suffix = "dry-run" if dry_run else "executed"
    output_path = PROJECT_ROOT / "api" / f"openai_to_fuelix_vector_store_migration_{suffix}_{int(time.time())}.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate the configured OpenAI vector store files into matching Fuel IX vector stores.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create/reuse Fuel IX vector stores and upload files. Without this flag, only a dry run is performed.",
    )
    parser.add_argument(
        "--store",
        choices=[_slug(spec.fuelix_name) for spec in STORE_SPECS],
        action="append",
        help="Limit the migration to one store slug. Can be provided more than once.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env()
    dry_run = not args.execute
    requested_stores = set(args.store or [])
    specs = [spec for spec in STORE_SPECS if not requested_stores or _slug(spec.fuelix_name) in requested_stores]

    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"OpenAI -> Fuel IX vector store migration ({mode})")
    print(f"Fuel IX base URL: {_fuelix_base_url()}")
    print(f"Fuel IX product-id: {os.getenv('FUELIX_PRODUCT_ID', 'core').strip() or '(none)'}")

    results = [migrate_store(spec, dry_run=dry_run) for spec in specs]
    summary_path = _write_summary(results, dry_run=dry_run)
    counts = _summary_counts(results)

    print("\nSummary")
    for key, value in counts.items():
        print(f"{key}: {value}")
    print(f"summary_json: {summary_path}")

    return 1 if counts["files_failed"] or any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
