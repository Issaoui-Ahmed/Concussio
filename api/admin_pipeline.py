"""Run the content refresh on demand, from /admin/scraping.

Same work the nightly cron does -- literally the same function -- exposed so a reviewer does not
have to wait until 06:17 UTC to find out whether the site changed. Two things make it worth
having beyond convenience:

    dryRun=true   scrapes and diffs but writes nothing, so "what would tonight do?" is
                  answerable without doing it.
    force=true    re-pushes the corpus even when its hash is unchanged. The repair path for a
                  copilot edited outside this system, which the hash comparison cannot see.

THIS ROUTE IS UNAUTHENTICATED, BY DECISION AND NOT BY OVERSIGHT. It was built behind
ADMIN_SECRET and the gate was removed on request: a shared secret typed per browser tab was
judged more friction than it was worth for an internal tool. Read that as a deliberate posture,
not a bug to quietly patch -- but read it clearly, because the blast radius is real:

    anyone who knows this path can rewrite the instructions of six production copilots,
    upload to the Fuel IX vector store, and rebuild the French pairing table.

What still stands between that and damage, none of it authentication:

    the gates      a scrape that looks broken (too few domains, too few tools, a bulk removal)
                   is refused before anything is written -- see refresh.py and vector_store.py.
    the lease      one run at a time, enforced by the database. Repeated calls serialise into
                   409s rather than piling concurrent writes onto the same tables.
    idempotence    a run with nothing to do writes nothing. Hammering this endpoint re-scrapes
                   the site; it does not accumulate changes.
    origin='manual' a person's pairing decision is never touched by a run, however it started.

If the posture is ever revisited, the thing to add is real per-person sign-in (Supabase Auth is
already in the stack), not another shared secret -- the identity is the part that was missing.

Status codes differ from the cron's on purpose. The cron answers 500 on a failed sink because
Vercel's log records nothing else. Here a person is reading a result panel, and a 500 would hide
the very body that explains what refused and why -- so a refusal is a 200 carrying `ok: false`.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()

# Mirrors the `crons` entry in vercel.json. Displayed so the card can say when the automatic run
# happens; nothing reads it to decide anything.
CRON_SCHEDULE = "17 6 * * *"

# How many past runs the card shows. Enough to see a pattern -- "the last four found nothing" --
# without turning the status call into a table scan.
HISTORY_LIMIT = 5


@app.get("/api/admin/pipeline/status")
def pipeline_status() -> JSONResponse:
    """What the card needs before anyone presses anything: is the store reachable, and what
    have recent runs done."""
    from scripts.content_pipeline.state import is_configured, load_recent_runs

    history = load_recent_runs(HISTORY_LIMIT)
    return JSONResponse(
        {
            "storeConfigured": is_configured(),
            "cronSchedule": CRON_SCHEDULE,
            "history": {
                "available": history.available,
                "error": history.error,
                "runs": [run.as_dict() for run in history.runs],
            },
        },
        headers={"Cache-Control": "no-store"},
    )


class RunRequest(BaseModel):
    dryRun: bool = False
    force: bool = False
    # Empty means every sink, which is what the cron runs. Naming a subset is for repairing one
    # sink without paying for the other two.
    sinks: List[str] = []


@app.post("/api/admin/pipeline/run")
def run_pipeline(payload: RunRequest) -> JSONResponse:
    from scripts.content_pipeline.refresh import ALL_SINKS, run_refresh
    from scripts.content_pipeline.state import TRIGGER_ADMIN, RunInFlight

    requested = payload.sinks or list(ALL_SINKS)
    unknown = [name for name in requested if name not in ALL_SINKS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sink(s): {', '.join(unknown)}. Valid: {', '.join(ALL_SINKS)}.",
        )

    try:
        result: Dict[str, Any] = run_refresh(
            force=payload.force,
            dry_run=payload.dryRun,
            sinks=requested,
            trigger=TRIGGER_ADMIN,
        )
    except RunInFlight as exc:
        # The nightly cron, another tab, or the same person pressing twice. All do this same
        # work, so the answer is "wait", not "try harder".
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JSONResponse(result, headers={"Cache-Control": "no-store"})
