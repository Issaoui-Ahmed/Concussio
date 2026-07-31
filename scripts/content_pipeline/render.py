"""Render stage: turn reviewed data into the artefacts the app consumes.

Deterministic and offline — no network here, so a render can always be re-run and diffed.

Only *data* is generated. `lib/i18n/resourceLinks.ts` holds the resolution logic and stays
hand-written and under test; this module emits `resourceLinks.data.ts` beside it. Generating
logic would mean regenerating code that has behavioural tests against it, and a scraper
should never be able to rewrite `localizeLink`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from scripts.content_pipeline.pairs import PairSet, PROJECT_ROOT
from scripts.content_pipeline.urls import normalize_url

DATA_TS_PATH = PROJECT_ROOT / "lib" / "i18n" / "resourceLinks.data.ts"
MANIFEST_PATH = PROJECT_ROOT / "data" / "content-manifest.json"

_GENERATED_BANNER = """// GENERATED FILE - DO NOT EDIT.
//
// Rendered from data/resource-pairs.json by scripts/content_pipeline/render.py, which is
// itself a snapshot of the last good scrape of pedsconcussion.com. No URL below is written by
// hand. To pick up a listing change, re-scrape:
//     python -m scripts.content_pipeline.cli refresh
//
// This is the OFFLINE FALLBACK only. At runtime /api/resource-links re-derives the same map
// from the live listings, so what ships here matters just when that endpoint is unreachable.
//
// The resolution logic lives in ./resourceLinks.ts and is hand-written; only the data below
// is generated.
"""


def _ts_string(value: str) -> str:
    """Emit a TypeScript double-quoted string literal."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )
    return f'"{escaped}"'


def render_resource_links_data(pair_set: PairSet) -> str:
    """Emit `resourceLinks.data.ts` from the reviewed pair set."""
    lines: List[str] = [_GENERATED_BANNER, ""]
    lines.append("export interface FrenchResource {")
    lines.append("    url: string;")
    lines.append("    title?: string;")
    lines.append("}")
    lines.append("")
    lines.append("/** English URL -> verified French equivalent. */")
    lines.append("export const RESOURCES: Record<string, FrenchResource> = {")

    for pair in sorted(pair_set.pairs, key=lambda item: normalize_url(item.en_url)):
        lines.append(f"    {_ts_string(pair.en_url)}: {{")
        lines.append(f"        url: {_ts_string(pair.fr_url)},")
        if pair.fr_title:
            lines.append(f"        title: {_ts_string(pair.fr_title)},")
        lines.append("    },")

    lines.append("};")
    lines.append("")
    lines.append(
        "/** URLs already in French: prevents the UI marking a French document \"(en anglais)\". */"
    )
    lines.append("export const ALREADY_FRENCH: readonly string[] = [")

    french = {normalize_url(url): url for url in pair_set.french_urls}
    for pair in pair_set.pairs:
        french.setdefault(normalize_url(pair.fr_url), pair.fr_url)
    for url in sorted(french.values()):
        lines.append(f"    {_ts_string(url)},")

    lines.append("];")
    lines.append("")
    return "\n".join(lines)


# --- manifest ---------------------------------------------------------------------------


def _hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update((part or "").encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def build_manifest(
    pair_set: PairSet,
    english_resources: Iterable[Dict[str, object]] = (),
    french_resources: Iterable[Dict[str, object]] = (),
) -> Dict[str, object]:
    """Per-unit content hashes — the record the change classifier diffs against."""
    units: Dict[str, Dict[str, str]] = {}

    for pair in pair_set.pairs:
        key = f"pair:{normalize_url(pair.en_url)}"
        units[key] = {
            "kind": "pair",
            "hash": _hash(pair.en_url, pair.fr_url, pair.fr_title or ""),
            "label": pair.fr_title or pair.fr_url,
        }

    for resource in english_resources:
        url = str(resource.get("url", ""))
        units[f"en-resource:{normalize_url(url)}"] = {
            "kind": "en-resource",
            "hash": _hash(url, str(resource.get("title", ""))),
            "label": str(resource.get("title", "")),
        }

    for resource in french_resources:
        url = str(resource.get("url", ""))
        units[f"fr-resource:{normalize_url(url)}"] = {
            "kind": "fr-resource",
            "hash": _hash(url, str(resource.get("title", ""))),
            "label": str(resource.get("title", "")),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "unit_count": len(units),
        "units": dict(sorted(units.items())),
    }


def load_manifest(path: Path = MANIFEST_PATH) -> Optional[Dict[str, object]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def classify_changes(
    previous: Optional[Dict[str, object]],
    current: Dict[str, object],
) -> Dict[str, List[str]]:
    """Compare two manifests. Drives the PR body, so a reviewer reads a change list rather
    than a raw diff."""
    old_units: Dict[str, Dict[str, str]] = (previous or {}).get("units", {})  # type: ignore[assignment]
    new_units: Dict[str, Dict[str, str]] = current.get("units", {})  # type: ignore[assignment]

    added = sorted(set(new_units) - set(old_units))
    removed = sorted(set(old_units) - set(new_units))
    changed = sorted(
        key
        for key in set(new_units) & set(old_units)
        if new_units[key].get("hash") != old_units[key].get("hash")
    )
    return {"added": added, "removed": removed, "changed": changed}


def describe_changes(changes: Dict[str, List[str]], current: Dict[str, object]) -> str:
    """Human-readable change summary for a PR body."""
    units: Dict[str, Dict[str, str]] = current.get("units", {})  # type: ignore[assignment]
    total = sum(len(items) for items in changes.values())
    if total == 0:
        return "No content changes detected."

    lines: List[str] = []
    for heading, key in (("Added", "added"), ("Changed", "changed"), ("Removed", "removed")):
        items = changes.get(key, [])
        if not items:
            continue
        lines.append(f"**{heading} ({len(items)})**")
        for item in items[:25]:
            label = units.get(item, {}).get("label", "")
            lines.append(f"- `{item}`" + (f" — {label}" if label else ""))
        if len(items) > 25:
            lines.append(f"- …and {len(items) - 25} more")
        lines.append("")
    return "\n".join(lines).strip()


def write_if_changed(path: Path, content: str) -> bool:
    """Write only when the content differs. Returns True if the file changed."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True
