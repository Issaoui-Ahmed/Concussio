"""Scheduled content refresh, running on Vercel Cron.

Why here and not GitHub Actions: GitHub disables scheduled workflows after 60 days of
repository inactivity, which would silently stop the automation two months after handoff.
Vercel crons never go dormant, so this needs no maintenance.

The design constraint that shapes everything below: **a Vercel function cannot write files.**
Serverless filesystems are read-only apart from an ephemeral /tmp, so there is nowhere to
commit `all_rec_markdown.md`. That rules out git-as-change-detector.

So the remote assistants ARE the state store. The flow is:

    scrape the guideline -> build instructions in memory -> read what Fuel IX currently has
    -> patch only the assistants whose instructions differ

No database, no token, nothing to rotate. "Has the site changed?" is answered by comparing
against what is actually deployed, which is a more truthful question than comparing against a
file in a repo.

What this does NOT cover: `lib/i18n/resourceLinks.data.ts` is a build-time artifact and cannot
be regenerated at runtime. EN->FR resource pairing stays a deliberate, reviewed change made
via `python -m scripts.content_pipeline.cli refresh` locally. It changes rarely; the guideline
text changes more often.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Any, Dict, List

from fastapi import FastAPI, Header, HTTPException

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fuelix_chat import ASSISTANT_ENV_BY_USER_TYPE, normalize_user_type
from core.prompts import build_fuelix_assistant_instructions

app = FastAPI()

# Floors mirroring scripts/content_pipeline/gates.py. A site redesign that breaks a selector
# returns empty sections rather than raising, and `core/scraper.py` swallows a failed section
# fetch into an empty dict — so without these a broken scrape would publish a gutted guideline
# to every assistant.
MIN_DOMAINS = 12
MIN_RECOMMENDATIONS = 90
MIN_CORPUS_CHARS = 100_000


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _require_cron_auth(authorization: str | None) -> None:
    """Reject anything that is not Vercel's scheduler.

    This endpoint scrapes and then patches six production assistants. Vercel sends
    `Authorization: Bearer $CRON_SECRET` when CRON_SECRET is set; without this check the URL
    would be a public trigger for a live content push.
    """
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured; refusing to run an unauthenticated content push.",
        )
    if authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _gate_corpus(markdown: str, domain_count: int) -> List[str]:
    """Returns a list of problems; empty means the scrape looks trustworthy."""
    from scripts.content_pipeline.corpus import analyze

    stats = analyze(markdown)
    problems: List[str] = []
    if domain_count < MIN_DOMAINS:
        problems.append(f"only {domain_count} domains (need >= {MIN_DOMAINS})")
    if len(stats.recommendation_numbers) < MIN_RECOMMENDATIONS:
        problems.append(
            f"only {len(stats.recommendation_numbers)} recommendations (need >= {MIN_RECOMMENDATIONS})"
        )
    if stats.characters < MIN_CORPUS_CHARS:
        problems.append(f"only {stats.characters} chars (need >= {MIN_CORPUS_CHARS})")
    return problems


def _fuelix_request(method: str, path: str, **kwargs) -> Any:
    import requests

    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="FUELIX_API_KEY is not set.")

    base = (os.getenv("FUELIX_API_BASE_URL") or "https://api.fuelix.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"

    response = requests.request(method, f"{base}{path}", headers=headers, timeout=90, **kwargs)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Fuel IX {method} {path} -> {response.status_code}: {response.text[:300]}",
        )
    return response.json()


@app.post("/api/cron/refresh")
@app.get("/api/cron/refresh")
def refresh_content(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    """Scrape the guideline and push it to any assistant whose copy is out of date."""
    _require_cron_auth(authorization)
    started = time.perf_counter()

    from scripts.content_pipeline.corpus import fetch_corpus

    corpus_markdown, domains = fetch_corpus()

    problems = _gate_corpus(corpus_markdown, len(domains))
    if problems:
        # Deliberately not a 5xx: the run did its job by refusing. Returning ok=false with the
        # reason keeps the failure visible in the cron log without pretending the site is down.
        return {
            "ok": False,
            "action": "aborted",
            "reason": "corpus gate failed",
            "problems": problems,
            "domains": len(domains),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    results: List[Dict[str, Any]] = []
    patched = unchanged = 0

    for role, env_var in ASSISTANT_ENV_BY_USER_TYPE.items():
        assistant_id = (os.getenv(env_var) or "").strip()
        if not assistant_id:
            results.append({"role": role, "status": "skipped", "reason": f"{env_var} not set"})
            continue

        desired = build_fuelix_assistant_instructions(
            normalize_user_type(role), recommendations_markdown=corpus_markdown
        )

        current = _fuelix_request("GET", f"/assistants/{assistant_id}") or {}
        current_instructions = current.get("instructions") or ""

        if current_instructions == desired:
            unchanged += 1
            results.append({"role": role, "status": "unchanged", "hash": _digest(desired)})
            continue

        _fuelix_request("POST", f"/assistants/{assistant_id}", json={"instructions": desired})

        # Read back rather than trusting the write: a partial patch would otherwise be
        # reported as success.
        after = _fuelix_request("GET", f"/assistants/{assistant_id}") or {}
        landed = (after.get("instructions") or "") == desired
        patched += 1 if landed else 0
        results.append(
            {
                "role": role,
                "status": "patched" if landed else "patch-not-verified",
                "hash": _digest(desired),
                "chars": len(desired),
            }
        )

    failed = [item for item in results if item["status"] == "patch-not-verified"]
    return {
        "ok": not failed,
        "action": "patched" if patched else "no-change",
        "domains": len(domains),
        "corpus_chars": len(corpus_markdown),
        "corpus_hash": _digest(corpus_markdown),
        "patched": patched,
        "unchanged": unchanged,
        "assistants": results,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
