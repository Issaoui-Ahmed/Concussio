import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "expired", "incomplete"}
TRANSIENT_FAULT_MARKER = "SC-FirebaseTokenExchange"


@dataclass
class ApiCall:
    name: str
    method: str
    path: str
    status: Optional[int]
    ok: bool
    note: str = ""
    body: Any = None


@dataclass
class QaCase:
    question: str
    eval_mode: str  # "contains_all" or "expect_unknown"
    expected_terms: List[str]


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
    fault = payload.get("fault")
    if isinstance(fault, dict):
        fault_string = fault.get("faultstring")
        if isinstance(fault_string, str) and fault_string.strip():
            return fault_string.strip()
    for key in ("error", "message", "detail", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
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
    retries: int = 2,
) -> ApiCall:
    url = f"{_base_url()}{path}"
    use_json_headers = files is None
    headers = _headers(json_content=use_json_headers)
    accepted_codes = accepted or {200, 201}

    last_status: Optional[int] = None
    last_body: Any = {}
    last_note = ""

    for attempt in range(retries + 1):
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
            last_status = response.status_code
            try:
                last_body = response.json()
            except ValueError:
                last_body = {"raw": response.text}
            last_note = _note_from_payload(last_body)
        except requests.RequestException as exc:
            last_status = None
            last_body = {}
            last_note = str(exc)

        if last_status in accepted_codes:
            return ApiCall(name, method, path, last_status, True, last_note, last_body)

        is_transient_500 = (
            last_status == 500
            and isinstance(last_note, str)
            and TRANSIENT_FAULT_MARKER in last_note
        )
        if is_transient_500 and attempt < retries:
            time.sleep(2.0)
            continue

        return ApiCall(
            name=name,
            method=method,
            path=path,
            status=last_status,
            ok=False,
            note=last_note,
            body=last_body,
        )

    return ApiCall(name, method, path, last_status, False, last_note, last_body)


def _extract_assistant_text(messages_payload: Any) -> str:
    if not isinstance(messages_payload, dict):
        return ""
    data = messages_payload.get("data")
    if not isinstance(data, list):
        return ""
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text_obj = block.get("text")
            if isinstance(text_obj, dict):
                value = text_obj.get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _poll_run_terminal(thread_id: str, run_id: str) -> ApiCall:
    last: Optional[ApiCall] = None
    for _ in range(25):
        result = _request(
            "Poll run",
            "GET",
            f"/threads/{thread_id}/runs/{run_id}",
            accepted={200},
            retries=2,
        )
        last = result
        if not result.ok:
            return result
        status = result.body.get("status") if isinstance(result.body, dict) else None
        if isinstance(status, str) and status in TERMINAL_RUN_STATES:
            return result
        time.sleep(2.0)
    return last or ApiCall("Poll run", "GET", f"/threads/{thread_id}/runs/{run_id}", None, False, "timeout")


