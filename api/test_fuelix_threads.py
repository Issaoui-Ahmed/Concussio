import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "expired", "incomplete"}


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    status: Optional[int]
    ok: bool
    skipped: bool = False
    note: str = ""


def _load_environment() -> None:
    root_env = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(root_env)


def _base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", "https://api.fuelix.ai/v1").rstrip("/")


def _headers() -> Dict[str, str]:
    token = os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY")
    if not token:
        raise RuntimeError("Missing Fuel IX API key. Set FUELIX_API_KEY in .env.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _extract_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    if isinstance(payload, list):
        return payload
    return []


def _payload_note(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "detail", "fault"):
            value = payload.get(key)
            if key == "fault" and isinstance(value, dict):
                fault_string = value.get("faultstring")
                if isinstance(fault_string, str) and fault_string.strip():
                    return fault_string.strip()
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _request(
    method: str,
    path: str,
    *,
    headers: Dict[str, str],
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[int], Any, str]:
    url = f"{_base_url()}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=90,
        )
    except requests.RequestException as exc:
        return None, {}, f"request failed: {exc}"

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    note = _payload_note(payload)
    return response.status_code, payload, note


def _request_multipart(
    method: str,
    path: str,
    *,
    headers: Dict[str, str],
    form_data: Dict[str, Any],
    file_path: Path,
    field_name: str = "file",
) -> tuple[Optional[int], Any, str]:
    url = f"{_base_url()}{path}"
    multipart_headers = dict(headers)
    multipart_headers.pop("Content-Type", None)
    try:
        with file_path.open("rb") as file_handle:
            response = requests.request(
                method=method,
                url=url,
                headers=multipart_headers,
                data=form_data,
                files={field_name: (file_path.name, file_handle, "text/plain")},
                timeout=90,
            )
    except requests.RequestException as exc:
        return None, {}, f"request failed: {exc}"

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    note = _payload_note(payload)
    return response.status_code, payload, note


def _record_result(
    results: List[StepResult],
    *,
    name: str,
    method: str,
    path: str,
    status: Optional[int],
    note: str = "",
    skipped: bool = False,
    accepted_statuses: Optional[set[int]] = None,
) -> None:
    if skipped:
        results.append(
            StepResult(name=name, method=method, path=path, status=None, ok=False, skipped=True, note=note)
        )
        return

    accepted = accepted_statuses if accepted_statuses is not None else {200, 201}
    ok = status in accepted
    results.append(
        StepResult(name=name, method=method, path=path, status=status, ok=ok, skipped=False, note=note)
    )


def _resolve_assistant_id(headers: Dict[str, str]) -> Optional[str]:
    explicit = os.getenv("FUELIX_ASSISTANT_ID", "").strip()
    if explicit:
        return explicit

    status, payload, _ = _request("GET", "/assistants", headers=headers, params={"limit": 1})
    if status not in (200, 201):
        return None
    items = _extract_list(payload)
    if not items:
        return None
    assistant_id = items[0].get("id")
    return assistant_id if isinstance(assistant_id, str) and assistant_id else None


def _extract_run_and_thread_ids(payload: Any) -> tuple[Optional[str], Optional[str]]:
    run_id: Optional[str] = None
    thread_id: Optional[str] = None

    if not isinstance(payload, dict):
        return run_id, thread_id

    run_obj = payload.get("run")
    if isinstance(run_obj, dict):
        candidate = run_obj.get("id")
        if isinstance(candidate, str) and candidate:
            run_id = candidate
        thread_candidate = run_obj.get("thread_id")
        if isinstance(thread_candidate, str) and thread_candidate:
            thread_id = thread_candidate

    thread_obj = payload.get("thread")
    if isinstance(thread_obj, dict) and not thread_id:
        candidate = thread_obj.get("id")
        if isinstance(candidate, str) and candidate:
            thread_id = candidate

    payload_id = payload.get("id")
    payload_object = payload.get("object")
    payload_thread_id = payload.get("thread_id")
    if (
        isinstance(payload_object, str)
        and payload_object == "thread.run"
        and isinstance(payload_id, str)
        and payload_id
    ):
        run_id = run_id or payload_id
        if isinstance(payload_thread_id, str) and payload_thread_id:
            thread_id = thread_id or payload_thread_id

    return run_id, thread_id


