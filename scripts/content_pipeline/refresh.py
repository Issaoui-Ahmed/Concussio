"""The refresh itself: one scrape, three sinks, each gated on its own comparison against Supabase.

    recommendations   -> content_state       -> copilot instructions (6 assistants)
    tool links        -> vector_store_files  -> Fuel IX vector store
    EN + FR listings  -> resource_pairs      -> the map the app resolves French links from

Supabase is the "what we have" side of every one of those comparisons. That matters because a
Vercel function cannot write files -- serverless filesystems are read-only apart from an
ephemeral /tmp -- so a committed file can never record what a deployed run actually published.
Every file-based record this replaced had already drifted: `all_rec_markdown.md` was never
written by any deployment, and `data/resource-pairs.json` only changed when someone ran a local
CLI.

Three callers, one code path:

    api/cron.py                        nightly, on Vercel Cron
    api/admin_pipeline.py              the button in /admin/scraping
    scripts/content_pipeline/cli.py    local

This module exists because those three were drifting. The orchestration used to live inside the
cron's request handler, which meant the CLI reached backwards into `api.cron` to borrow it and
the admin path would have had to reimplement it. A second implementation of "what the nightly
run does" is a second thing to keep true.

Each sink is independent. One failing does not stop the others, and each reports its own
outcome, so a bad scrape of the French listing cannot block a genuine guideline update.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.content_pipeline.state import (
    RunInFlight,
    StateError,
    TRIGGER_CRON,
    claim_run,
    finish_run,
)

# Floors mirroring scripts/content_pipeline/gates.py. A site redesign that breaks a selector
# returns empty sections rather than raising, and `core/scraper.py` swallows a failed section
# fetch into an empty dict -- so without these a broken scrape would publish a gutted guideline
# to every assistant.
MIN_DOMAINS = 12
MIN_RECOMMENDATIONS = 90
MIN_CORPUS_CHARS = 100_000

SINK_CORPUS = "corpus"
SINK_VECTOR_STORE = "vectorStore"
SINK_PAIRS = "pairs"
ALL_SINKS: Tuple[str, ...] = (SINK_CORPUS, SINK_VECTOR_STORE, SINK_PAIRS)


class RefreshError(RuntimeError):
    """An upstream call failed. Web layers map this to a 502; the CLI just prints it."""


def _fuelix_request(method: str, path: str, **kwargs) -> Any:
    import requests

    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        raise RefreshError("FUELIX_API_KEY is not set.")

    base = (os.getenv("FUELIX_API_BASE_URL") or "https://api.fuelix.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"

    response = requests.request(method, f"{base}{path}", headers=headers, timeout=90, **kwargs)
    if response.status_code >= 400:
        raise RefreshError(
            f"Fuel IX {method} {path} -> {response.status_code}: {response.text[:300]}"
        )
    return response.json()


# --- sink 1: recommendations -> copilot instructions ------------------------------------------


def gate_corpus(markdown: str, domain_count: int) -> List[str]:
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


def sink_corpus(*, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Scrape the guideline; if it differs from what Supabase says we published, push it.

    The stored corpus is the comparison, not the assistants' own instructions. That makes the
    common case -- nothing changed -- one Supabase read instead of six Fuel IX reads, and it
    gives a durable record of what was published and when.

    The trade-off is that an assistant edited outside this system is not detected while the
    corpus is unchanged. `force` exists for exactly that: it re-pushes and re-verifies
    regardless of the stored hash.

    `dry_run` scrapes and compares but touches no assistant, so a reviewer can see whether
    tonight's run would push before deciding to push it now.
    """
    from scripts.content_pipeline.corpus import analyze, fetch_corpus
    from scripts.content_pipeline.state import digest, load_corpus_state, save_corpus_state

    corpus_markdown, domains = fetch_corpus()
    problems = gate_corpus(corpus_markdown, len(domains))
    if problems:
        # Deliberately not an exception: the run did its job by refusing. Reporting the reason
        # keeps the failure visible without pretending the site is down.
        return {"ok": False, "action": "aborted", "problems": problems, "domains": len(domains)}

    stats = analyze(corpus_markdown)
    fresh_hash = digest(corpus_markdown)
    state = load_corpus_state()
    if state.error:
        return {"ok": False, "action": "aborted", "problems": [f"state: {state.error}"]}

    measurements = {
        "hash": fresh_hash,
        "previousHash": state.content_hash or None,
        "domains": len(domains),
        "recommendations": len(stats.recommendation_numbers),
        "corpusChars": len(corpus_markdown),
    }

    if state.found and state.content_hash == fresh_hash and not force:
        return {
            "ok": True,
            "action": "no-change",
            "publishedAt": state.published_at,
            **measurements,
        }

    if dry_run:
        # Named for what it is rather than reported as a change: nothing was written, and the
        # reason the run would push ("the corpus moved" vs "you asked us to") is the useful part.
        return {
            "ok": True,
            "action": "would-patch",
            "reason": "forced" if force and state.content_hash == fresh_hash else "corpus changed",
            "assistants": _assistant_roster(),
            **measurements,
        }

    from core.fuelix_chat import ASSISTANT_ENV_BY_USER_TYPE, normalize_user_type
    from core.prompts import build_fuelix_assistant_instructions

    results: List[Dict[str, Any]] = []
    patched = 0
    for role, env_var in ASSISTANT_ENV_BY_USER_TYPE.items():
        assistant_id = (os.getenv(env_var) or "").strip()
        if not assistant_id:
            results.append({"role": role, "status": "skipped", "reason": f"{env_var} not set"})
            continue

        desired = build_fuelix_assistant_instructions(
            normalize_user_type(role), recommendations_markdown=corpus_markdown
        )
        current = _fuelix_request("GET", f"/assistants/{assistant_id}") or {}
        if (current.get("instructions") or "") == desired:
            results.append({"role": role, "status": "already-current"})
            continue

        _fuelix_request("POST", f"/assistants/{assistant_id}", json={"instructions": desired})
        # Read back rather than trusting the write: a partial patch would otherwise be reported
        # as success, and the stored hash would then claim we published something we did not.
        after = _fuelix_request("GET", f"/assistants/{assistant_id}") or {}
        landed = (after.get("instructions") or "") == desired
        patched += 1 if landed else 0
        results.append({"role": role, "status": "patched" if landed else "patch-not-verified"})

    failed = [item for item in results if item["status"] == "patch-not-verified"]
    if not failed:
        # Only recorded once every assistant verified. Saving on a partial push would make the
        # next run believe it was already published and skip the repair.
        save_corpus_state(
            corpus_markdown,
            meta={
                "domains": len(domains),
                "recommendations": len(stats.recommendation_numbers),
                "characters": stats.characters,
            },
        )

    return {
        "ok": not failed,
        "action": "patched" if patched else "verified",
        "patched": patched,
        "assistants": results,
        **measurements,
    }


