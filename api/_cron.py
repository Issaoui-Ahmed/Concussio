"""Scheduled content refresh, running on Vercel Cron.

The work lives in `scripts/content_pipeline/refresh.py`, which the admin button and the local
CLI call too -- this module is the scheduler's door into it: authenticate, run, choose a status
code. Keeping the orchestration out of the request handler is what stops "what the nightly run
does" and "what the button does" from being two different things.

Why Vercel Cron and not GitHub Actions: GitHub disables scheduled workflows after 60 days of
repository inactivity, which would silently stop the automation two months after handoff.
Vercel crons never go dormant.
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()


def _require_cron_auth(authorization: str | None) -> None:
    """Reject anything that is not Vercel's scheduler.

    This endpoint scrapes and then writes to six production assistants, a vector store and the
    live pairing table. Vercel sends `Authorization: Bearer $CRON_SECRET`; without this check
    the URL would be a public trigger for all of that.
    """
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured; refusing to run an unauthenticated content push.",
        )
    if authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized.")


@app.post("/api/cron/refresh")
@app.get("/api/cron/refresh")
def refresh_content(
    authorization: str | None = Header(default=None),
    force: int = 0,
) -> JSONResponse:
    """Run all three sinks. Each is independent; one failing does not stop the others.

    `?force=1` re-pushes the corpus even when its hash is unchanged, which is the way to repair
    an assistant that was edited outside this system.

    Returns 500 when any sink failed. This used to answer 200 with `ok: false` in the body,
    which meant a run that refused every night looked identical to a healthy one from the
    outside -- Vercel's own log only records the status code, so nothing would ever surface it.
    (The admin endpoint deliberately does the opposite: a person reading a result panel needs
    the body, not the status.)

    A 409 means someone pressed the button in /admin/scraping and their run is still going. The
    schedule is daily, so the next attempt is a day away -- but the run that holds the lease is
    doing this exact work anyway, so nothing is missed.
    """
    _require_cron_auth(authorization)

    from scripts.content_pipeline.refresh import run_refresh
    from scripts.content_pipeline.state import TRIGGER_CRON, RunInFlight

    try:
        payload = run_refresh(force=bool(force), trigger=TRIGGER_CRON)
    except RunInFlight as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JSONResponse(payload, status_code=200 if payload.get("ok") else 500)
