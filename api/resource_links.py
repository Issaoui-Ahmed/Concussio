"""Serve the EN->FR resource link map, and the admin view that curates it.

The map is a straight read of the `resource_pairs` table. Nothing is scraped or matched on this
path: the refresh cron does that work daily and writes the result, so answering a request is one
indexed SELECT rather than three page fetches and a matcher run.

That is the change. This endpoint used to re-derive the map live on every cache miss -- fetching
the English tools page and both French listings, then matching -- which is why it needed a
15-minute CDN cache to stay affordable. The table now holds what those fetches produced.

    origin='auto'    written by the refresh cron from an exact tool-number match.
    origin='manual'  written by a person in /admin/scraping. The cron never touches these.

A row with a null fr_url is a suppression: a reviewer said this tool has no French counterpart,
so it must resolve to nothing rather than being re-proposed.

If the table cannot be read the response carries no pairs, and the frontend keeps the map it
bundled at build time -- stale links rather than missing ones. See lib/i18n/resourceLinkStore.ts.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()

# The table is the authority and a reviewer must see their own edit take effect, so this is much
# shorter than the old scrape-backed value. It costs a database read, not three page fetches.
CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=604800"


def _build_map() -> Dict[str, Any]:
    from scripts.content_pipeline.state import load_resource_pairs

    table = load_resource_pairs()

    pairs: Dict[str, Dict[str, str]] = {}
    for row in table.resolvable():
        entry: Dict[str, str] = {"url": row.fr_url or ""}
        if row.fr_title:
            entry["title"] = row.fr_title
        pairs[row.en_url] = entry

    errors: List[str] = []
    if table.error:
        errors.append(table.error)

    return {
        "pairs": pairs,
        "meta": {
            "total": len(pairs),
            "auto": sum(1 for row in table.resolvable() if not row.locked),
            "manual": sum(1 for row in table.resolvable() if row.locked),
            "suppressed": len(table.suppressed()),
            "errors": errors,
        },
    }


@app.get("/api/resource-links")
def resource_links() -> JSONResponse:
    started = time.perf_counter()
    payload = _build_map()
    payload["meta"]["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return JSONResponse(payload, headers={"Cache-Control": CACHE_CONTROL})


# --- admin report -------------------------------------------------------------------------
#
# The map above is what the app consumes. This is the human view of the same data, shaped for a
# two-column workbench: every English Living Guideline Tool, every French resource, and the
# links between them as separate lists.
#
# This one DOES scrape, deliberately. A reviewer pairing two documents needs to see what the
# site lists right now, including anything published since the last cron run -- and it is a
# no-store admin view, so the cost lands on one person rather than every request.

ORIGIN_MANUAL = "manual"
ORIGIN_AUTO = "auto"


def _is_pdf(url: str) -> bool:
    return (url or "").split("?")[0].rstrip("/").lower().endswith(".pdf")


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(url or "").netloc or "").lower().removeprefix("www.")


def _resource_entry(resource: Any) -> Dict[str, Any]:
    return {
        "title": resource.title,
        "url": resource.url,
        "toolNumber": resource.tool_number,
        "group": getattr(resource, "group", "") or "",
        "sourcePage": getattr(resource, "source_page", "") or "",
        "host": _host(resource.url),
        "isPdf": _is_pdf(resource.url),
        "offListing": False,
    }


def _placeholder_entry(url: str, title: str = "") -> Dict[str, Any]:
    """A resource referenced by a row but absent from the live listing.

    Means the site moved a URL out from under a recorded pairing. The row still renders --
    flagged -- rather than vanishing from the one view that could fix it.
    """
    return {
        "title": title,
        "url": url,
        "toolNumber": None,
        "group": "",
        "sourcePage": "",
        "host": _host(url),
        "isPdf": _is_pdf(url),
        "offListing": True,
    }


def _build_report() -> Dict[str, Any]:
    from scripts.content_pipeline.fetch import TOOLS_RESOURCES_URL, fetch_all, living_tools
    from scripts.content_pipeline.match import TIER_TOOL_NUMBER, match_resources
    from scripts.content_pipeline.pairs import Pair, PairSet
    from scripts.content_pipeline.state import load_resource_pairs
    from scripts.content_pipeline.urls import normalize_url

    table = load_resource_pairs()
    fetched = fetch_all()
    english_tools = living_tools(fetched.english_tools)
    errors = list(fetched.errors)
    if table.error:
        errors.append(f"pair table: {table.error}")

    # Whether the "Living Guideline Tools" heading could be read at all, reported separately
    # from the generic error list so the UI can say so where the tools would have been. An
    # empty English column otherwise looks like "this site has no tools" rather than "we could
    # not find the heading" -- and since `living_tools` deliberately returns nothing when the
    # heading is missing, that distinction is now the difference between a quiet blank column
    # and a broken scrape.
    heading_found = bool(english_tools)
    english_source = {
        "ok": heading_found,
        "count": len(english_tools),
        "listedOnPage": len(fetched.english_tools),
        "heading": "Living Guideline Tools",
        "sourcePage": TOOLS_RESOURCES_URL,
        "message": None
        if heading_found
        else (
            f"The “Living Guideline Tools” heading could not be found on "
            f"{TOOLS_RESOURCES_URL}, so no English tools could be read. "
            f"{len(fetched.english_tools)} other links were listed on the page but are not part "
            f"of the guideline, and are deliberately ignored. Nothing has been changed: the "
            f"nightly refresh refuses to add or remove anything while this is the case."
        ),
    }

    rows = table.by_url()

    links: List[Dict[str, Any]] = []
    for row in table.resolvable():
        links.append(
            {
                "enUrl": row.en_url,
                "frUrl": row.fr_url,
                "frTitle": row.fr_title or "",
                "origin": ORIGIN_MANUAL if row.locked else ORIGIN_AUTO,
                "note": row.note or "",
                # Rows are keyed by English URL now, so the row's own key is its identifier.
                "overrideId": row.en_url if row.locked else None,
                "createdAt": row.created_at or None,
            }
        )

    # What the matcher would propose for tools with no row at all. Between cron runs the site
    # can publish a translation the table has not caught up with, and this is where a reviewer
    # sees it. Suppressed tools are excluded -- re-suggesting one is how a removal undoes itself.
    decided = set(rows)
    claimed = PairSet(
        pairs=[Pair(en_url=r.en_url, fr_url=r.fr_url or "") for r in table.resolvable()]
    )
    candidates = [t for t in english_tools if normalize_url(t.url) not in decided]
    result = match_resources(candidates, fetched.french_resources, claimed)
    for proposal in result.auto:
        if proposal.tier != TIER_TOOL_NUMBER:
            continue
        links.append(
            {
                "enUrl": proposal.en.url,
                "frUrl": proposal.fr.url,
                "frTitle": proposal.fr.title or "",
                "origin": ORIGIN_AUTO,
                "note": proposal.evidence,
                "overrideId": None,
                "createdAt": None,
                "proposed": True,
            }
        )

    english: Dict[str, Dict[str, Any]] = {}
    for resource in english_tools:
        english.setdefault(normalize_url(resource.url), _resource_entry(resource))

    french: Dict[str, Dict[str, Any]] = {}
    for resource in fetched.french_resources:
        french.setdefault(normalize_url(resource.url), _resource_entry(resource))

    # Anything a link references must exist in its column or the UI holds a dangling reference
    # and silently drops the row.
    for link in links:
        english.setdefault(normalize_url(link["enUrl"]), _placeholder_entry(link["enUrl"]))
        if link["frUrl"]:
            french.setdefault(
                normalize_url(link["frUrl"]), _placeholder_entry(link["frUrl"], link["frTitle"])
            )

    # Suppressed tools have no link row, so they would otherwise be indistinguishable from
    # never-reviewed ones. Flagging them is what stops a reviewer redoing a decision.
    suppressed = table.suppressed()
    for key, entry in english.items():
        entry["suppressed"] = key in suppressed

    english_list = sorted(english.values(), key=lambda item: (item["offListing"], _sort_key(item)))
    french_list = sorted(french.values(), key=lambda item: (item["offListing"], _sort_key(item)))

    settled = [link for link in links if not link.get("proposed")]
    linked_en = {normalize_url(link["enUrl"]) for link in links}
    linked_fr = {normalize_url(link["frUrl"]) for link in links if link["frUrl"]}

    summary = {
        "english": len(english_list),
        "french": len(french_list),
        "paired": len(settled),
        "proposed": len(links) - len(settled),
        "manual": sum(1 for link in links if link["origin"] == ORIGIN_MANUAL),
        "auto": sum(1 for link in links if link["origin"] == ORIGIN_AUTO),
        "suppressed": len(suppressed),
        "unpairedEnglish": sum(
            1 for item in english_list
            if normalize_url(item["url"]) not in linked_en and not item.get("suppressed")
        ),
        "unpairedFrench": sum(
            1 for item in french_list if normalize_url(item["url"]) not in linked_fr
        ),
        "manualOverrides": sum(1 for row in table.pairs if row.locked),
    }

    return {
        "english": english_list,
        "french": french_list,
        "links": links,
        "summary": summary,
        "englishSource": english_source,
        "store": {
            "configured": table.configured,
            "available": table.available,
            "error": table.error,
            "overrides": summary["manualOverrides"],
        },
        "authRequired": _auth_required(),
        "errors": errors,
    }


def _sort_key(item: Dict[str, Any]) -> tuple:
    """Tool number first and numerically, then title. Keeps 2.1 above 10.1."""
    number = item.get("toolNumber")
    if number:
        try:
            major, minor = (int(part) for part in str(number).split("."))
            return (0, major, minor, "")
        except ValueError:
            pass
    return (1, 0, 0, (item.get("title") or item.get("url") or "").lower())


@app.get("/api/resource-links/report")
def resource_links_report() -> JSONResponse:
    started = time.perf_counter()
    payload = _build_report()
    payload["elapsedMs"] = int((time.perf_counter() - started) * 1000)
    # No caching: this view is editable, and a reviewer must see their own change land.
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


# --- mutations ----------------------------------------------------------------------------
#
# These change which French document a clinician is sent to, so they are gated on a shared
# secret when one is configured. The gate is opt-in because /admin has no auth of its own yet:
# making it mandatory would lock the page's own controls out by default. Set ADMIN_SECRET and
# the write paths close.


def _auth_required() -> bool:
    return bool((os.getenv("ADMIN_SECRET") or "").strip())


def _require_admin(secret: Optional[str]) -> None:
    expected = (os.getenv("ADMIN_SECRET") or "").strip()
    if not expected:
        return
    if (secret or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin secret.")


def _store_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


class PairRequest(BaseModel):
    enUrl: str
    frUrl: str
    frTitle: str = ""
    note: str = ""


@app.post("/api/resource-links/pairs")
def create_pair(
    payload: PairRequest, x_admin_secret: Optional[str] = Header(default=None)
) -> Dict[str, Any]:
    """Record a human's EN->FR decision. Written as origin='manual', so the cron will not touch it."""
    _require_admin(x_admin_secret)
    from scripts.content_pipeline.state import ORIGIN_MANUAL as MANUAL, StateError, StoredPair, upsert_pair
    from scripts.content_pipeline.urls import normalize_url

    en_url = (payload.enUrl or "").strip()
    fr_url = (payload.frUrl or "").strip()
    if not en_url or not fr_url:
        raise HTTPException(status_code=400, detail="Both an English and a French URL are required.")
    if normalize_url(en_url) == normalize_url(fr_url):
        raise HTTPException(status_code=400, detail="A resource cannot be paired with itself.")

    pair = StoredPair(
        en_url=en_url, fr_url=fr_url, fr_title=payload.frTitle, origin=MANUAL,
        source="admin", note=payload.note,
    )
    try:
        upsert_pair(pair)
    except StateError as exc:
        raise _store_error(exc) from exc
    return {"ok": True, "pair": pair.as_dict()}