def _assistant_roster() -> List[Dict[str, Any]]:
    """Which copilots a real run would touch. Read from env, so a missing id shows up in a preview."""
    from core.fuelix_chat import ASSISTANT_ENV_BY_USER_TYPE

    return [
        {
            "role": role,
            "status": "would-patch" if (os.getenv(env_var) or "").strip() else "skipped",
            **({} if (os.getenv(env_var) or "").strip() else {"reason": f"{env_var} not set"}),
        }
        for role, env_var in ASSISTANT_ENV_BY_USER_TYPE.items()
    ]


# --- sinks 2 and 3: one fetch, two consumers ---------------------------------------------------
#
# Both read the English tools listing, so the pages are fetched once by the orchestrator and
# handed to each. They used to fetch independently, which meant pulling the same page twice per
# run -- and, worse, two sinks could act on two different snapshots of a site that changed
# between them.


def sink_vector_store(fetched: Any = None, *, dry_run: bool = False) -> Dict[str, Any]:
    from scripts.content_pipeline.vector_store import sync

    english = fetched.english_tools if fetched is not None else None
    return sync(dry_run=dry_run, english_tools=english).as_dict()


def sink_pairs(fetched: Any = None, *, dry_run: bool = False) -> Dict[str, Any]:
    from scripts.content_pipeline.pairing import sync_pairs

    return sync_pairs(dry_run=dry_run, fetched=fetched).as_dict()


