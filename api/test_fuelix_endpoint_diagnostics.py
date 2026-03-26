import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv


SUCCESS_CODES: Set[int] = {200, 201}


@dataclass
class ProbeResult:
    name: str
    method: str
    path: str
    status: Optional[int]
    ok: bool
    error: str = ""
    body_preview: str = ""


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")


def _base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", "https://api.fuelix.ai/v1").rstrip("/")


def _headers(json_content: bool = True) -> Dict[str, str]:
    token = os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY")
    if not token:
        raise RuntimeError("Missing Fuel IX API key. Set FUELIX_API_KEY in .env.")

    headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
    if json_content:
        headers["Content-Type"] = "application/json"

    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _extract_error(payload: Any) -> str:
    if isinstance(payload, dict):
        fault = payload.get("fault")
        if isinstance(fault, dict):
            fault_string = fault.get("faultstring")
            if isinstance(fault_string, str) and fault_string.strip():
                return fault_string.strip()

        for key in ("error", "message", "detail", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
    return ""


def _preview(payload: Any, max_chars: int = 220) -> str:
    try:
        raw = json.dumps(payload, ensure_ascii=False)
    except Exception:
        raw = str(payload)
    raw = raw.replace("\n", " ")
    return raw[:max_chars] + ("..." if len(raw) > max_chars else "")


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _request(
    name: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    accepted: Optional[Set[int]] = None,
    timeout_seconds: int = 90,
) -> Tuple[ProbeResult, Any]:
    url = f"{_base_url()}{path}"
    accepted_codes = accepted or SUCCESS_CODES

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_headers(json_content=True),
            params=params,
            json=json_body,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return (
            ProbeResult(
                name=name,
                method=method,
                path=path,
                status=None,
                ok=False,
                error=f"request failed: {exc}",
                body_preview="",
            ),
            {},
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    status = response.status_code
    ok = status in accepted_codes
    return (
        ProbeResult(
            name=name,
            method=method,
            path=path,
            status=status,
            ok=ok,
            error="" if ok else _extract_error(payload),
            body_preview=_preview(payload),
        ),
        payload,
    )


def _pick_first_id(payload: Any, field: str = "id") -> Optional[str]:
    for item in _extract_items(payload):
        value = item.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _poll_run(thread_id: str, run_id: str, max_attempts: int = 8, delay_seconds: float = 1.5) -> ProbeResult:
    terminal = {"completed", "failed", "cancelled", "expired", "incomplete"}
    last_result: Optional[ProbeResult] = None
    for _ in range(max_attempts):
        result, payload = _request(
            "Poll run",
            "GET",
            f"/threads/{thread_id}/runs/{run_id}",
            accepted={200},
            timeout_seconds=60,
        )
        last_result = result
        if not result.ok:
            return result
        status = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(status, str) and status in terminal:
            result.name = f"Poll run terminal ({status})"
            return result
        time.sleep(delay_seconds)
    if last_result is None:
        return ProbeResult("Poll run", "GET", f"/threads/{thread_id}/runs/{run_id}", None, False, "poll failed")
    last_result.name = "Poll run timeout"
    last_result.ok = False
    last_result.error = "run did not reach terminal state in polling window"
    return last_result


def run_diagnostics() -> List[ProbeResult]:
    results: List[ProbeResult] = []

    created_thread_ids: List[str] = []
    thread_id_for_run: Optional[str] = None
    assistant_id: Optional[str] = None

    # Core list endpoints
    list_models, payload_models = _request("List models", "GET", "/models")
    results.append(list_models)

    list_asst, payload_asst = _request("List assistants", "GET", "/assistants", params={"limit": 20, "order": "desc"})
    results.append(list_asst)
    assistant_id = _pick_first_id(payload_asst)

    list_vs, payload_vs = _request("List vector stores", "GET", "/vector_stores", params={"limit": 20, "order": "desc"})
    results.append(list_vs)
    vector_store_id = _pick_first_id(payload_vs)

    list_files, payload_files = _request("List files", "GET", "/files", params={"limit": 20})
    results.append(list_files)
    file_id = _pick_first_id(payload_files)

    list_threads, payload_threads = _request("List threads", "GET", "/threads", params={"limit": 20, "order": "desc"})
    results.append(list_threads)
    existing_thread_id = _pick_first_id(payload_threads)

    # Retrieve endpoints (if ids exist)
    if assistant_id:
        r, _ = _request("Retrieve assistant", "GET", f"/assistants/{assistant_id}")
        results.append(r)

    if vector_store_id:
        r, _ = _request("Retrieve vector store", "GET", f"/vector_stores/{vector_store_id}")
        results.append(r)
        r, _ = _request("List vector store files", "GET", f"/vector_stores/{vector_store_id}/files", params={"limit": 20})
        results.append(r)

    if file_id:
        r, _ = _request("Retrieve file", "GET", f"/files/{file_id}")
        results.append(r)

    if existing_thread_id:
        r, _ = _request("Retrieve existing thread", "GET", f"/threads/{existing_thread_id}")
        results.append(r)
        r, _ = _request("List existing thread messages", "GET", f"/threads/{existing_thread_id}/messages", params={"limit": 20, "order": "desc"})
        results.append(r)

    # Create thread + message flow
    create_thread, payload_create_thread = _request(
        "Create thread",
        "POST",
        "/threads",
        json_body={
            "messages": [{"role": "user", "content": "Endpoint diagnostic thread bootstrap."}],
            "metadata": {"diagnostic": "fuelix-endpoint-probe"},
        },
    )
    results.append(create_thread)
    if create_thread.ok and isinstance(payload_create_thread, dict):
        thread_id = payload_create_thread.get("id")
        if isinstance(thread_id, str) and thread_id:
            created_thread_ids.append(thread_id)
            thread_id_for_run = thread_id

            create_msg, payload_msg = _request(
                "Create message",
                "POST",
                f"/threads/{thread_id}/messages",
                json_body={"role": "user", "content": "Add a follow-up test message."},
            )
            results.append(create_msg)
            if create_msg.ok and isinstance(payload_msg, dict):
                message_id = payload_msg.get("id")
                if isinstance(message_id, str) and message_id:
                    r, _ = _request("Retrieve message", "GET", f"/threads/{thread_id}/messages/{message_id}")
                    results.append(r)

            r, _ = _request("List messages", "GET", f"/threads/{thread_id}/messages", params={"limit": 20, "order": "desc"})
            results.append(r)

    # Run flow (likely to surface quota/rate-limit issues)
    if assistant_id:
        run_create, payload_run = _request(
            "Create thread run",
            "POST",
            "/threads/runs",
            json_body={
                "assistant_id": assistant_id,
                "thread": {
                    "messages": [
                        {"role": "user", "content": "Reply in one sentence: this is a diagnostics check."}
                    ]
                },
            },
            timeout_seconds=120,
        )
        results.append(run_create)

        if run_create.ok and isinstance(payload_run, dict):
            run_id = payload_run.get("id")
            run_thread_id = payload_run.get("thread_id")
            if isinstance(run_id, str) and isinstance(run_thread_id, str):
                created_thread_ids.append(run_thread_id)
                poll_result = _poll_run(run_thread_id, run_id)
                results.append(poll_result)
                r, _ = _request(
                    "List run thread messages",
                    "GET",
                    f"/threads/{run_thread_id}/messages",
                    params={"limit": 20, "order": "desc"},
                )
                results.append(r)

    # Cleanup created threads
    for idx, tid in enumerate(dict.fromkeys(created_thread_ids), start=1):
        r, _ = _request(
            f"Delete thread #{idx}",
            "DELETE",
            f"/threads/{tid}",
            accepted={200, 400, 404},
            timeout_seconds=60,
        )
        results.append(r)

    return results


def main() -> int:
    _load_env()
    results = run_diagnostics()

    print("\nFuel IX Endpoint Diagnostics\n")
    for r in results:
        state = "PASS" if r.ok else "FAIL"
        status = "none" if r.status is None else str(r.status)
        err = f" | error={r.error}" if r.error else ""
        print(f"[{state}] {r.name:26} {r.method:6} {r.path:40} status={status}{err}")

    failed = [r for r in results if not r.ok]
    print(f"\nSummary: total={len(results)} failed={len(failed)}")

    if failed:
        print("\nFailed Endpoints:")
        for r in failed:
            status = "none" if r.status is None else str(r.status)
            print(f"- {r.method} {r.path} | status={status} | error={r.error}")

    print("\nJSON:")
    print(json.dumps([asdict(r) for r in results], indent=2))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