def _evaluate_answer(case: QaCase, answer: str) -> Dict[str, Any]:
    normalized = answer.lower()
    if case.eval_mode == "contains_all":
        missing = [term for term in case.expected_terms if term.lower() not in normalized]
        return {
            "pass": len(missing) == 0,
            "missing_terms": missing,
            "matched_terms": [term for term in case.expected_terms if term.lower() in normalized],
        }

    unknown_markers = [
        "cannot find",
        "not in the provided",
        "not provided",
        "i don't have",
        "i do not have",
        "not available",
        "don't see",
    ]
    marker_hit = any(marker in normalized for marker in unknown_markers)
    fabricated_like = bool(re.search(r"\b[a-z]{2,5}-\d{3,6}\b", normalized))
    return {
        "pass": marker_hit and not fabricated_like,
        "marker_hit": marker_hit,
        "fabricated_pattern_detected": fabricated_like,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            lk = key.lower()
            if lk in {"authorization", "token", "api_key", "proxykey"}:
                clean[key] = "***REDACTED***"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def main() -> int:
    _load_env()
    calls: List[ApiCall] = []
    qa_results: List[Dict[str, Any]] = []

    uploaded_file_ids: List[str] = []
    created_threads: List[str] = []
    vector_store_id: Optional[str] = None
    assistant_id: Optional[str] = None

    fixtures = [
        (
            "clinic_protocol.txt",
            (
                "Concussion Clinic Return-to-Learn Protocol (v2.3)\n"
                "Effective date: 2026-02-01\n"
                "Step 1: Relative cognitive rest for 24 hours.\n"
                "Step 2: Light cognitive activity capped at 30 minutes/day.\n"
                "Step 3: Return to full school load only after 24 hours symptom-free.\n"
            ),
        ),
        (
            "operations_contact.txt",
            (
                "Concussion Program Operations Contact Sheet\n"
                "Urgent on-call number: 1-800-555-0142\n"
                "Extension: 77\n"
                "Follow-up cadence: every 72 hours for first two visits, then weekly.\n"
            ),
        ),
        (
            "sports_clearance.txt",
            (
                "Sports Clearance Policy\n"
                "Minimum timeline: 7 days from symptom onset before full-contact clearance.\n"
                "Physician signature code required on form: CL-77B.\n"
                "Internal baseline test code: RLP-8841.\n"
            ),
        ),
    ]

    created_temp_paths: List[Path] = []
    for filename, content in fixtures:
        path = Path(__file__).resolve().parent / f"rag_exp_{int(time.time())}_{filename}"
        path.write_text(content, encoding="utf-8")
        created_temp_paths.append(path)

    try:
        for path in created_temp_paths:
            with path.open("rb") as handle:
                upload = _request(
                    f"Upload {path.name}",
                    "POST",
                    "/files",
                    files={"file": (path.name, handle, "text/plain")},
                    data={"purpose": "assistants", "alias_id": f"rag-exp-{int(time.time())}"},
                )
            calls.append(upload)
            if upload.ok and isinstance(upload.body, dict) and isinstance(upload.body.get("id"), str):
                uploaded_file_ids.append(upload.body["id"])
    finally:
        for path in created_temp_paths:
            if path.exists():
                path.unlink()

    create_store = _request(
        "Create vector store",
        "POST",
        "/vector_stores",
        json_body={"name": f"RAG Realistic Experiment {int(time.time())}", "metadata": {"test": "rag-realistic"}},
    )
    calls.append(create_store)
    if create_store.ok and isinstance(create_store.body, dict) and isinstance(create_store.body.get("id"), str):
        vector_store_id = create_store.body["id"]

    if vector_store_id:
        for file_id in uploaded_file_ids:
            attach = _request(
                f"Attach file {file_id}",
                "POST",
                f"/vector_stores/{vector_store_id}/files",
                json_body={"file_id": file_id},
            )
            calls.append(attach)

            # Wait until each file is indexed.
            for _ in range(25):
                get_file = _request(
                    f"Poll VS file {file_id}",
                    "GET",
                    f"/vector_stores/{vector_store_id}/files/{file_id}",
                    accepted={200},
                    retries=2,
                )
                calls.append(get_file)
                if not get_file.ok:
                    break
                status = get_file.body.get("status") if isinstance(get_file.body, dict) else None
                if status == "completed":
                    break
                time.sleep(2.0)

    if vector_store_id:
        create_assistant = _request(
            "Create RAG assistant",
            "POST",
            "/assistants",
            json_body={
                "name": f"RAG Experiment Assistant {int(time.time())}",
                "description": "Assistant for realistic retrieval experiment.",
                "model": "claude-sonnet-4-5",
                "instructions": (
                    "Answer strictly from the provided knowledge base. "
                    "If information is not present, say you cannot find it in the provided documents."
                ),
                "tools": [],
                "tool_resources": {"file_search": {"vector_store_ids": [vector_store_id]}},
            },
        )
        calls.append(create_assistant)
        if create_assistant.ok and isinstance(create_assistant.body, dict) and isinstance(create_assistant.body.get("id"), str):
            assistant_id = create_assistant.body["id"]

    qa_cases = [
        QaCase(
            question="What is the urgent on-call number and extension for the concussion program?",
            eval_mode="contains_all",
            expected_terms=["1-800-555-0142", "77"],
        ),
        QaCase(
            question="After how long symptom-free can a student return to full school load?",
            eval_mode="contains_all",
            expected_terms=["24 hours", "symptom-free"],
        ),
        QaCase(
            question="What is the minimum days from symptom onset for full-contact clearance and what signature code is required?",
            eval_mode="contains_all",
            expected_terms=["7 days", "CL-77B"],
        ),
        QaCase(
            question="What is the MRI machine serial number used by this clinic?",
            eval_mode="expect_unknown",
            expected_terms=[],
        ),
    ]

    if assistant_id:
        for idx, case in enumerate(qa_cases, start=1):
            run_create = _request(
                f"Create run Q{idx}",
                "POST",
                "/threads/runs",
                json_body={
                    "assistant_id": assistant_id,
                    "model": "claude-sonnet-4-5",
                    "thread": {"messages": [{"role": "user", "content": case.question}]},
                },
            )
            calls.append(run_create)
            if not run_create.ok:
                qa_results.append(
                    {
                        "question": case.question,
                        "pass": False,
                        "error": f"run create failed with status {run_create.status}",
                    }
                )
                continue

            run_id = run_create.body.get("id") if isinstance(run_create.body, dict) else None
            thread_id = run_create.body.get("thread_id") if isinstance(run_create.body, dict) else None
            if not isinstance(run_id, str) or not isinstance(thread_id, str):
                qa_results.append(
                    {
                        "question": case.question,
                        "pass": False,
                        "error": "missing run_id or thread_id",
                    }
                )
                continue
            created_threads.append(thread_id)

            final_run = _poll_run_terminal(thread_id, run_id)
            final_run.name = f"Wait run Q{idx}"
            calls.append(final_run)

            list_msgs = _request(
                f"List messages Q{idx}",
                "GET",
                f"/threads/{thread_id}/messages",
                accepted={200},
            )
            calls.append(list_msgs)

            answer_text = _extract_assistant_text(list_msgs.body)
            eval_result = _evaluate_answer(case, answer_text)
            qa_results.append(
                {
                    "question": case.question,
                    "pass": bool(eval_result.get("pass")),
                    "evaluation": eval_result,
                    "assistant_answer": answer_text,
                    "run_status": (
                        final_run.body.get("status")
                        if isinstance(final_run.body, dict)
                        else None
                    ),
                }
            )

    # Cleanup resources.
    for thread_id in list(dict.fromkeys(created_threads)):
        calls.append(
            _request(
                f"Delete thread {thread_id}",
                "DELETE",
                f"/threads/{thread_id}",
                accepted={200, 400, 404},
            )
        )

    if assistant_id:
        calls.append(_request("Delete assistant", "DELETE", f"/assistants/{assistant_id}", accepted={200, 404}))

    if vector_store_id:
        for file_id in uploaded_file_ids:
            calls.append(
                _request(
                    f"Remove VS file {file_id}",
                    "DELETE",
                    f"/vector_stores/{vector_store_id}/files/{file_id}",
                    accepted={200, 404},
                )
            )
        calls.append(_request("Delete vector store", "DELETE", f"/vector_stores/{vector_store_id}", accepted={200, 404}))

    for file_id in uploaded_file_ids:
        calls.append(_request(f"Delete file {file_id}", "DELETE", f"/files/{file_id}", accepted={200, 404}))

    print("\nFuel IX Realistic RAG Experiment\n")
    for call in calls:
        state = "PASS" if call.ok else "FAIL"
        status = "none" if call.status is None else str(call.status)
        suffix = f" | {call.note}" if call.note else ""
        print(f"[{state}] {call.name:30} {call.method:6} {call.path:46} status={status}{suffix}")

    qa_passed = sum(1 for result in qa_results if result.get("pass"))
    qa_total = len(qa_results)
    print(f"\nQA Score: {qa_passed}/{qa_total}\n")
    print("QA Details:")
    print(json.dumps(_sanitize(qa_results), indent=2))

    failed_calls = [call for call in calls if not call.ok]
    print("\nSummary:")
    print(
        json.dumps(
            _sanitize(
                {
                    "assistant_id": assistant_id,
                    "vector_store_id": vector_store_id,
                    "uploaded_file_ids": uploaded_file_ids,
                    "qa_passed": qa_passed,
                    "qa_total": qa_total,
                    "failed_api_calls": [
                        {
                            "name": call.name,
                            "path": call.path,
                            "status": call.status,
                            "note": call.note,
                        }
                        for call in failed_calls
                    ],
                }
            ),
            indent=2,
        )
    )

    if failed_calls:
        return 1
    return 0 if qa_passed == qa_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
