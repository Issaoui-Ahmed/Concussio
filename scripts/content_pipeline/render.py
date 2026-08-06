"""Render stage: emit the offline fallback map the app bundles at build time.

Deterministic apart from one table read, so a render can always be re-run and diffed.

This artefact matters less than it used to. `/api/resource-links` now serves the pairing table
directly, so `resourceLinks.data.ts` is only reached when that endpoint is unavailable -- it is
a safety net, not the source. Regenerate it whenever the table has settled, so a deploy that
cannot reach Supabase still resolves French links to something recent:

    python -m scripts.content_pipeline.cli render

Only *data* is generated. `lib/i18n/resourceLinks.ts` holds the resolution logic, stays
hand-written and is covered by tests; this module emits `resourceLinks.data.ts` beside it. A
scraper should never be able to rewrite `localizeLink`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from scripts.content_pipeline.pairs import PairSet, PROJECT_ROOT
from scripts.content_pipeline.urls import normalize_url

DATA_TS_PATH = PROJECT_ROOT / "lib" / "i18n" / "resourceLinks.data.ts"

_GENERATED_BANNER = """// GENERATED FILE - DO NOT EDIT.
//
// Rendered from the `resource_pairs` table in Supabase by scripts/content_pipeline/render.py.
// No URL below is written by hand. To refresh it:
//     python -m scripts.content_pipeline.cli render
//
// This is the OFFLINE FALLBACK only. At runtime /api/resource-links reads the same table, so
// what ships here matters just when that endpoint is unreachable.
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
    """Emit `resourceLinks.data.ts` from a pair set."""
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
    return "\n".join(lines)


def write_if_changed(path: Path, content: str) -> bool:
    """Write only when the content differs. Returns True if the file changed."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True
