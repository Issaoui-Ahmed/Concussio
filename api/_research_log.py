"""/admin/research-log: what the CHEO study log is configured to do, and a live test of it.

The test writes a real file into CHEO's folder, so unlike most admin endpoints these check the
admin cookie (`api/admin_access.py`).

A failed test answers 200 with `ok: false`, like /api/admin/pipeline/run: a person is reading
a step-by-step panel, and a 500 would hide the very body that says which step broke and why.
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import admin_access
from core import research_log

app = FastAPI()


def _require_admin(request: Request) -> None:
    if not admin_access.is_admin(request.cookies.get(admin_access.COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Unlock /admin with the admin password first.")


@app.get("/api/admin/research-log/status")
def research_log_status(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(research_log.status(), headers={"Cache-Control": "no-store"})


@app.post("/api/admin/research-log/test")
def research_log_test(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(research_log.run_delivery_test(), headers={"Cache-Control": "no-store"})