def _wait_for_terminal_run(
    thread_id: str,
    run_id: str,
    headers: Dict[str, str],
    max_attempts: int = 15,
    delay_seconds: float = 2.0,
) -> None:
    for _ in range(max_attempts):
        status, payload, _ = _request(
            "GET",
            f"/threads/{thread_id}/runs/{run_id}",
            headers=headers,
        )
        if status is not None and status >= 500:
            time.sleep(delay_seconds)
            continue
        if status not in (200, 201):
            return
        run_status = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(run_status, str) and run_status in TERMINAL_RUN_STATES:
            return
        time.sleep(delay_seconds)


def main() -> int:
    _load_environment()
    headers = _headers()
    results: List[StepResult] = []

    primary_thread_id: Optional[str] = None
    primary_message_id: Optional[str] = None
    run_thread_id: Optional[str] = None
    run_id: Optional[str] = None
    run_step_id: Optional[str] = None
    cancel_thread_id: Optional[str] = None
    cancel_run_id: Optional[str] = None
    created_copilot_id: Optional[str] = None
    created_file_id: Optional[str] = None
    created_vector_store_id: Optional[str] = None
    vector_store_file_record_id: Optional[str] = None

    status, payload, note = _request(
        "GET",
        "/models",
        headers=headers,
    )
    _record_result(
        results,
        name="List models",
        method="GET",
        path="/models",
        status=status,
        note=note,
    )

    status, payload, note = _request(
        "GET",
        "/assistants",
        headers=headers,
        params={"limit": 20, "order": "desc"},
    )
    _record_result(
        results,
        name="List copilots",
        method="GET",
        path="/assistants",
        status=status,
        note=note,
    )

    copilot_name = f"Concussio Smoke Copilot {int(time.time())}"
    status, payload, note = _request(
        "POST",
        "/assistants",
        headers=headers,
        json_body={
            "name": copilot_name,
            "description": "Temporary assistant for endpoint smoke testing.",
            "model": "claude-sonnet-4-5",
            "instructions": "Reply briefly to smoke-test prompts.",
            "tools": [],
        },
    )
    _record_result(
        results,
        name="Create copilot",
        method="POST",
        path="/assistants",
        status=status,
        note=note,
    )
    if isinstance(payload, dict):
        candidate = payload.get("id")
        if isinstance(candidate, str) and candidate:
            created_copilot_id = candidate

    if created_copilot_id:
        status, _, note = _request("GET", f"/assistants/{created_copilot_id}", headers=headers)
        _record_result(
            results,
            name="Retrieve copilot",
            method="GET",
            path="/assistants/{id}",
            status=status,
            note=note,
        )

        status, _, note = _request(
            "POST",
            f"/assistants/{created_copilot_id}",
            headers=headers,
            json_body={
                "name": f"{copilot_name} v2",
                "instructions": "Reply briefly and include the word updated.",
                "model": "claude-sonnet-4-5",
            },
        )
        _record_result(
            results,
            name="Update copilot",
            method="POST",
            path="/assistants/{id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Retrieve copilot",
            method="GET",
            path="/assistants/{id}",
            status=None,
            skipped=True,
            note="copilot creation failed",
        )
        _record_result(
            results,
            name="Update copilot",
            method="POST",
            path="/assistants/{id}",
            status=None,
            skipped=True,
            note="copilot creation failed",
        )

    temp_file_path = Path(__file__).resolve().parent / f"fuelix_smoke_{int(time.time())}.txt"
    temp_file_path.write_text("Fuel IX file endpoint smoke test.\n", encoding="utf-8")
    try:
        status, payload, note = _request_multipart(
            "POST",
            "/files",
            headers=headers,
            form_data={
                "purpose": "assistants",
                "alias_id": f"alias-smoke-{int(time.time())}",
            },
            file_path=temp_file_path,
        )
    finally:
        if temp_file_path.exists():
            temp_file_path.unlink()

    _record_result(
        results,
        name="Upload file",
        method="POST",
        path="/files",
        status=status,
        note=note,
    )
    if isinstance(payload, dict):
        candidate = payload.get("id")
        if isinstance(candidate, str) and candidate:
            created_file_id = candidate

    status, _, note = _request("GET", "/files", headers=headers)
    _record_result(
        results,
        name="List files",
        method="GET",
        path="/files",
        status=status,
        note=note,
    )

    if created_file_id:
        status, _, note = _request("GET", f"/files/{created_file_id}", headers=headers)
        _record_result(
            results,
            name="Retrieve file",
            method="GET",
            path="/files/{id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Retrieve file",
            method="GET",
            path="/files/{id}",
            status=None,
            skipped=True,
            note="file upload failed",
        )

    status, payload, note = _request(
        "POST",
        "/vector_stores",
        headers=headers,
        json_body={
            "name": f"Concussio Smoke Store {int(time.time())}",
            "metadata": {"source": "smoke-test"},
        },
    )
    _record_result(
        results,
        name="Create vector store",
        method="POST",
        path="/vector_stores",
        status=status,
        note=note,
    )
    if isinstance(payload, dict):
        candidate = payload.get("id")
        if isinstance(candidate, str) and candidate:
            created_vector_store_id = candidate

    status, _, note = _request("GET", "/vector_stores", headers=headers)
    _record_result(
        results,
        name="List vector stores",
        method="GET",
        path="/vector_stores",
        status=status,
        note=note,
    )

    if created_vector_store_id:
        status, _, note = _request("GET", f"/vector_stores/{created_vector_store_id}", headers=headers)
        _record_result(
            results,
            name="Retrieve vector store",
            method="GET",
            path="/vector_stores/{id}",
            status=status,
            note=note,
        )

        status, _, note = _request(
            "POST",
            f"/vector_stores/{created_vector_store_id}",
            headers=headers,
            json_body={"name": f"Updated Smoke Store {int(time.time())}"},
        )
        _record_result(
            results,
            name="Update vector store",
            method="POST",
            path="/vector_stores/{id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Retrieve vector store",
            method="GET",
            path="/vector_stores/{id}",
            status=None,
            skipped=True,
            note="vector store creation failed",
        )
        _record_result(
            results,
            name="Update vector store",
            method="POST",
            path="/vector_stores/{id}",
            status=None,
            skipped=True,
            note="vector store creation failed",
        )

    if created_vector_store_id and created_file_id:
        status, _, note = _request(
            "POST",
            f"/vector_stores/{created_vector_store_id}/files",
            headers=headers,
            json_body={"file_id": created_file_id},
        )
        _record_result(
            results,
            name="Add file to vector store",
            method="POST",
            path="/vector_stores/{id}/files",
            status=status,
            note=note,
        )

        status, payload, note = _request(
            "GET",
            f"/vector_stores/{created_vector_store_id}/files",
            headers=headers,
        )
        _record_result(
            results,
            name="List vector store files",
            method="GET",
            path="/vector_stores/{id}/files",
            status=status,
            note=note,
        )
        if isinstance(payload, dict):
            items = _extract_list(payload)
            if items:
                candidate = items[0].get("id")
                if isinstance(candidate, str) and candidate:
                    vector_store_file_record_id = candidate

        retrieve_id = vector_store_file_record_id or created_file_id
        status, _, note = _request(
            "GET",
            f"/vector_stores/{created_vector_store_id}/files/{retrieve_id}",
            headers=headers,
        )
        _record_result(
            results,
            name="Retrieve vector store file",
            method="GET",
            path="/vector_stores/{id}/files/{file_id}",
            status=status,
            note=note,
        )

        status, _, note = _request(
            "DELETE",
            f"/vector_stores/{created_vector_store_id}/files/{retrieve_id}",
            headers=headers,
        )
        _record_result(
            results,
            name="Remove vector store file",
            method="DELETE",
            path="/vector_stores/{id}/files/{file_id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Add file to vector store",
            method="POST",
            path="/vector_stores/{id}/files",
            status=None,
            skipped=True,
            note="vector store or file id unavailable",
        )
        _record_result(
            results,
            name="List vector store files",
            method="GET",
            path="/vector_stores/{id}/files",
            status=None,
            skipped=True,
            note="vector store or file id unavailable",
        )
        _record_result(
            results,
            name="Retrieve vector store file",
            method="GET",
            path="/vector_stores/{id}/files/{file_id}",
            status=None,
            skipped=True,
            note="vector store or file id unavailable",
        )
        _record_result(
            results,
            name="Remove vector store file",
            method="DELETE",
            path="/vector_stores/{id}/files/{file_id}",
            status=None,
            skipped=True,
            note="vector store or file id unavailable",
        )

    status, payload, note = _request(
        "POST",
        "/threads",
        headers=headers,
        json_body={
            "messages": [{"role": "user", "content": "Ping from Concussio Fuel IX smoke test."}],
            "metadata": {"channel": "smoke-test"},
        },
    )
    _record_result(
        results,
        name="Create thread",
        method="POST",
        path="/threads",
        status=status,
        note=note,
    )
    if isinstance(payload, dict):
        thread_id = payload.get("id")
        if isinstance(thread_id, str) and thread_id:
            primary_thread_id = thread_id

    status, _, note = _request("GET", "/threads", headers=headers, params={"limit": 20, "order": "desc"})
    _record_result(
        results,
        name="List threads",
        method="GET",
        path="/threads",
        status=status,
        note=note,
    )

    if primary_thread_id:
        status, _, note = _request(
            "POST",
            f"/threads/{primary_thread_id}",
            headers=headers,
            json_body={"metadata": {"channel": "smoke-test", "priority": "high"}},
        )
        _record_result(
            results,
            name="Update thread",
            method="POST",
            path="/threads/{threadId}",
            status=status,
            note=note,
        )

        status, _, note = _request("GET", f"/threads/{primary_thread_id}", headers=headers)
        _record_result(
            results,
            name="Retrieve thread",
            method="GET",
            path="/threads/{threadId}",
            status=status,
            note=note,
        )

        status, payload, note = _request(
            "POST",
            f"/threads/{primary_thread_id}/messages",
            headers=headers,
            json_body={
                "role": "user",
                "content": "Message creation smoke-test payload.",
            },
        )
        _record_result(
            results,
            name="Create message",
            method="POST",
            path="/threads/{threadId}/messages",
            status=status,
            note=note,
        )

        if isinstance(payload, dict):
            message_id = payload.get("id")
            if isinstance(message_id, str) and message_id:
                primary_message_id = message_id

        status, payload, note = _request("GET", f"/threads/{primary_thread_id}/messages", headers=headers)
        _record_result(
            results,
            name="List messages",
            method="GET",
            path="/threads/{threadId}/messages",
            status=status,
            note=note,
        )
        if not primary_message_id:
            items = _extract_list(payload)
            if items:
                candidate = items[0].get("id")
                if isinstance(candidate, str) and candidate:
                    primary_message_id = candidate

        if primary_message_id:
            status, _, note = _request(
                "GET",
                f"/threads/{primary_thread_id}/messages/{primary_message_id}",
                headers=headers,
            )
            _record_result(
                results,
                name="Retrieve message",
                method="GET",
                path="/threads/{threadId}/messages/{messageId}",
                status=status,
                note=note,
            )
        else:
            _record_result(
                results,
                name="Retrieve message",
                method="GET",
                path="/threads/{threadId}/messages/{messageId}",
                status=None,
                skipped=True,
                note="no message id was created or returned by list",
            )
    else:
        _record_result(
            results,
            name="Update thread",
            method="POST",
            path="/threads/{threadId}",
            status=None,
            skipped=True,
            note="thread creation failed",
        )
        _record_result(
            results,
            name="Retrieve thread",
            method="GET",
            path="/threads/{threadId}",
            status=None,
            skipped=True,
            note="thread creation failed",
        )
        _record_result(
            results,
            name="Create message",
            method="POST",
            path="/threads/{threadId}/messages",
            status=None,
            skipped=True,
            note="thread creation failed",
        )
        _record_result(
            results,
            name="List messages",
            method="GET",
            path="/threads/{threadId}/messages",
            status=None,
            skipped=True,
            note="thread creation failed",
        )
        _record_result(
            results,
            name="Retrieve message",
            method="GET",
            path="/threads/{threadId}/messages/{messageId}",
            status=None,
            skipped=True,
            note="thread or message id unavailable",
        )

    assistant_id = created_copilot_id or _resolve_assistant_id(headers)
    if assistant_id:
        status, payload, note = _request(
            "POST",
            "/threads/runs",
            headers=headers,
            json_body={
                "assistant_id": assistant_id,
                "thread": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Give a one-line summary of concussion return-to-play guidance.",
                        }
                    ]
                },
                "model": "claude-sonnet-4-5",
            },
        )
        _record_result(
            results,
            name="Create thread + run",
            method="POST",
            path="/threads/runs",
            status=status,
            note=note,
        )
        extracted_run_id, extracted_thread_id = _extract_run_and_thread_ids(payload)
        run_id = extracted_run_id
        run_thread_id = extracted_thread_id

        if run_thread_id:
            status, _, note = _request("GET", f"/threads/{run_thread_id}/runs", headers=headers)
            _record_result(
                results,
                name="List runs",
                method="GET",
                path="/threads/{threadId}/runs",
                status=status,
                note=note,
            )
        else:
            _record_result(
                results,
                name="List runs",
                method="GET",
                path="/threads/{threadId}/runs",
                status=None,
                skipped=True,
                note="run thread id unavailable",
            )

        if run_thread_id and run_id:
            status, _, note = _request("GET", f"/threads/{run_thread_id}/runs/{run_id}", headers=headers)
            _record_result(
                results,
                name="Retrieve run",
                method="GET",
                path="/threads/{threadId}/runs/{runId}",
                status=status,
                note=note,
            )
            _wait_for_terminal_run(run_thread_id, run_id, headers)
        else:
            _record_result(
                results,
                name="Retrieve run",
                method="GET",
                path="/threads/{threadId}/runs/{runId}",
                status=None,
                skipped=True,
                note="run id unavailable",
            )

        if run_thread_id and run_id:
            status, payload, note = _request(
                "GET",
                f"/threads/{run_thread_id}/runs/{run_id}/steps",
                headers=headers,
            )
            _record_result(
                results,
                name="List run steps",
                method="GET",
                path="/threads/{threadId}/runs/{runId}/steps",
                status=status,
                note=note,
            )
            steps = _extract_list(payload)
            if steps:
                candidate = steps[0].get("id")
                if isinstance(candidate, str) and candidate:
                    run_step_id = candidate
        else:
            _record_result(
                results,
                name="List run steps",
                method="GET",
                path="/threads/{threadId}/runs/{runId}/steps",
                status=None,
                skipped=True,
                note="run id unavailable",
            )

        if run_thread_id and run_id and run_step_id:
            status, _, note = _request(
                "GET",
                f"/threads/{run_thread_id}/runs/{run_id}/steps/{run_step_id}",
                headers=headers,
            )
            _record_result(
                results,
                name="Retrieve run step",
                method="GET",
                path="/threads/{threadId}/runs/{runId}/steps/{stepId}",
                status=status,
                note=note,
            )
        else:
            _record_result(
                results,
                name="Retrieve run step",
                method="GET",
                path="/threads/{threadId}/runs/{runId}/steps/{stepId}",
                status=None,
                skipped=True,
                note="step id unavailable",
            )

        status, payload, note = _request(
            "POST",
            "/threads/runs",
            headers=headers,
            json_body={
                "assistant_id": assistant_id,
                "thread": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Start another run for cancel endpoint smoke-test.",
                        }
                    ]
                },
                "model": "claude-sonnet-4-5",
            },
        )
        cancel_run_id, cancel_thread_id = _extract_run_and_thread_ids(payload)

        if cancel_thread_id and cancel_run_id:
            status, _, note = _request(
                "POST",
                f"/threads/{cancel_thread_id}/runs/{cancel_run_id}/cancel",
                headers=headers,
            )
            _record_result(
                results,
                name="Cancel run",
                method="POST",
                path="/threads/{threadId}/runs/{runId}/cancel",
                status=status,
                note=note or "400 can occur when run is not in a cancellable state yet.",
                accepted_statuses={200, 400},
            )
        else:
            _record_result(
                results,
                name="Cancel run",
                method="POST",
                path="/threads/{threadId}/runs/{runId}/cancel",
                status=None,
                skipped=True,
                note="cancel run ids unavailable",
            )
    else:
        for name, method, path in [
            ("Create thread + run", "POST", "/threads/runs"),
            ("List runs", "GET", "/threads/{threadId}/runs"),
            ("Retrieve run", "GET", "/threads/{threadId}/runs/{runId}"),
            ("Cancel run", "POST", "/threads/{threadId}/runs/{runId}/cancel"),
            ("List run steps", "GET", "/threads/{threadId}/runs/{runId}/steps"),
            ("Retrieve run step", "GET", "/threads/{threadId}/runs/{runId}/steps/{stepId}"),
        ]:
            _record_result(
                results,
                name=name,
                method=method,
                path=path,
                status=None,
                skipped=True,
                note="no assistant id found (set FUELIX_ASSISTANT_ID or ensure assistants exist)",
            )

    threads_to_delete = [primary_thread_id, run_thread_id, cancel_thread_id]
    unique_threads = list(dict.fromkeys(t for t in threads_to_delete if t))
    for index, thread_id in enumerate(unique_threads):
        status, _, note = _request("DELETE", f"/threads/{thread_id}", headers=headers)
        _record_result(
            results,
            name=f"Delete thread #{index + 1}",
            method="DELETE",
            path="/threads/{threadId}",
            status=status,
            note=note,
            accepted_statuses={200, 400, 404},
        )

    if created_copilot_id:
        status, _, note = _request("DELETE", f"/assistants/{created_copilot_id}", headers=headers)
        _record_result(
            results,
            name="Delete copilot",
            method="DELETE",
            path="/assistants/{id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Delete copilot",
            method="DELETE",
            path="/assistants/{id}",
            status=None,
            skipped=True,
            note="copilot creation failed",
        )

    if created_vector_store_id:
        status, _, note = _request("DELETE", f"/vector_stores/{created_vector_store_id}", headers=headers)
        _record_result(
            results,
            name="Delete vector store",
            method="DELETE",
            path="/vector_stores/{id}",
            status=status,
            note=note,
        )
    else:
        _record_result(
            results,
            name="Delete vector store",
            method="DELETE",
            path="/vector_stores/{id}",
            status=None,
            skipped=True,
            note="vector store creation failed",
        )

    if created_file_id:
        status, _, note = _request("DELETE", f"/files/{created_file_id}", headers=headers)
        _record_result(
            results,
            name="Delete file",
            method="DELETE",
            path="/files/{id}",
            status=status,
            note=note or "404 is acceptable if file was already removed by prior operations.",
            accepted_statuses={200, 404},
        )
    else:
        _record_result(
            results,
            name="Delete file",
            method="DELETE",
            path="/files/{id}",
            status=None,
            skipped=True,
            note="file upload failed",
        )

    print("\nFuel IX endpoint smoke test results\n")
    for result in results:
        if result.skipped:
            print(f"[SKIP] {result.name:20} {result.method:6} {result.path:44} {result.note}")
            continue

        state = "PASS" if result.ok else "FAIL"
        status = "none" if result.status is None else str(result.status)
        note_suffix = f" | {result.note}" if result.note else ""
        print(f"[{state}] {result.name:20} {result.method:6} {result.path:44} status={status}{note_suffix}")

    passed = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    print(f"\nSummary: passed={passed}, failed={failed}, skipped={skipped}")

    print("\nJSON results:")
    print(
        json.dumps(
            [
                {
                    "name": r.name,
                    "method": r.method,
                    "path": r.path,
                    "status": r.status,
                    "ok": r.ok,
                    "skipped": r.skipped,
                    "note": r.note,
                }
                for r in results
            ],
            indent=2,
        )
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
