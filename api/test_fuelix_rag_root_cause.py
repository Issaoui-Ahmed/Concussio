import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv


TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "expired", "incomplete"}


@dataclass
class CallResult:
    name: str
    method: str
    path: str
    status: Optional[int]
    ok: bool
    note: str = ""
    body: Any = None


def _load_env() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", "https://api.fuelix.ai/v1").rstrip("/")


def _headers(json_content: bool = True) -> Dict[str, str]:
    token = os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY")
    if not token:
        raise RuntimeError("Missing Fuel IX API key in environment.")
    headers: Dict[str, str] = {"Authorization": f"Bearer {token}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _note_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("fault"), dict):
        fault = payload["fault"].get("faultstring")
        if isinstance(fault, str) and fault.strip():
            return fault.strip()
    for key in ("error", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _request(
    name: str,
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    accepted: Optional[set[int]] = None,
) -> CallResult:
    url = f"{_base_url()}{path}"
    use_json_headers = files is None
    headers = _headers(json_content=use_json_headers)
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            files=files,
            data=data,
            timeout=120,
        )
    except requests.RequestException as exc:
        return CallResult(name=name, method=method, path=path, status=None, ok=False, note=str(exc), body={})

    try:
        body: Any = response.json()
    except ValueError:
        body = {"raw": response.text}

    accepted_codes = accepted or {200, 201}
    return CallResult(
        name=name,
        method=method,
        path=path,
        status=response.status_code,
        ok=response.status_code in accepted_codes,
        note=_note_from_payload(body),
        body=body,
    )


def _extract_list_data(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    return []


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in {"authorization", "proxykey", "token", "api_key"}:
                sanitized[key] = "***REDACTED***"
                continue
            sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _poll_run(thread_id: str, run_id: str, max_attempts: int = 25, delay: float = 2.0) -> CallResult:
    last_result: Optional[CallResult] = None
    for _ in range(max_attempts):
        result = _request(
            "Poll run status",
            "GET",
            f"/threads/{thread_id}/runs/{run_id}",
        )
        last_result = result
        if result.status not in (200, 201):
            return result
        status = result.body.get("status") if isinstance(result.body, dict) else None
        if isinstance(status, str) and status in TERMINAL_RUN_STATES:
            return result
        time.sleep(delay)
    return last_result or CallResult("Poll run status", "GET", f"/threads/{thread_id}/runs/{run_id}", None, False)


def _print_result(result: CallResult) -> None:
    state = "PASS" if result.ok else "FAIL"
    status = "none" if result.status is None else str(result.status)
    suffix = f" | {result.note}" if result.note else ""
    print(f"[{state}] {result.name:34} {result.method:6} {result.path:46} status={status}{suffix}")


def main() -> int:
    _load_env()
    results: list[CallResult] = []

    created_file_id: Optional[str] = None
    created_vector_store_id: Optional[str] = None
    created_assistant_id: Optional[str] = None
    doc_thread_id: Optional[str] = None
    doc_run_id: Optional[str] = None
    cancel_thread_id: Optional[str] = None
    cancel_run_id: Optional[str] = None
    rag_blocked_reason: Optional[str] = None

    temp_path = Path(__file__).resolve().parent / f"fuelix_rag_e2e_{int(time.time())}.txt"
    temp_path.write_text(
        "Concussio RAG Smoke Doc\n"
        "Unique marker: RAG_ROOT_CAUSE_7391.\n"
        "If asked for the marker, answer exactly: RAG_ROOT_CAUSE_7391.\n",
        encoding="utf-8",
    )

    with temp_path.open("rb") as file_handle:
        upload = _request(
            "Upload RAG file",
            "POST",
            "/files",
            files={"file": (temp_path.name, file_handle, "text/plain")},
            data={"purpose": "assistants", "alias_id": f"alias-rag-{int(time.time())}"},
        )
    results.append(upload)
    if isinstance(upload.body, dict):
        file_id = upload.body.get("id")
        if isinstance(file_id, str) and file_id:
            created_file_id = file_id

    list_files = _request("List files", "GET", "/files")
    results.append(list_files)

    if created_file_id:
        retrieve_file = _request("Retrieve uploaded file", "GET", f"/files/{created_file_id}")
        results.append(retrieve_file)

    create_store = _request(
        "Create vector store",
        "POST",
        "/vector_stores",
        json_body={"name": f"RAG Root Cause Store {int(time.time())}", "metadata": {"test": "rag-root-cause"}},
    )
    results.append(create_store)
    if isinstance(create_store.body, dict):
        vs_id = create_store.body.get("id")
        if isinstance(vs_id, str) and vs_id:
            created_vector_store_id = vs_id

    if created_vector_store_id and created_file_id:
        attach = _request(
            "Attach file to vector store",
            "POST",
            f"/vector_stores/{created_vector_store_id}/files",
            json_body={"file_id": created_file_id},
        )
        results.append(attach)

        list_vs_files = _request("List vector store files", "GET", f"/vector_stores/{created_vector_store_id}/files")
        results.append(list_vs_files)

        retrieve_vs_file = _request(
            "Retrieve vector store file",
            "GET",
            f"/vector_stores/{created_vector_store_id}/files/{created_file_id}",
        )
        results.append(retrieve_vs_file)

        # Wait for indexing to finish before RAG run.
        for _ in range(20):
            status = (
                retrieve_vs_file.body.get("status")
                if isinstance(retrieve_vs_file.body, dict)
                else None
            )
            if status == "completed":
                break
            time.sleep(2)
            retrieve_vs_file = _request(
                "Poll vector store file",
                "GET",
                f"/vector_stores/{created_vector_store_id}/files/{created_file_id}",
            )
            results.append(retrieve_vs_file)

        create_assistant = _request(
            "Create RAG assistant",
            "POST",
            "/assistants",
            json_body={
                "name": f"RAG Root Cause Asst {int(time.time())}",
                "description": "Assistant for RAG endpoint diagnostics.",
                "model": "claude-sonnet-4-5",
                "instructions": (
                    "Use file_search results first. If the user asks for a marker in docs, return it verbatim."
                ),
                "tools": [],
                "tool_resources": {"file_search": {"vector_store_ids": [created_vector_store_id]}},
            },
        )
        results.append(create_assistant)
        if isinstance(create_assistant.body, dict):
            asst = create_assistant.body.get("id")
            if isinstance(asst, str) and asst:
                created_assistant_id = asst
        if not created_assistant_id:
            rag_blocked_reason = (
                create_assistant.note
                or (
                    "; ".join(create_assistant.body.get("detail", []))
                    if isinstance(create_assistant.body, dict)
                    and isinstance(create_assistant.body.get("detail"), list)
                    else "RAG assistant creation failed."
                )
            )
            fallback_assistant = _request(
                "Create fallback assistant",
                "POST",
                "/assistants",
                json_body={
                    "name": f"Fallback Asst {int(time.time())}",
                    "description": "Fallback assistant to continue endpoint diagnostics.",
                    "model": "claude-sonnet-4-5",
                    "instructions": "Respond briefly.",
                    "tools": [],
                },
            )
            results.append(fallback_assistant)
            if isinstance(fallback_assistant.body, dict):
                fallback_id = fallback_assistant.body.get("id")
                if isinstance(fallback_id, str) and fallback_id:
                    created_assistant_id = fallback_id

    # Probe create-message path independently from run creation.
    thread_probe = _request(
        "Create thread for message probe",
        "POST",
        "/threads",
        json_body={
            "messages": [{"role": "user", "content": "initial message"}],
            "metadata": {"probe": "message-path"},
        },
    )
    results.append(thread_probe)
    probe_thread_id = (
        thread_probe.body.get("id")
        if isinstance(thread_probe.body, dict) and isinstance(thread_probe.body.get("id"), str)
        else None
    )
    if probe_thread_id:
        probe_doc_path = _request(
            "Probe doc create-message path",
            "POST",
            f"/threads/{probe_thread_id}/messages/msg-probe-1",
            json_body={"role": "user", "content": "probe"},
            accepted={404},
        )
        results.append(probe_doc_path)
        probe_real_path = _request(
            "Probe working create-message path",
            "POST",
            f"/threads/{probe_thread_id}/messages",
            json_body={"role": "user", "content": "probe"},
        )
        results.append(probe_real_path)
    else:
        results.append(
            CallResult(
                name="Probe doc create-message path",
                method="POST",
                path="/threads/{threadId}/messages/{messageId}",
                status=None,
                ok=False,
                note="message probe thread creation failed",
                body={},
            )
        )
        results.append(
            CallResult(
                name="Probe working create-message path",
                method="POST",
                path="/threads/{threadId}/messages",
                status=None,
                ok=False,
                note="message probe thread creation failed",
                body={},
            )
        )

    if created_assistant_id:
        run_create = _request(
            "Create thread+run (RAG)",
            "POST",
            "/threads/runs",
            json_body={
                "assistant_id": created_assistant_id,
                "model": "claude-sonnet-4-5",
                "thread": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "What is the unique marker in the uploaded document?",
                        }
                    ]
                },
            },
        )
        results.append(run_create)
        if isinstance(run_create.body, dict):
            run_id = run_create.body.get("id")
            thread_id = run_create.body.get("thread_id")
            if isinstance(run_id, str):
                doc_run_id = run_id
            if isinstance(thread_id, str):
                doc_thread_id = thread_id

    if doc_thread_id and doc_run_id:
        run_final = _poll_run(doc_thread_id, doc_run_id)
        run_final.name = "Wait run terminal state"
        results.append(run_final)

        list_messages = _request("List run thread messages", "GET", f"/threads/{doc_thread_id}/messages")
        results.append(list_messages)

    if created_assistant_id:
        # Root-cause probe #2: cancel run behavior by trying immediate cancel.
        cancel_seed = _request(
            "Create run for cancel probe",
            "POST",
            "/threads/runs",
            json_body={
                "assistant_id": created_assistant_id,
                "model": "claude-sonnet-4-5",
                "thread": {"messages": [{"role": "user", "content": "write one short sentence"}]},
            },
        )
        results.append(cancel_seed)
        if isinstance(cancel_seed.body, dict):
            rid = cancel_seed.body.get("id")
            tid = cancel_seed.body.get("thread_id")
            if isinstance(rid, str):
                cancel_run_id = rid
            if isinstance(tid, str):
                cancel_thread_id = tid

        if cancel_thread_id and cancel_run_id:
            current = _request("Retrieve cancel probe run", "GET", f"/threads/{cancel_thread_id}/runs/{cancel_run_id}")
            results.append(current)
            current_status = current.body.get("status") if isinstance(current.body, dict) else None
            cancel_call = _request(
                "Cancel probe run",
                "POST",
                f"/threads/{cancel_thread_id}/runs/{cancel_run_id}/cancel",
                accepted={200, 400},
            )
            if current_status:
                cancel_call.note = (cancel_call.note + " | " if cancel_call.note else "") + f"run_status_before_cancel={current_status}"
            results.append(cancel_call)

    # Root-cause probe #3 and #4 around delete thread/file.
    if cancel_thread_id:
        delete_cancel_thread = _request(
            "Delete cancel thread (early)",
            "DELETE",
            f"/threads/{cancel_thread_id}",
            accepted={200, 400, 404},
        )
        results.append(delete_cancel_thread)
        if delete_cancel_thread.status in (400, 423):
            run_now = (
                _request("Retrieve run after delete fail", "GET", f"/threads/{cancel_thread_id}/runs/{cancel_run_id}")
                if cancel_run_id
                else None
            )
            if run_now:
                results.append(run_now)

    if created_vector_store_id and created_file_id:
        remove_vs_file = _request(
            "Remove file from vector store",
            "DELETE",
            f"/vector_stores/{created_vector_store_id}/files/{created_file_id}",
            accepted={200, 404},
        )
        results.append(remove_vs_file)

    if created_file_id:
        file_before_delete = _request("Retrieve file before final delete", "GET", f"/files/{created_file_id}", accepted={200, 404})
        results.append(file_before_delete)

    # Cleanup
    if doc_thread_id:
        results.append(_request("Delete RAG thread", "DELETE", f"/threads/{doc_thread_id}", accepted={200, 400, 404}))
    if probe_thread_id:
        results.append(_request("Delete message probe thread", "DELETE", f"/threads/{probe_thread_id}", accepted={200, 400, 404}))
    if created_assistant_id:
        results.append(_request("Delete RAG assistant", "DELETE", f"/assistants/{created_assistant_id}", accepted={200, 404}))
    if created_vector_store_id:
        results.append(_request("Delete vector store", "DELETE", f"/vector_stores/{created_vector_store_id}", accepted={200, 404}))
    if created_file_id:
        results.append(_request("Delete uploaded file", "DELETE", f"/files/{created_file_id}", accepted={200, 404}))

    print("\nFuel IX RAG E2E Root-Cause Test\n")
    for item in results:
        _print_result(item)

    print("\nKey IDs:")
    print(
        json.dumps(
            {
                "file_id": created_file_id,
                "vector_store_id": created_vector_store_id,
                "assistant_id": created_assistant_id,
                "rag_thread_id": doc_thread_id,
                "rag_run_id": doc_run_id,
                "cancel_thread_id": cancel_thread_id,
                "cancel_run_id": cancel_run_id,
                "rag_blocked_reason": rag_blocked_reason,
            },
            indent=2,
        )
    )

    summary = [
        {
            "name": r.name,
            "status": r.status,
            "ok": r.ok,
            "note": r.note,
            "body": _sanitize(r.body) if isinstance(r.body, dict) else {},
        }
        for r in results
    ]
    print("\nJSON summary:")
    print(json.dumps(summary, indent=2))

    failed = [r for r in results if not r.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
