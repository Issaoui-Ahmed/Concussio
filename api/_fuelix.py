from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Literal, Optional, Union
import os
import json
import requests


app = FastAPI()


DEFAULT_FUELIX_BASE_URL = "https://api.fuelix.ai/v1"


class CopilotTool(BaseModel):
    type: str


class CreateCopilotRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1)
    instructions: str = Field(min_length=1, max_length=256000)
    description: str = Field(min_length=1, max_length=600)
    metadata: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    top_p: Optional[Union[float, Dict[str, Any]]] = None
    reasoning: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh"]] = None
    tools: List[CopilotTool] = Field(default_factory=list, max_length=128)
    tool_resources: Optional[Dict[str, Any]] = None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if value < 0 or value > 2:
            raise ValueError("temperature must be between 0 and 2")
        return value

    @field_validator("top_p")
    @classmethod
    def validate_top_p(
        cls, value: Optional[Union[float, Dict[str, Any]]]
    ) -> Optional[Union[float, Dict[str, Any]]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if not isinstance(value, (int, float)):
            raise ValueError("top_p must be a number, object, or null")
        if value < 0 or value > 1:
            raise ValueError("top_p number must be between 0 and 1")
        return value


class UpdateCopilotRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    model: Optional[str] = Field(default=None, min_length=1)
    instructions: Optional[str] = Field(default=None, min_length=1, max_length=256000)
    description: Optional[str] = Field(default=None, min_length=1, max_length=600)
    metadata: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    top_p: Optional[Union[float, Dict[str, Any]]] = None
    reasoning: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh"]] = None
    tools: Optional[List[CopilotTool]] = Field(default=None, max_length=128)
    tool_resources: Optional[Dict[str, Any]] = None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if value < 0 or value > 2:
            raise ValueError("temperature must be between 0 and 2")
        return value

    @field_validator("top_p")
    @classmethod
    def validate_top_p(
        cls, value: Optional[Union[float, Dict[str, Any]]]
    ) -> Optional[Union[float, Dict[str, Any]]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if not isinstance(value, (int, float)):
            raise ValueError("top_p must be a number, object, or null")
        if value < 0 or value > 1:
            raise ValueError("top_p number must be between 0 and 1")
        return value


class CreateVectorStoreRequest(BaseModel):
    name: str = Field(min_length=1)
    file_ids: List[str] = Field(default_factory=list)
    expires_after: Optional[Dict[str, Any]] = None
    chunking_strategy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AttachVectorStoreFileRequest(BaseModel):
    file_id: str = Field(min_length=1)
    chunking_strategy: Optional[Dict[str, Any]] = None


class UpdateVectorStoreRequest(BaseModel):
    name: Optional[str] = None
    expires_after: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class ThreadMessageInput(BaseModel):
    role: Literal["user", "assistant"]
    content: Any
    attachments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class CreateThreadRequest(BaseModel):
    messages: List[ThreadMessageInput] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tool_resources: Optional[Dict[str, Any]] = None


class UpdateThreadRequest(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tool_resources: Optional[Dict[str, Any]] = None


class CreateThreadRunRequest(BaseModel):
    assistant_id: str = Field(min_length=1)
    thread: Dict[str, Any]
    stream: Optional[bool] = None
    model: Optional[str] = None
    reasoning: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh"]] = None


class CreateMessageRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]
    attachments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, str]] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: Union[str, List[Dict[str, Any]]]) -> Union[str, List[Dict[str, Any]]]:
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("content cannot be empty")
            return value

        if not value:
            raise ValueError("content array must contain at least one content block")

        for item in value:
            if not isinstance(item, dict):
                raise ValueError("content array items must be objects")
            item_type = item.get("type")
            if item_type == "text":
                text_value = item.get("text")
                if not isinstance(text_value, str) or not text_value.strip():
                    raise ValueError("text content blocks must include a non-empty text field")
                continue
            if item_type == "image_url":
                image_url = item.get("image_url")
                if not isinstance(image_url, dict) or not isinstance(image_url.get("url"), str):
                    raise ValueError("image_url content blocks must include image_url.url")
                continue
            if item_type == "image_file":
                image_file = item.get("image_file")
                if not isinstance(image_file, dict) or not isinstance(image_file.get("file_id"), str):
                    raise ValueError("image_file content blocks must include image_file.file_id")
                continue
            raise ValueError("unsupported content block type")

        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if value is None:
            return None
        if len(value) > 16:
            raise ValueError("metadata supports at most 16 key-value pairs")
        for key, item in value.items():
            if len(key) > 64:
                raise ValueError("metadata keys must be <= 64 characters")
            if len(item) > 512:
                raise ValueError("metadata values must be <= 512 characters")
        return value

    @field_validator("attachments")
    @classmethod
    def validate_attachments(cls, value: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if value is None:
            return None
        for attachment in value:
            if not isinstance(attachment, dict):
                raise ValueError("attachments items must be objects")
            file_id = attachment.get("file_id")
            if file_id is not None and not isinstance(file_id, str):
                raise ValueError("attachments.file_id must be a string")
            tools = attachment.get("tools")
            if tools is not None and not isinstance(tools, list):
                raise ValueError("attachments.tools must be an array when provided")
        return value


def _get_fuelix_api_key() -> str:
    api_key = os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Fuel IX API key is missing. Set FUELIX_API_KEY in your environment.",
        )
    return api_key


