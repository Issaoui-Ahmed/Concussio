"""One-time migration: teach Supabase which vector-store file belongs to which tool link.

    python -m scripts.content_pipeline.adopt            # dry run, prints the mapping
    python -m scripts.content_pipeline.adopt --execute  # write the rows

The combined store holds 38 files that were all uploaded by hand: 28 Living Guideline Tools
and 10 research papers. The pipeline needs to know which files correspond to which live link,
because from then on a row is what makes a file touchable -- see scripts/sql/content_pipeline.sql.

SPENT -- this has already run and can no longer run again. It needed the `Living guideline
tools` store to tell tools from research papers inside the combined store, and that store was
deleted on 2026-08-02 once its 27 rows were written. The tool/paper distinction now exists only
in `vector_store_files`, which is exactly what those rows are for.

Kept as the record of how the mapping was derived. Re-running it exits with "store not found".
If the rows are ever lost, they cannot be rebuilt automatically -- the combined store no longer
carries anything distinguishing a hand-uploaded tool from a hand-uploaded paper.

Nothing is uploaded, downloaded or detached here. It writes Supabase rows pointing at file ids
that already exist, so it is safe to re-run and safe to get wrong -- delete the rows and try
again.

Matching is two-pass. The tool number carried by both the filename ("Tool 6.1 - ...") and the
URL slug ("/tool-6-1-.../") settles most of it exactly. The rest are titled differently on each
side ("Concussion Recognition Tool 6" is filed as "CRT6") and are matched by token overlap,
assigned globally best-first so a strong match cannot be stolen by a weak one earlier in the
list. Anything left unmatched is reported, never guessed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

from scripts.content_pipeline.fetch import Resource, fetch_english_tools, living_tools
from scripts.content_pipeline.state import (
    StoredFile,
    UPLOADED_ADOPTED,
    load_vector_store_files,
    record_vector_store_file,
)

load_dotenv()

# The store the six copilots actually read. Resolved by name so a rebuild that recreates it
# does not silently strand this script on a dead id.
COMBINED_STORE_NAME = "ConcussCare Coach Knowledge Base"
# The store whose membership marks a file as a tool rather than a research paper.
TOOLS_STORE_NAME = "Living guideline tools"

_FILENAME_NUMBER_RE = re.compile(r"tool\s*(\d{1,2})\.(\d{1,2})", re.IGNORECASE)

# Words that carry no discriminating signal between a filename and an anchor title.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "from", "at", "by",
    "tool", "outil", "txt", "pdf", "docx", "living", "guideline", "guidelines", "draft",
    "pedsconcussion", "com", "https", "http", "www", "wp", "content", "uploads",
}

# Below this the two sides share nothing but noise, and no pairing is proposed.
_MIN_SCORE = 0.18


def _api() -> Tuple[str, Dict[str, str]]:
    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        raise SystemExit("FUELIX_API_KEY is not set.")
    base = (os.getenv("FUELIX_API_BASE_URL") or "https://api.fuelix.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    product = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product:
        headers["product-id"] = product
    return base, headers


def _get(path: str, **params) -> dict:
    base, headers = _api()
    response = requests.get(f"{base}{path}", headers=headers, params=params or None, timeout=60)
    if response.status_code >= 400:
        raise SystemExit(f"Fuel IX GET {path} -> {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError:
        return {}


def _data(payload: dict) -> List[dict]:
    items = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def resolve_store_id(name: str) -> Optional[str]:
    for store in _data(_get("/vector_stores", limit=100)):
        if str(store.get("name", "")).strip().lower() == name.lower():
            return str(store.get("id"))
    return None


def store_files(store_id: str) -> Dict[str, str]:
    """file_id -> filename for one store."""
    out: Dict[str, str] = {}
    for entry in _data(_get(f"/vector_stores/{store_id}/files", limit=100)):
        file_id = str(entry.get("id", ""))
        meta = _get(f"/files/{file_id}")
        out[file_id] = str(meta.get("filename", "")) if isinstance(meta, dict) else ""
    return out


# --- matching --------------------------------------------------------------------------------


def _tokens(*parts: str) -> set:
    """Lowercased word set, with camelCase split so `VirtualConcussionExamManual` decomposes."""
    joined = " ".join(parts)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", joined)
    words = re.split(r"[^A-Za-z0-9]+", spaced.lower())
    return {word for word in words if word and word not in _STOPWORDS and len(word) > 1}


def _score(filename: str, resource: Resource) -> float:
    """Containment-weighted overlap between a stored filename and a scraped resource.

    Containment rather than Jaccard: filenames are abbreviated ("CRT6") while anchor titles are
    verbose, so a symmetric measure punishes exactly the pairs that need matching most.
    """
    left = _tokens(filename)
    right = _tokens(resource.title, resource.url)
    if not left or not right:
        return 0.0

    # An initialism match is the whole signal when it fires -- `crt6` against "Concussion
    # Recognition Tool 6" shares no ordinary token -- so it scores as a full match rather than
    # being diluted by the words around it.
    if left & _acronyms(resource.title):
        return 1.0

    shared = left & right
    if not shared:
        return 0.0
    return len(shared) / min(len(left), len(right))


def _filename_number(filename: str) -> Optional[str]:
    match = _FILENAME_NUMBER_RE.search(filename or "")
    return f"{int(match.group(1))}.{int(match.group(2))}" if match else None


def _acronyms(title: str) -> set:
    """Acronyms a title could plausibly be filed under.

    Files are sometimes named for the instrument's short form while the site's anchor text
    spells it out: `Tool 1.2 - CRT6.txt` is the page titled "Concussion Recognition Tool 6".
    Token overlap between those two is exactly zero, so without this the file and its link look
    unrelated -- and an unmatched link means the refresh job uploads a second copy of a
    document the store already has.

    Built from leading initials over 2..5 words, with any trailing digit in the title appended,
    which is what turns "Concussion Recognition Tool 6" into `crt6`. Stopwords are deliberately
    NOT filtered here: "Tool" is noise for overlap scoring but load-bearing for the initialism.
    """
    words = [word for word in re.split(r"[^A-Za-z0-9]+", title or "") if word]
    if len(words) < 2:
        return set()
    trailing = [word for word in words[:8] if word.isdigit()]
    found = set()
    for size in range(2, 6):
        if len(words) < size:
            break
        initials = "".join(word[0] for word in words[:size]).lower()
        found.add(initials)
        for digit in trailing:
            found.add(f"{initials}{digit}")
    return found


@dataclass
class Match:
    resource: Resource
    file_id: str
    filename: str
    how: str
    score: float = 1.0


def build_mapping(
    tool_files: Dict[str, str], scraped: Sequence[Resource]
) -> Tuple[List[Match], List[Resource], Dict[str, str]]:
    """Returns (matches, unmatched_resources, unmatched_files)."""
    matches: List[Match] = []
    remaining_files = dict(tool_files)
    remaining_resources = list(scraped)

    # Pass 1 -- tool number on both sides. Exact, language-independent, no judgement involved.
    by_number = {
        number: (fid, fn)
        for fid, fn in remaining_files.items()
        if (number := _filename_number(fn))
    }
    for resource in list(remaining_resources):
        if not resource.tool_number:
            continue
        hit = by_number.get(resource.tool_number)
        if not hit or hit[0] not in remaining_files:
            continue
        file_id, filename = hit
        matches.append(Match(resource, file_id, filename, f"tool number {resource.tool_number}"))
        remaining_files.pop(file_id, None)
        remaining_resources.remove(resource)

    # Pass 2 -- global best-first over token overlap. Sorting every candidate pair by score and
    # consuming greedily means a strong match is never lost to a weaker one that happened to be
    # considered first.
    candidates = [
        (_score(filename, resource), resource, file_id, filename)
        for resource in remaining_resources
        for file_id, filename in remaining_files.items()
    ]
    candidates.sort(key=lambda item: item[0], reverse=True)

    taken_files: set = set()
    taken_resources: set = set()
    for score, resource, file_id, filename in candidates:
        if score < _MIN_SCORE:
            break
        if file_id in taken_files or id(resource) in taken_resources:
            continue
        matches.append(Match(resource, file_id, filename, "title overlap", score))
        taken_files.add(file_id)
        taken_resources.add(id(resource))

    unmatched_resources = [r for r in remaining_resources if id(r) not in taken_resources]
    unmatched_files = {f: n for f, n in remaining_files.items() if f not in taken_files}
    return matches, unmatched_resources, unmatched_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write rows. Defaults to dry run.")
    args = parser.parse_args()

    print(f"Adoption ({'EXECUTE' if args.execute else 'DRY RUN'})\n")

    combined_id = resolve_store_id(COMBINED_STORE_NAME)
    tools_id = resolve_store_id(TOOLS_STORE_NAME)
    if not combined_id:
        raise SystemExit(f'Store "{COMBINED_STORE_NAME}" not found.')
    if not tools_id:
        raise SystemExit(
            f'Store "{TOOLS_STORE_NAME}" not found. If it was already deleted, the '
            f"tool/paper distinction is gone and this mapping cannot be rebuilt automatically."
        )

    combined = store_files(combined_id)
    tools = store_files(tools_id)
    print(f"  combined store {combined_id}: {len(combined)} files")
    print(f"  tools store    {tools_id}: {len(tools)} files")

    # Only files present in BOTH: a tool that is not in the combined store is not something the
    # copilots can retrieve, so adopting it would record an ownership the pipeline cannot act on.
    tool_files = {fid: fn for fid, fn in tools.items() if fid in combined}
    strays = set(tools) - set(combined)
    print(f"  tools also in combined: {len(tool_files)}" + (f"  ({len(strays)} not in combined)" if strays else ""))
    print(f"  papers / unmanaged:     {len(combined) - len(tool_files)}  (never touched by the pipeline)")

    scraped_all, errors = fetch_english_tools()
    for error in errors:
        print(f"  fetch error: {error}")
    scraped = living_tools(scraped_all)
    print(f"  scraped living tools:   {len(scraped)}\n")

    matches, unmatched_resources, unmatched_files = build_mapping(tool_files, scraped)

    matches.sort(key=lambda m: (m.how != "title overlap", m.resource.title.lower()))
    print(f"=== MAPPED {len(matches)} ===")
    for match in matches:
        detail = match.how if match.how != "title overlap" else f"title overlap {match.score:.2f}"
        print(f"  {match.filename[:58]:<58} <- {detail}")
        print(f"      {match.resource.url}")

    if unmatched_resources:
        print(f"\n=== LINK WITH NO FILE ({len(unmatched_resources)}) ===")
        print("  These links have no document in the store. The refresh job will upload them.")
        for resource in unmatched_resources:
            print(f"  {resource.title[:60]}\n      {resource.url}")

    if unmatched_files:
        print(f"\n=== FILE WITH NO LINK ({len(unmatched_files)}) ===")
        print("  No row is written for these, so the pipeline can never detach them.")
        for file_id, filename in unmatched_files.items():
            print(f"  {filename}  ({file_id})")

    existing = load_vector_store_files()
    if existing.error:
        print(f"\n  ! could not read existing rows: {existing.error}")
    else:
        print(f"\n  vector_store_files currently holds {len(existing.files)} rows")

    if not args.execute:
        print("\nDRY RUN -- nothing written. Re-run with --execute to write these rows.")
        return 0

    for match in matches:
        record_vector_store_file(
            StoredFile(
                source_url=match.resource.url,
                title=match.resource.title,
                store_id=combined_id,
                file_id=match.file_id,
                filename=match.filename,
                uploaded_by=UPLOADED_ADOPTED,
            )
        )
    print(f"\nWrote {len(matches)} rows, all marked '{UPLOADED_ADOPTED}' -- monitored for link "
          f"changes, but never removed automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