class UnpairRequest(BaseModel):
    enUrl: str
    note: str = ""


@app.post("/api/resource-links/unpair")
def unpair(
    payload: UnpairRequest, x_admin_secret: Optional[str] = Header(default=None)
) -> Dict[str, Any]:
    """Remove whatever French link an English tool has, from any source.

    Recorded as a manual row with a null French URL rather than a delete, because a plain delete
    would let the next cron run re-derive the very pairing the reviewer just rejected.
    """
    _require_admin(x_admin_secret)
    from scripts.content_pipeline.state import ORIGIN_MANUAL as MANUAL, StateError, StoredPair, upsert_pair

    en_url = (payload.enUrl or "").strip()
    if not en_url:
        raise HTTPException(status_code=400, detail="An English URL is required.")

    pair = StoredPair(en_url=en_url, fr_url=None, origin=MANUAL, source="admin", note=payload.note)
    try:
        upsert_pair(pair)
    except StateError as exc:
        raise _store_error(exc) from exc
    return {"ok": True, "pair": pair.as_dict()}


@app.post("/api/resource-links/auto-pair")
def auto_pair(x_admin_secret: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Run the matcher now instead of waiting for the nightly cron.

    Identical to what the cron does, so this adds nothing a scheduled run would not; it just
    makes the result visible immediately. Manual rows are untouched.
    """
    _require_admin(x_admin_secret)
    from scripts.content_pipeline.pairing import sync_pairs

    report = sync_pairs(dry_run=False)
    if report.problems:
        raise HTTPException(status_code=502, detail="; ".join(report.problems))
    return {
        "ok": report.ok,
        "added": len(report.added),
        "updated": len(report.updated),
        "retired": len(report.retired),
        "skippedSuppressed": report.locked,
        "pairs": [{"enUrl": url} for url in report.added],
        "errors": report.failures,
    }


@app.delete("/api/resource-links/overrides")
def clear_overrides(x_admin_secret: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Drop every manual decision, leaving only what the matcher derives.

    Safe by construction: the next refresh re-derives every auto pair from the live listings, so
    the worst case is losing hand-made pairings, not losing the map.
    """
    _require_admin(x_admin_secret)
    from scripts.content_pipeline.state import ORIGIN_MANUAL as MANUAL, StateError, load_resource_pairs
    from scripts.content_pipeline.state import delete_pair

    table = load_resource_pairs()
    if table.error:
        raise HTTPException(status_code=502, detail=table.error)

    deleted = 0
    try:
        for row in table.pairs:
            if row.origin == MANUAL:
                delete_pair(row.en_url)
                deleted += 1
    except StateError as exc:
        raise _store_error(exc) from exc
    return {"ok": True, "deleted": deleted}