def _get_fuelix_base_url() -> str:
    return os.getenv("FUELIX_API_BASE_URL", DEFAULT_FUELIX_BASE_URL).rstrip("/")


def _get_fuelix_product_id() -> Optional[str]:
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    return product_id or None


def _pagination_params(
    after: Optional[str],
    before: Optional[str],
    limit: int,
    order: Literal["asc", "desc"],
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": limit, "order": order}
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    if run_id:
        params["run_id"] = run_id
    return params


def _request_fuelix(
    method: str,
    endpoint_path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_payload: Optional[Dict[str, Any]] = None,
    form_payload: Optional[Dict[str, Any]] = None,
    files_payload: Optional[Dict[str, Any]] = None,
) -> Any:
    url = f"{_get_fuelix_base_url()}{endpoint_path}"
    headers = {"Authorization": f"Bearer {_get_fuelix_api_key()}"}
    product_id = _get_fuelix_product_id()
    if product_id:
        headers["product-id"] = product_id

    if json_payload is not None:
        headers["Content-Type"] = "application/json"

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_payload,
            data=form_payload,
            files=files_payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Fuel IX request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}

    if response.status_code >= 400:
        detail: Any = payload
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message") or payload
        raise HTTPException(status_code=response.status_code, detail=detail)

    return payload


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    if isinstance(payload, list):
        return payload
    return []


@app.get("/copilots")
@app.get("/api/fuelix/copilots")
def list_copilots(
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        "/assistants",
        params=_pagination_params(after, before, limit, order),
    )
    return {"items": _extract_items(payload), "raw": payload}


@app.get("/models")
@app.get("/api/fuelix/models")
def list_models():
    payload = _request_fuelix("GET", "/models")
    return {"items": _extract_items(payload), "raw": payload}


