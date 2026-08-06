"""Supabase state: the "what we have" side of every comparison the pipeline makes.

Three records, one per sink, described in scripts/sql/content_pipeline.sql:

    content_state       the recommendations corpus we last gave the copilots
    vector_store_files  the Living Guideline Tools link set, and the file each link owns
    resource_pairs      the EN->FR pairing table the app resolves against

Plus a fourth that records the runs themselves (scripts/sql/pipeline_runs.sql):

    pipeline_runs       what each refresh did, and the lease stopping two from overlapping

Why Supabase and not files: a Vercel function cannot write to disk, so a committed file can
never record what a deployed run actually published. Every file-based record this replaces had
already drifted from reality.

Reads degrade rather than raise. A store outage must leave the app serving its last known
links, not none -- so `load_*` returns an empty/errored result and callers decide. Writes raise,
because a write that silently did nothing is how state quietly diverges.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from scripts.content_pipeline.urls import normalize_url

# Short on purpose: the public /api/resource-links path reads this store, and a hanging
# database must not be what makes the request time out.
_TIMEOUT = 15

SINK_CORPUS = "corpus"

ORIGIN_AUTO = "auto"
ORIGIN_MANUAL = "manual"

UPLOADED_ADOPTED = "adopted"
UPLOADED_PIPELINE = "pipeline"


class StateError(RuntimeError):
    """Raised by the write paths. Reads return an errored result instead.

    Carries the HTTP status and body so a caller can tell one failure from another --
    `claim_run` needs to distinguish "someone else is already running" (a unique violation,
    which is the lease working) from "the database is unreachable" (which is not).
    """

    def __init__(self, message: str, *, status: Optional[int] = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class RunInFlight(StateError):
    """A refresh is already running. Raised by `claim_run` only."""


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


# --- transport -------------------------------------------------------------------------------


def _config() -> Tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not url or not key:
        raise StateError("SUPABASE_URL and SUPABASE_KEY must be set.")
    return url, key


def is_configured() -> bool:
    try:
        _config()
    except StateError:
        return False
    return True


def _request(method: str, table: str, query: str = "", *, json_body: Any = None, prefer: str = "") -> Any:
    import requests

    url, key = _config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    try:
        response = requests.request(
            method, f"{url}/rest/v1/{table}{query}",
            headers=headers, json=json_body, timeout=_TIMEOUT,
        )
    except Exception as exc:
        raise StateError(f"Could not reach Supabase: {type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        detail = (response.text or "")[:300]
        if response.status_code in (400, 404) and "PGRST205" in detail:
            raise StateError(
                f"Table `{table}` is missing -- run the matching file in scripts/sql/ in the "
                f"Supabase SQL editor. ({response.status_code}: {detail})",
                status=response.status_code,
                body=detail,
            )
        raise StateError(
            f"Supabase {method} {table} -> {response.status_code}: {detail}",
            status=response.status_code,
            body=detail,
        )

    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _eq(value: str) -> str:
    """Percent-encode a PostgREST filter value for a text column.

    Deliberately NOT double-quoted. The obvious-looking `eq."<value>"` form -- which the old
    resource_overrides code used -- does not work against this PostgREST: the quotes are read as
    part of the value, so `sink=eq."corpus"` matches nothing while `sink=eq.corpus` matches.
    Verified against the live database both ways.

    That failure mode is silent and one-directional, which is what made it worth a comment: a
    filtered SELECT returns [] and a filtered DELETE removes nothing, both with a 200. Nothing
    errors; the state simply never changes.

    Percent-encoding alone is sufficient. Of the characters URLs carry, only `,` is PostgREST
    syntax (the `in.()` separator) and encoding turns it into %2C; `.` is only special as the
    operator separator, which has already been consumed by the time the value is parsed.
    """
    return quote(value, safe="")


# --- 1. corpus state -------------------------------------------------------------------------


@dataclass
class CorpusState:
    content: str = ""
    content_hash: str = ""
    published_at: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    found: bool = False
    error: Optional[str] = None


def load_corpus_state(sink: str = SINK_CORPUS) -> CorpusState:
    """What we last published. Never raises -- an unreadable store means "unknown", not "empty"."""
    try:
        rows = _request("GET", "content_state", f"?sink=eq.{_eq(sink)}&select=*") or []
    except StateError as exc:
        return CorpusState(error=str(exc))
    if not isinstance(rows, list) or not rows:
        return CorpusState()
    row = rows[0]
    return CorpusState(
        content=row.get("content") or "",
        content_hash=row.get("content_hash") or "",
        published_at=str(row.get("published_at") or ""),
        meta=row.get("meta") or {},
        found=True,
    )


def save_corpus_state(content: str, *, sink: str = SINK_CORPUS, meta: Optional[Dict[str, Any]] = None) -> str:
    """Record what was just published. Returns the stored hash."""
    content_hash = digest(content)
    _request(
        "POST", "content_state", "",
        json_body={
            "sink": sink,
            "content": content,
            "content_hash": content_hash,
            "meta": meta or {},
            "updated_at": "now()",
            "published_at": "now()",
        },
        prefer="resolution=merge-duplicates",
    )
    return content_hash


# --- 2. vector store files -------------------------------------------------------------------


@dataclass
class StoredFile:
    source_url: str
    title: str = ""
    store_id: str = ""
    file_id: str = ""
    filename: str = ""
    uploaded_by: str = UPLOADED_PIPELINE

    @property
    def auto_removable(self) -> bool:
        """Whether a refresh run may take this file out of the store unattended.

        Only what the pipeline uploaded. Two facts about the Fuel IX API force the asymmetry,
        both verified against the live service rather than assumed:

        - `DELETE /vector_stores/{store}/files/{id}` destroys the file object outright. There
          is no detach-without-delete, so "remove from the store" and "delete forever" are the
          same operation.
        - `GET /files/{id}/content` returns 404. A file's bytes cannot be read back, so it
          cannot be archived before removal either.

        A pipeline file is re-fetchable from its source URL, so removing one by mistake costs a
        re-download. The 27 adopted files are hand-made .txt conversions that exist nowhere
        else -- not in git, not on the site in that form. Removing one is unrecoverable, so the
        pipeline reports it and leaves it for a person.
        """
        return self.uploaded_by == UPLOADED_PIPELINE


@dataclass
class StoredFileSet:
    files: List[StoredFile] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.error is None

    def by_url(self) -> Dict[str, StoredFile]:
        return {normalize_url(item.source_url): item for item in self.files}


def load_vector_store_files() -> StoredFileSet:
    """The stored link set. This is what a fresh scrape is compared against."""
    try:
        rows = _request("GET", "vector_store_files", "?select=*") or []
    except StateError as exc:
        return StoredFileSet(error=str(exc))
    if not isinstance(rows, list):
        return StoredFileSet(error="Supabase returned an unexpected payload.")
    return StoredFileSet(
        files=[
            StoredFile(
                source_url=str(row.get("source_url") or ""),
                title=row.get("title") or "",
                store_id=str(row.get("store_id") or ""),
                file_id=str(row.get("file_id") or ""),
                filename=row.get("filename") or "",
                uploaded_by=str(row.get("uploaded_by") or UPLOADED_PIPELINE),
            )
            for row in rows
            if isinstance(row, dict) and row.get("source_url")
        ]
    )


def record_vector_store_file(entry: StoredFile) -> None:
    _request(
        "POST", "vector_store_files", "",
        json_body={
            "source_url": entry.source_url,
            "title": entry.title or None,
            "store_id": entry.store_id,
            "file_id": entry.file_id,
            "filename": entry.filename or None,
            "uploaded_by": entry.uploaded_by,
            "updated_at": "now()",
        },
        prefer="resolution=merge-duplicates",
    )


def forget_vector_store_file(source_url: str) -> None:
    _request("DELETE", "vector_store_files", f"?source_url=eq.{_eq(source_url)}")


# --- 3. resource pairs -----------------------------------------------------------------------


@dataclass
class StoredPair:
    en_url: str
    fr_url: Optional[str] = None
    fr_title: str = ""
    origin: str = ORIGIN_AUTO
    source: str = ""
    note: str = ""
    created_at: str = ""

    @property
    def suppressed(self) -> bool:
        """A row with no French URL means "this tool has no counterpart" -- do not re-propose."""
        return not self.fr_url

    @property
    def locked(self) -> bool:
        """Manual decisions are never overwritten or retired by a refresh run."""
        return self.origin == ORIGIN_MANUAL

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enUrl": self.en_url,
            "frUrl": self.fr_url,
            "frTitle": self.fr_title,
            "origin": self.origin,
            "source": self.source,
            "note": self.note,
            "createdAt": self.created_at,
        }


@dataclass
class PairTable:
    pairs: List[StoredPair] = field(default_factory=list)
    error: Optional[str] = None
    configured: bool = True

    @property
    def available(self) -> bool:
        return self.error is None

    def by_url(self) -> Dict[str, StoredPair]:
        return {normalize_url(item.en_url): item for item in self.pairs}

    def resolvable(self) -> List[StoredPair]:
        """Rows that actually point somewhere -- suppressions excluded."""
        return [item for item in self.pairs if not item.suppressed]

    def suppressed(self) -> set:
        return {normalize_url(item.en_url) for item in self.pairs if item.suppressed}


def load_resource_pairs() -> PairTable:
    """The live pairing table. Never raises; the app falls back to its bundled map."""
    if not is_configured():
        return PairTable(error="Supabase is not configured.", configured=False)
    try:
        rows = _request("GET", "resource_pairs", "?select=*&order=en_url.asc") or []
    except StateError as exc:
        return PairTable(error=str(exc))
    if not isinstance(rows, list):
        return PairTable(error="Supabase returned an unexpected payload.")
    return PairTable(
        pairs=[
            StoredPair(
                en_url=str(row.get("en_url") or ""),
                fr_url=row.get("fr_url") or None,
                fr_title=row.get("fr_title") or "",
                origin=str(row.get("origin") or ORIGIN_AUTO),
                source=row.get("source") or "",
                note=row.get("note") or "",
                created_at=str(row.get("created_at") or ""),
            )
            for row in rows
            if isinstance(row, dict) and row.get("en_url")
        ]
    )


def upsert_pair(pair: StoredPair) -> None:
    """Write a pairing, replacing whatever was there. Used by the admin UI."""
    _request(
        "POST", "resource_pairs", "",
        json_body={
            "en_url": pair.en_url,
            "fr_url": pair.fr_url,
            "fr_title": pair.fr_title or None,
            "origin": pair.origin,
            "source": pair.source or None,
            "note": pair.note or None,
            "updated_at": "now()",
        },
        prefer="resolution=merge-duplicates",
    )


def upsert_auto_pair(pair: StoredPair) -> None:
    """Write a derived pairing without ever overwriting a human's decision.

    Two calls rather than one upsert, because an upsert cannot be made conditional on a column
    it is about to overwrite. The refresh job reads the table and then writes it, and a reviewer
    can make a row manual in between -- a plain upsert would silently flip it back to 'auto' and
    undo them.

        insert  ... ignore-duplicates   creates the row only if nothing holds that key
        patch   ... &origin=eq.auto     updates only while the row is still derived

    Both filters are applied by the database, so the decision cannot be stale by the time it
    lands. A row that turned manual between the two simply matches neither.
    """
    body = {
        "fr_url": pair.fr_url,
        "fr_title": pair.fr_title or None,
        "origin": ORIGIN_AUTO,
        "source": pair.source or None,
        "note": pair.note or None,
        "updated_at": "now()",
    }
    _request(
        "POST", "resource_pairs", "",
        json_body={"en_url": pair.en_url, **body},
        prefer="resolution=ignore-duplicates",
    )
    _request(
        "PATCH", "resource_pairs",
        f"?en_url=eq.{_eq(pair.en_url)}&origin=eq.{ORIGIN_AUTO}",
        json_body=body,
    )


def delete_pair(en_url: str) -> None:
    _request("DELETE", "resource_pairs", f"?en_url=eq.{_eq(en_url)}")


def delete_auto_pair(en_url: str) -> None:
    """Retire a derived pair, leaving a manual decision for the same tool untouched.

    The origin filter is the guard, applied server-side rather than by reading first and then
    deleting: between those two steps a reviewer could have made the row manual.
    """
    _request(
        "DELETE", "resource_pairs",
        f"?en_url=eq.{_eq(en_url)}&origin=eq.{ORIGIN_AUTO}",
    )


# --- 4. refresh runs ---------------------------------------------------------------------------

TRIGGER_CRON = "cron"
TRIGGER_ADMIN = "admin"
TRIGGER_CLI = "cli"

# How long a row may sit unfinished before a later run treats it as abandoned. Comfortably
# above the 300s Vercel function ceiling, so a run that is merely slow is never swept out from
# under itself; a function killed mid-run leaves its row open forever without this.
STALE_RUN_MINUTES = 15

# PostgREST's unique-violation code. This is the lease doing its job, not an outage.
_UNIQUE_VIOLATION = "23505"


@dataclass
class PipelineRun:
    id: Optional[int] = None
    trigger: str = TRIGGER_CRON
    dry_run: bool = False
    forced: bool = False
    started_at: str = ""
    finished_at: str = ""
    ok: Optional[bool] = None
    changed: Optional[bool] = None
    report: Dict[str, Any] = field(default_factory=dict)

    @property
    def in_flight(self) -> bool:
        return not self.finished_at

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "dryRun": self.dry_run,
            "forced": self.forced,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at or None,
            "ok": self.ok,
            "changed": self.changed,
            "inFlight": self.in_flight,
            "report": self.report,
        }


@dataclass
class RunHistory:
    runs: List[PipelineRun] = field(default_factory=list)
    error: Optional[str] = None
    configured: bool = True

    @property
    def available(self) -> bool:
        return self.error is None

    @property
    def latest(self) -> Optional[PipelineRun]:
        return self.runs[0] if self.runs else None


def _run_from_row(row: Dict[str, Any]) -> PipelineRun:
    return PipelineRun(
        id=row.get("id"),
        trigger=str(row.get("trigger") or TRIGGER_CRON),
        dry_run=bool(row.get("dry_run")),
        forced=bool(row.get("forced")),
        started_at=str(row.get("started_at") or ""),
        finished_at=str(row.get("finished_at") or ""),
        ok=row.get("ok"),
        changed=row.get("changed"),
        report=row.get("report") or {},
    )


def sweep_stale_runs(minutes: int = STALE_RUN_MINUTES) -> int:
    """Close any run left open longer than `minutes`, so the lease cannot deadlock.

    A function killed at the platform's duration ceiling never reaches its own `finally`, and
    its row would then block every later run forever. Closed as failed rather than deleted:
    "we started this and never heard back" is a real outcome and worth seeing in the history.

    The cutoff is computed here rather than in the filter because PostgREST compares against a
    literal, not an expression -- there is no `lt.now()-interval` to write.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = _request(
        "PATCH", "pipeline_runs",
        f"?finished_at=is.null&started_at=lt.{_eq(cutoff)}",
        json_body={
            "finished_at": "now()",
            "ok": False,
            "changed": False,
            "report": {"abandoned": f"no result recorded within {minutes} minutes"},
        },
        prefer="return=representation",
    )
    return len(rows) if isinstance(rows, list) else 0


