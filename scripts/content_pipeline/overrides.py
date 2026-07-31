"""Manual pairing decisions, stored in Supabase and layered over the reviewed pair set.

Why these do not simply edit ``data/resource-pairs.json``: a Vercel function cannot write files
(``api/cron.py`` is built around the same constraint). The reviewed file therefore stays the
committed *baseline*, and everything a human does in /admin/scraping lands in a table that is
layered on top of it at request time. Two consequences worth being explicit about:

- An edit reaches real users without a redeploy, which is the point.
- The baseline alone no longer tells the whole story. ``clear_all()`` exists so it can: delete
  every row and the app is back to exactly what the committed file plus the matcher produce.
  Nothing here is destructive.

Two kinds, reusing the vocabulary the reviewed file already has:

    pair        an approved EN->FR mapping                    -> PairSet.pairs
    unpair      a suppression: this English resource has no French counterpart

``unpair`` exists because every link has to be removable from the admin page, including the ones
that come from the committed baseline or from the matcher. Neither of those can be deleted where
it lives — the baseline is a file this process cannot write, and the matcher recomputes its
matches on every request — so removal is recorded as a row that outranks both.

It is a suppression, not a veto with an opinion: it says "not this one", and clearing the store
brings the baseline and the matcher straight back. Nothing here is destructive.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from scripts.content_pipeline.pairs import Pair, PairSet
from scripts.content_pipeline.urls import normalize_url

TABLE = "resource_overrides"

KIND_PAIR = "pair"
KIND_UNPAIR = "unpair"
KINDS = (KIND_PAIR, KIND_UNPAIR)

# Marks pairs that came from this store rather than from the reviewed file or the matcher, so
# the admin view can label them and the "clear" button knows what it is clearing.
SOURCE_MANUAL = "manual"

# Short on purpose. This store is read on the public /api/resource-links path, which already
# spends most of its budget scraping; a hanging database must not be what makes it time out.
_TIMEOUT = 15


class OverrideStoreError(RuntimeError):
    """Raised by the write paths only. Reads degrade to an empty set instead."""


@dataclass
class Override:
    id: str
    kind: str
    en_url: str
    fr_url: Optional[str] = None
    fr_title: str = ""
    note: str = ""
    created_at: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "enUrl": self.en_url,
            "frUrl": self.fr_url,
            "frTitle": self.fr_title,
            "note": self.note,
            "createdAt": self.created_at,
        }


@dataclass
class OverrideSet:
    """What the store currently holds, plus whether it could be read at all.

    ``error`` being set is not the same as there being no overrides: one means "the manual
    decisions are unknown", the other means "there are none". The admin UI has to be able to
    tell those apart, or it would present a degraded read as a clean slate and invite someone
    to redo work that already exists.
    """

    overrides: List[Override] = field(default_factory=list)
    error: Optional[str] = None
    configured: bool = True

    @property
    def available(self) -> bool:
        return self.error is None

    def of_kind(self, kind: str) -> List[Override]:
        return [item for item in self.overrides if item.kind == kind]

    def suppressed(self) -> set:
        """Normalized English URLs that must not resolve to anything, whatever else says so."""
        return {normalize_url(item.en_url) for item in self.of_kind(KIND_UNPAIR)}


# --- transport -------------------------------------------------------------------------------


def _config() -> Tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not url or not key:
        raise OverrideStoreError(
            "SUPABASE_URL and SUPABASE_KEY must be set to store manual pairings."
        )
    return url, key


def is_configured() -> bool:
    try:
        _config()
    except OverrideStoreError:
        return False
    return True


def _request(method: str, query: str = "", *, json_body: Any = None, prefer: str = "") -> Any:
    import requests

    url, key = _config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    try:
        response = requests.request(
            method,
            f"{url}/rest/v1/{TABLE}{query}",
            headers=headers,
            json=json_body,
            timeout=_TIMEOUT,
        )
    except Exception as exc:
        raise OverrideStoreError(f"Could not reach Supabase: {type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        detail = (response.text or "")[:300]
        if response.status_code in (404, 400) and TABLE in detail:
            raise OverrideStoreError(
                f"Table `{TABLE}` is missing — run scripts/sql/resource_overrides.sql in the "
                f"Supabase SQL editor. ({response.status_code}: {detail})"
            )
        raise OverrideStoreError(f"Supabase {method} -> {response.status_code}: {detail}")

    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _row_to_override(row: Dict[str, Any]) -> Override:
    return Override(
        id=str(row.get("id") or ""),
        kind=str(row.get("kind") or ""),
        en_url=str(row.get("en_url") or ""),
        fr_url=row.get("fr_url") or None,
        fr_title=row.get("fr_title") or "",
        note=row.get("note") or "",
        created_at=str(row.get("created_at") or ""),
    )


# --- reads -----------------------------------------------------------------------------------


def load() -> OverrideSet:
    """Read every override. Never raises — a store outage must not blank the resource map."""
    if not is_configured():
        return OverrideSet(
            error="Supabase is not configured; manual pairings are unavailable.",
            configured=False,
        )
    try:
        rows = _request("GET", "?select=*&order=created_at.desc") or []
    except OverrideStoreError as exc:
        return OverrideSet(error=str(exc))

    if not isinstance(rows, list):
        return OverrideSet(error="Supabase returned an unexpected payload.")

    return OverrideSet(
        overrides=[
            item
            for item in (_row_to_override(row) for row in rows if isinstance(row, dict))
            if item.kind in KINDS and item.en_url
        ]
    )


# --- writes ----------------------------------------------------------------------------------


def create_pair(
    en_url: str, fr_url: str, *, fr_title: str = "", note: str = "", created_by: str = ""
) -> Override:
    """Approve an EN->FR mapping, replacing any manual mapping this resource already had.

    One French document per English URL, because that is the shape of the thing consuming it:
    ``PairSet.pair_index()`` is a dict keyed on the normalized English URL. Storing two would
    make which one wins an accident of row order.
    """
    en_url = (en_url or "").strip()
    fr_url = (fr_url or "").strip()
    if not en_url or not fr_url:
        raise OverrideStoreError("Both an English and a French URL are required.")
    if normalize_url(en_url) == normalize_url(fr_url):
        raise OverrideStoreError("A resource cannot be paired with itself.")

    _request("DELETE", f"?kind=eq.{KIND_PAIR}&en_url=eq.{_eq(en_url)}")

    rows = _request(
        "POST",
        json_body={
            "kind": KIND_PAIR,
            "en_url": en_url,
            "fr_url": fr_url,
            "fr_title": fr_title or None,
            "note": note or None,
            "created_by": created_by or None,
        },
        prefer="return=representation",
    )
    return _first(rows, "Supabase accepted the pairing but returned no row.")


def create_unpair(en_url: str, *, note: str = "", created_by: str = "") -> Override:
    """Suppress every pairing for one English resource, from any source.

    Both halves matter. Deleting the manual row alone would let the baseline pairing show
    through again, and leaving the suppression alone would let a manual row outrank it — so
    this removes the one and writes the other, in that order.
    """
    en_url = (en_url or "").strip()
    if not en_url:
        raise OverrideStoreError("An English URL is required.")

    _request("DELETE", f"?kind=eq.{KIND_PAIR}&en_url=eq.{_eq(en_url)}")
    _request("DELETE", f"?kind=eq.{KIND_UNPAIR}&en_url=eq.{_eq(en_url)}")

    rows = _request(
        "POST",
        json_body={
            "kind": KIND_UNPAIR,
            "en_url": en_url,
            "note": note or None,
            "created_by": created_by or None,
        },
        prefer="return=representation",
    )
    return _first(rows, "Supabase accepted the removal but returned no row.")


def delete(override_id: str) -> bool:
    """Remove one override. Returns False when the id was not there."""
    override_id = (override_id or "").strip()
    if not override_id:
        raise OverrideStoreError("An override id is required.")
    if not _is_uuid(override_id):
        # Not a shape this table's primary key can hold, so the row is definitively absent.
        # Answering "no such override" beats forwarding it and surfacing a cast error as a 502.
        return False
    rows = _request(
        "DELETE", f"?id=eq.{_eq_id(override_id)}", prefer="return=representation"
    )
    return bool(rows)


def clear_all() -> int:
    """Drop every manual override. Returns how many rows went.

    PostgREST refuses an unfiltered DELETE, so this filters on the one column every row has.
    """
    rows = _request(
        "DELETE",
        f"?kind=in.({','.join(KINDS)})",
        prefer="return=representation",
    )
    return len(rows) if isinstance(rows, list) else 0


def _eq(value: str) -> str:
    """Quote a PostgREST filter value for a **text** column.

    URLs carry `?`, `&` and `,` — all of which PostgREST reads as syntax. Double quotes make it
    a literal, and an embedded quote is escaped by doubling.

    Do not use this on `id`. PostgREST does not strip these quotes before Postgres casts the
    value, so a uuid column sees the literal `"…"` and rejects it (22P02). That is the whole
    reason `_eq_id` exists.
    """
    from urllib.parse import quote

    return quote(f'"{value.replace(chr(34), chr(34) * 2)}"', safe="")


def _eq_id(value: str) -> str:
    """A filter value for the **uuid** primary key — percent-encoded, deliberately unquoted.

    A uuid is hex and dashes, so it contains none of the characters `_eq`'s quoting exists to
    neutralize; the quoting would be pure downside.
    """
    from urllib.parse import quote

    return quote(value, safe="")


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _first(rows: Any, message: str) -> Override:
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return _row_to_override(rows[0])
    raise OverrideStoreError(message)


# --- layering --------------------------------------------------------------------------------


def layer(base: PairSet, overrides: OverrideSet) -> PairSet:
    """Return ``base`` with the manual pairings applied. Does not mutate the input.

    A manual pairing supersedes the baseline pairing for the same English resource — that is the
    whole mechanism. Delete the row and the baseline shows through again unchanged, which is why
    "clear all" is a safe button rather than a destructive one.
    """
    # A suppression outranks everything, including a manual pair for the same resource. The two
    # indexes are independent, so both rows can exist; deciding here rather than relying on
    # create_unpair's cleanup means the answer does not depend on write order.
    suppressed = overrides.suppressed()

    manual_pairs = [
        Pair(
            en_url=item.en_url,
            fr_url=item.fr_url or "",
            fr_title=item.fr_title or None,
            source=SOURCE_MANUAL,
            note=item.note,
        )
        for item in overrides.of_kind(KIND_PAIR)
        if item.fr_url and normalize_url(item.en_url) not in suppressed
    ]

    manual_keys = {normalize_url(pair.en_url) for pair in manual_pairs}
    pairs = manual_pairs + [
        pair
        for pair in base.pairs
        if normalize_url(pair.en_url) not in manual_keys
        and normalize_url(pair.en_url) not in suppressed
    ]

    return PairSet(pairs=pairs, french_urls=list(base.french_urls))