# --- did anything actually happen? -------------------------------------------------------------


def _sink_changed(name: str, result: Dict[str, Any]) -> bool:
    """Whether this sink moved something a person would care about.

    Kept out of the sink bodies because "changed" means something different in each: a list of
    URLs for two of them, a verb for the third.
    """
    if name == SINK_CORPUS:
        return result.get("action") in ("patched", "would-patch")
    return bool(result.get("added") or result.get("removed") or result.get("updated")
                or result.get("retired"))


def summarize(payload: Dict[str, Any]) -> bool:
    sinks = payload.get("sinks") or {}
    return any(_sink_changed(name, result) for name, result in sinks.items())


# --- entrypoint ---------------------------------------------------------------------------------


def run_refresh(
    *,
    force: bool = False,
    dry_run: bool = False,
    sinks: Sequence[str] = ALL_SINKS,
    trigger: str = TRIGGER_CRON,
    record: bool = True,
) -> Dict[str, Any]:
    """Run the sinks and return one report. Raises `RunInFlight` if another run holds the lease.

    The lease covers dry runs too. A preview's whole value is showing what a real run would do,
    and a preview taken while another run is mutating the same tables is describing a state that
    no longer exists by the time it is read.

    Every sink failure is caught and reported rather than raised: the caller gets a result for
    each sink no matter how the others went, which is the property that lets a broken French
    listing coexist with a genuine guideline update.
    """
    started = time.perf_counter()

    run = None
    lease_error: Optional[str] = None
    if record:
        try:
            run = claim_run(trigger=trigger, dry_run=dry_run, forced=force)
        except RunInFlight:
            raise
        except StateError as exc:
            # No lease and no history row, but the run itself is still worth doing: every sink
            # compares against this same store, so if it is truly unreachable they will each
            # say so, and if it is not then this was a blip worth surviving.
            lease_error = str(exc)

    selected = [name for name in ALL_SINKS if name in set(sinks)]

    # One fetch of the tool and resource listings, shared by both listing-driven sinks.
    fetched = None
    fetch_error = None
    if SINK_VECTOR_STORE in selected or SINK_PAIRS in selected:
        try:
            from scripts.content_pipeline.fetch import fetch_all

            fetched = fetch_all()
        except Exception as exc:
            fetch_error = f"{type(exc).__name__}: {exc}"

    runners: Dict[str, Callable[[], Dict[str, Any]]] = {
        SINK_CORPUS: lambda: sink_corpus(force=force, dry_run=dry_run),
        SINK_VECTOR_STORE: lambda: sink_vector_store(fetched, dry_run=dry_run),
        SINK_PAIRS: lambda: sink_pairs(fetched, dry_run=dry_run),
    }

    results: Dict[str, Any] = {}
    for name in selected:
        try:
            results[name] = runners[name]()
        except Exception as exc:
            results[name] = {
                "ok": False,
                "action": "error",
                "problems": [f"{type(exc).__name__}: {exc}"],
            }

    ok = all(result.get("ok") for result in results.values()) and not fetch_error
    payload: Dict[str, Any] = {
        "ok": ok,
        "sinks": results,
        "dryRun": dry_run,
        "forced": force,
        "trigger": trigger,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    if fetch_error:
        payload["fetchError"] = fetch_error
    if lease_error:
        payload["leaseError"] = lease_error

    payload["changed"] = summarize(payload)
    payload["runId"] = run.id if run else None
    payload["startedAt"] = run.started_at if run else None

    if run is not None:
        try:
            finish_run(run.id, ok=ok, changed=payload["changed"], report=payload)
        except StateError as exc:
            # The work is done and the report is in hand; failing to file it must not turn a
            # successful run into an error. The row is swept as abandoned later.
            payload["leaseError"] = f"could not record the run: {exc}"

    return payload