def claim_run(*, trigger: str, dry_run: bool = False, forced: bool = False) -> PipelineRun:
    """Take the lease and open a run row. Raises `RunInFlight` if another run holds it.

    Claiming is the insert itself, not a read followed by an insert: the partial unique index
    in scripts/sql/pipeline_runs.sql allows exactly one row with a null `finished_at`, so two
    callers racing produce one success and one 23505. Nothing here has to be atomic in Python.
    """
    try:
        sweep_stale_runs()
    except StateError:
        # A failed sweep is not a reason to refuse the run. Either the claim below succeeds
        # anyway, or it hits the lease and the caller is told a run is already in flight.
        pass

    try:
        rows = _request(
            "POST", "pipeline_runs", "",
            json_body={"trigger": trigger, "dry_run": dry_run, "forced": forced},
            prefer="return=representation",
        )
    except StateError as exc:
        if _UNIQUE_VIOLATION in (exc.body or ""):
            raise RunInFlight(
                "A refresh is already running. Wait for it to finish before starting another.",
                status=exc.status, body=exc.body,
            ) from exc
        raise

    if not isinstance(rows, list) or not rows:
        raise StateError("Supabase accepted the run but returned no row to track it by.")
    return _run_from_row(rows[0])


def finish_run(
    run_id: Optional[int], *, ok: bool, changed: bool, report: Optional[Dict[str, Any]] = None
) -> None:
    """Close a run and record what it did. Releasing the lease is the side effect that matters."""
    if run_id is None:
        return
    _request(
        "PATCH", "pipeline_runs", f"?id=eq.{run_id}",
        json_body={
            "finished_at": "now()",
            "ok": ok,
            "changed": changed,
            "report": report or {},
        },
    )


def load_recent_runs(limit: int = 5) -> RunHistory:
    """The newest runs, any trigger. Never raises -- history is context, not the answer."""
    if not is_configured():
        return RunHistory(error="Supabase is not configured.", configured=False)
    try:
        rows = _request(
            "GET", "pipeline_runs",
            f"?select=*&order=started_at.desc&limit={max(1, int(limit))}",
        ) or []
    except StateError as exc:
        return RunHistory(error=str(exc))
    if not isinstance(rows, list):
        return RunHistory(error="Supabase returned an unexpected payload.")
    return RunHistory(runs=[_run_from_row(row) for row in rows if isinstance(row, dict)])