@app.post("/copilots")
@app.post("/api/fuelix/copilots")
def create_copilot(request: CreateCopilotRequest):
    payload = _request_fuelix(
        "POST",
        "/assistants",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.get("/copilots/{copilot_id}")
@app.get("/api/fuelix/copilots/{copilot_id}")
def retrieve_copilot(copilot_id: str):
    payload = _request_fuelix("GET", f"/assistants/{copilot_id}")
    return payload


@app.post("/copilots/{copilot_id}")
@app.post("/api/fuelix/copilots/{copilot_id}")
def update_copilot(copilot_id: str, request: UpdateCopilotRequest):
    payload = _request_fuelix(
        "POST",
        f"/assistants/{copilot_id}",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.delete("/copilots/{copilot_id}")
@app.delete("/api/fuelix/copilots/{copilot_id}")
def delete_copilot(copilot_id: str):
    payload = _request_fuelix("DELETE", f"/assistants/{copilot_id}")
    return payload


@app.get("/files")
@app.get("/api/fuelix/files")
def list_files(limit: int = 100):
    payload = _request_fuelix("GET", "/files", params={"limit": limit})
    return {"items": _extract_items(payload), "raw": payload}


@app.post("/files")
@app.post("/api/fuelix/files")
async def upload_file(
    file: UploadFile = File(...),
    purpose: Literal["assistants", "vision"] = Form("assistants"),
    alias_id: Optional[str] = Form(None),
):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    files_payload = {
        "file": (
            file.filename,
            file_bytes,
            file.content_type or "application/octet-stream",
        )
    }
    form_payload: Dict[str, Any] = {"purpose": purpose}
    if alias_id:
        form_payload["alias_id"] = alias_id

    payload = _request_fuelix(
        "POST",
        "/files",
        form_payload=form_payload,
        files_payload=files_payload,
    )
    return payload


@app.get("/files/{file_id}")
@app.get("/api/fuelix/files/{file_id}")
def retrieve_file(file_id: str):
    payload = _request_fuelix("GET", f"/files/{file_id}")
    return payload


@app.delete("/files/{file_id}")
@app.delete("/api/fuelix/files/{file_id}")
def delete_file(file_id: str):
    payload = _request_fuelix("DELETE", f"/files/{file_id}")
    return payload


@app.get("/vector-stores")
@app.get("/api/fuelix/vector-stores")
def list_vector_stores(
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        "/vector_stores",
        params=_pagination_params(after, before, limit, order),
    )
    return {"items": _extract_items(payload), "raw": payload}


@app.post("/vector-stores")
@app.post("/api/fuelix/vector-stores")
def create_vector_store(request: CreateVectorStoreRequest):
    body = request.model_dump(exclude_none=True)
    if not body.get("file_ids"):
        body.pop("file_ids", None)
    payload = _request_fuelix("POST", "/vector_stores", json_payload=body)
    return payload


@app.get("/vector-stores/{vector_store_id}")
@app.get("/api/fuelix/vector-stores/{vector_store_id}")
def retrieve_vector_store(vector_store_id: str):
    payload = _request_fuelix("GET", f"/vector_stores/{vector_store_id}")
    return payload


@app.post("/vector-stores/{vector_store_id}")
@app.post("/api/fuelix/vector-stores/{vector_store_id}")
@app.put("/vector-stores/{vector_store_id}")
@app.put("/api/fuelix/vector-stores/{vector_store_id}")
@app.patch("/vector-stores/{vector_store_id}")
@app.patch("/api/fuelix/vector-stores/{vector_store_id}")
def update_vector_store(vector_store_id: str, request: UpdateVectorStoreRequest):
    payload = _request_fuelix(
        "POST",
        f"/vector_stores/{vector_store_id}",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.delete("/vector-stores/{vector_store_id}")
@app.delete("/api/fuelix/vector-stores/{vector_store_id}")
def delete_vector_store(vector_store_id: str):
    payload = _request_fuelix("DELETE", f"/vector_stores/{vector_store_id}")
    return payload


@app.post("/vector-stores/{vector_store_id}/files")
@app.post("/api/fuelix/vector-stores/{vector_store_id}/files")
def attach_file_to_vector_store(vector_store_id: str, request: AttachVectorStoreFileRequest):
    payload = _request_fuelix(
        "POST",
        f"/vector_stores/{vector_store_id}/files",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


def _parse_chunking_strategy(chunking_strategy: Optional[str]) -> Optional[Dict[str, Any]]:
    if not chunking_strategy:
        return None
    try:
        parsed_chunking = json.loads(chunking_strategy)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="chunking_strategy must be valid JSON.") from exc
    if not isinstance(parsed_chunking, dict):
        raise HTTPException(status_code=400, detail="chunking_strategy must be a JSON object.")
    return parsed_chunking


async def _upload_and_attach_file_to_vector_store(
    *,
    vector_store_id: str,
    file: UploadFile,
    purpose: Literal["assistants", "vision"],
    alias_id: Optional[str],
    parsed_chunking_strategy: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail=f"Uploaded file '{file.filename}' is empty.")

    files_payload = {
        "file": (
            file.filename,
            file_bytes,
            file.content_type or "application/octet-stream",
        )
    }
    form_payload: Dict[str, Any] = {"purpose": purpose}
    if alias_id:
        form_payload["alias_id"] = alias_id

    uploaded_file = _request_fuelix(
        "POST",
        "/files",
        form_payload=form_payload,
        files_payload=files_payload,
    )
    file_id = uploaded_file.get("id") if isinstance(uploaded_file, dict) else None
    if not isinstance(file_id, str) or not file_id:
        raise HTTPException(status_code=502, detail="Fuel IX did not return a file id after upload.")

    attach_payload: Dict[str, Any] = {"file_id": file_id}
    if parsed_chunking_strategy:
        attach_payload["chunking_strategy"] = parsed_chunking_strategy

    try:
        vector_store_file = _request_fuelix(
            "POST",
            f"/vector_stores/{vector_store_id}/files",
            json_payload=attach_payload,
        )
    except HTTPException as exc:
        try:
            _request_fuelix("DELETE", f"/files/{file_id}")
        except HTTPException:
            pass
        raise exc

    return {"file": uploaded_file, "vector_store_file": vector_store_file}


@app.post("/vector-stores/{vector_store_id}/upload-file")
@app.post("/api/fuelix/vector-stores/{vector_store_id}/upload-file")
async def upload_file_to_vector_store(
    vector_store_id: str,
    file: UploadFile = File(...),
    purpose: Literal["assistants", "vision"] = Form("assistants"),
    alias_id: Optional[str] = Form(None),
    chunking_strategy: Optional[str] = Form(None),
):
    parsed_chunking_strategy = _parse_chunking_strategy(chunking_strategy)
    return await _upload_and_attach_file_to_vector_store(
        vector_store_id=vector_store_id,
        file=file,
        purpose=purpose,
        alias_id=alias_id,
        parsed_chunking_strategy=parsed_chunking_strategy,
    )


@app.post("/vector-stores/{vector_store_id}/upload-files")
@app.post("/api/fuelix/vector-stores/{vector_store_id}/upload-files")
async def upload_files_to_vector_store(
    vector_store_id: str,
    files: List[UploadFile] = File(...),
    purpose: Literal["assistants", "vision"] = Form("assistants"),
    alias_id: Optional[str] = Form(None),
    chunking_strategy: Optional[str] = Form(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    parsed_chunking_strategy = _parse_chunking_strategy(chunking_strategy)
    items: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for file in files:
        try:
            item = await _upload_and_attach_file_to_vector_store(
                vector_store_id=vector_store_id,
                file=file,
                purpose=purpose,
                alias_id=alias_id,
                parsed_chunking_strategy=parsed_chunking_strategy,
            )
            items.append(item)
        except HTTPException as exc:
            failures.append(
                {
                    "filename": file.filename,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )

    return {
        "count": len(items),
        "failed_count": len(failures),
        "items": items,
        "failures": failures,
    }


@app.get("/vector-stores/{vector_store_id}/files")
@app.get("/api/fuelix/vector-stores/{vector_store_id}/files")
def list_vector_store_files(
    vector_store_id: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        f"/vector_stores/{vector_store_id}/files",
        params=_pagination_params(after, before, limit, order),
    )
    return payload


@app.get("/vector-stores/{vector_store_id}/files/{file_id}")
@app.get("/api/fuelix/vector-stores/{vector_store_id}/files/{file_id}")
def retrieve_vector_store_file(vector_store_id: str, file_id: str):
    payload = _request_fuelix("GET", f"/vector_stores/{vector_store_id}/files/{file_id}")
    return payload


@app.delete("/vector-stores/{vector_store_id}/files/{file_id}")
@app.delete("/api/fuelix/vector-stores/{vector_store_id}/files/{file_id}")
def remove_vector_store_file(vector_store_id: str, file_id: str):
    payload = _request_fuelix("DELETE", f"/vector_stores/{vector_store_id}/files/{file_id}")
    return payload


@app.post("/threads/runs")
@app.post("/api/fuelix/threads/runs")
def create_thread_and_run(request: CreateThreadRunRequest):
    payload = _request_fuelix(
        "POST",
        "/threads/runs",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.post("/threads")
@app.post("/api/fuelix/threads")
def create_thread(request: CreateThreadRequest):
    payload = _request_fuelix("POST", "/threads", json_payload=request.model_dump(exclude_none=True))
    return payload


@app.get("/threads")
@app.get("/api/fuelix/threads")
def list_threads(
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        "/threads",
        params=_pagination_params(after, before, limit, order),
    )
    return payload


@app.post("/threads/{thread_id}")
@app.post("/api/fuelix/threads/{thread_id}")
def update_thread(thread_id: str, request: UpdateThreadRequest):
    payload = _request_fuelix(
        "POST",
        f"/threads/{thread_id}",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.get("/threads/{thread_id}")
@app.get("/api/fuelix/threads/{thread_id}")
def retrieve_thread(thread_id: str):
    payload = _request_fuelix("GET", f"/threads/{thread_id}")
    return payload


@app.delete("/threads/{thread_id}")
@app.delete("/api/fuelix/threads/{thread_id}")
def delete_thread(thread_id: str):
    payload = _request_fuelix("DELETE", f"/threads/{thread_id}")
    return payload


@app.get("/threads/{thread_id}/messages/{message_id}")
@app.get("/api/fuelix/threads/{thread_id}/messages/{message_id}")
def retrieve_message(thread_id: str, message_id: str):
    payload = _request_fuelix("GET", f"/threads/{thread_id}/messages/{message_id}")
    return payload


@app.post("/threads/{thread_id}/messages")
@app.post("/api/fuelix/threads/{thread_id}/messages")
def create_message(
    thread_id: str,
    request: CreateMessageRequest,
):
    payload = _request_fuelix(
        "POST",
        f"/threads/{thread_id}/messages",
        json_payload=request.model_dump(exclude_none=True),
    )
    return payload


@app.get("/threads/{thread_id}/messages")
@app.get("/api/fuelix/threads/{thread_id}/messages")
def list_messages(
    thread_id: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
    run_id: Optional[str] = None,
):
    payload = _request_fuelix(
        "GET",
        f"/threads/{thread_id}/messages",
        params=_pagination_params(after, before, limit, order, run_id=run_id),
    )
    return payload


@app.get("/threads/{thread_id}/runs/{run_id}")
@app.get("/api/fuelix/threads/{thread_id}/runs/{run_id}")
def retrieve_run(thread_id: str, run_id: str):
    payload = _request_fuelix("GET", f"/threads/{thread_id}/runs/{run_id}")
    return payload


@app.get("/threads/{thread_id}/runs")
@app.get("/api/fuelix/threads/{thread_id}/runs")
def list_runs(
    thread_id: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        f"/threads/{thread_id}/runs",
        params=_pagination_params(after, before, limit, order),
    )
    return payload


@app.post("/threads/{thread_id}/runs/{run_id}/cancel")
@app.post("/api/fuelix/threads/{thread_id}/runs/{run_id}/cancel")
def cancel_run(thread_id: str, run_id: str):
    payload = _request_fuelix("POST", f"/threads/{thread_id}/runs/{run_id}/cancel")
    return payload


@app.get("/threads/{thread_id}/runs/{run_id}/steps/{step_id}")
@app.get("/api/fuelix/threads/{thread_id}/runs/{run_id}/steps/{step_id}")
def retrieve_run_step(thread_id: str, run_id: str, step_id: str):
    payload = _request_fuelix("GET", f"/threads/{thread_id}/runs/{run_id}/steps/{step_id}")
    return payload


@app.get("/threads/{thread_id}/runs/{run_id}/steps")
@app.get("/api/fuelix/threads/{thread_id}/runs/{run_id}/steps")
def list_run_steps(
    thread_id: str,
    run_id: str,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
):
    payload = _request_fuelix(
        "GET",
        f"/threads/{thread_id}/runs/{run_id}/steps",
        params=_pagination_params(after, before, limit, order),
    )
    return payload
