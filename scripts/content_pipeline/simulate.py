"""Simulate a source-side change and check what the pipeline would do about it.

    python -m scripts.content_pipeline.simulate              # every scenario, offline
    python -m scripts.content_pipeline.simulate --live       # same, seeded from the live site
    python -m scripts.content_pipeline.simulate --capture    # re-record the fixture from live
    python -m scripts.content_pipeline.simulate --list
    python -m scripts.content_pipeline.simulate -s new-tool -s tool-moved

The pipeline's entire job is to notice that pedsconcussion.com changed and move the right sink.
Nothing here could test that, because we do not control the source: waiting for the guideline to
publish a tool was the only way to exercise the interesting paths, and the interesting paths are
the refusals -- which nobody wants to trigger for real.

The seam is that both listing-driven sinks accept an already-fetched listing, so they can be
handed a scrape that never happened:

    vector_store.sync(english_tools=...)      scripts/content_pipeline/vector_store.py
    pairing.sync_pairs(fetched=...)           scripts/content_pipeline/pairing.py

WHAT IS SIMULATED AND WHAT IS NOT. The scrape and the stored state are both served from memory.
That is deliberate and it is the whole technique: they are the two sides of every comparison the
pipeline makes, and a test has to be able to set both. Everything *between* them is the shipping
code, unmodified -- the extractors, `plan()`, `gate()`, the matcher and its child-variant veto,
the removal split, the upload cap.

Being able to set the stored side is not just convenience. Every file in `vector_store_files` is
currently an adopted hand-made conversion, so no live run can reach the auto-removal branch at
all; `tool-retired-pipeline` sets one row's `uploaded_by` and exercises it.

Nothing here can write. Sinks are only ever called with `dry_run=True`, and on top of that every
state writer is replaced with a function that raises, so a mistake in this file cannot reach
Supabase or Fuel IX. No lease is taken and no `pipeline_runs` row is filed either, which is why
this is not built on `run_refresh`.

Offline is the default so the suite is runnable on a plane and deterministic in CI. `--live`
seeds from the real site and the real tables instead; expectations are calibrated against the
fixture, so a mismatch there is reported as DRIFT rather than failure -- it means the site or the
tables have moved away from what was recorded, which is worth seeing but is not a code defect.

One caveat if you import this module rather than running it: `_install` patches the sinks' state
loaders for the rest of the process and does not put them back. Running a real sink afterwards in
the same interpreter would read the simulated world. The writers are left raising, so the
direction that could do damage is closed, but do not build anything on top of this module that
expects the pipeline to still be wired to Supabase.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from dotenv import load_dotenv

from scripts.content_pipeline import fetch as fetch_module
from scripts.content_pipeline import pairing as pairing_module
from scripts.content_pipeline import vector_store as vector_store_module
from scripts.content_pipeline.fetch import (
    FRENCH_RESOURCE_URLS,
    GROUP_LIVING_TOOL,
    FetchResult,
    Resource,
    fetch_all,
    living_tools,
)
from scripts.content_pipeline.match import _is_child_variant
from scripts.content_pipeline.state import (
    PairTable,
    StoredFile,
    StoredFileSet,
    StoredPair,
    UPLOADED_PIPELINE,
    load_resource_pairs,
    load_vector_store_files,
)
from scripts.content_pipeline.urls import normalize_url

load_dotenv()

FIXTURE_DIR = Path(__file__).parent / "fixtures"
STATE_FIXTURE = FIXTURE_DIR / "state.json"

# The pages a full fetch asks for. Which file each was recorded into is written into the
# fixture rather than hard-coded here, so the recording describes itself and a change to
# `FRENCH_RESOURCE_URLS` cannot silently desynchronise the two.
CAPTURED_URLS = (fetch_module.TOOLS_RESOURCES_URL,) + tuple(FRENCH_RESOURCE_URLS)

PAGE_FILENAMES: Dict[str, str] = {
    fetch_module.TOOLS_RESOURCES_URL: "listing-en.html",
    FRENCH_RESOURCE_URLS[0]: "listing-fr-ressources.html",
    FRENCH_RESOURCE_URLS[1]: "listing-fr-ressources-en-francais.html",
}

# Fuel IX object ids are replaced with these when the fixture is recorded. The dry-run paths
# never dereference them -- `sync` returns before any request -- and infrastructure identifiers
# are not worth committing just to make a stub look realistic.
REDACTED_STORE_ID = "vs_fixture"
REDACTED_FILE_PREFIX = "file_fixture_"


class SimulationWrote(RuntimeError):
    """A state writer was called. Nothing in a simulation may write; this is the backstop."""


# --- the world a scenario mutates ---------------------------------------------------------------


@dataclass
class World:
    """Both sides of every comparison the pipeline makes, in a form a scenario can edit.

    `fetched` is what the site says; `stored` and `pairs` are what Supabase says we have. The
    sinks diff one against the other, so a scenario is just an edit to one of these.
    """

    fetched: FetchResult
    stored: StoredFileSet
    pairs: PairTable

    def living(self) -> List[Resource]:
        return living_tools(self.fetched.english_tools)

    def stored_row(self, url: str) -> Optional[StoredFile]:
        return self.stored.by_url().get(normalize_url(url))


def _refuse_write(*_args, **_kwargs):
    raise SimulationWrote(
        "A simulation tried to write to Supabase. Scenarios run dry; this is a bug in "
        "scripts/content_pipeline/simulate.py, not something to work around."
    )


def _install(world: World) -> None:
    """Point the sinks' state reads at `world`, and make every state write raise.

    Both loaders are patched in live mode too, not just offline. It costs nothing -- the world
    was seeded from those same reads -- and it means a scenario that edits the stored side
    behaves identically in both modes.
    """
    vector_store_module.load_vector_store_files = lambda: world.stored
    vector_store_module.resolve_store_id = lambda *_a, **_k: REDACTED_STORE_ID
    pairing_module.load_resource_pairs = lambda: world.pairs

    vector_store_module.record_vector_store_file = _refuse_write
    vector_store_module.forget_vector_store_file = _refuse_write
    pairing_module.upsert_auto_pair = _refuse_write
    pairing_module.delete_auto_pair = _refuse_write


# --- fixture ------------------------------------------------------------------------------------


def _read_fixture() -> Dict[str, object]:
    if not STATE_FIXTURE.exists():
        raise SystemExit(
            f"No fixture at {STATE_FIXTURE}. Record one with:\n"
            f"    python -m scripts.content_pipeline.simulate --capture"
        )
    return json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))


def seed_offline() -> World:
    """Build the world from the recorded pages and tables.

    The pages are recorded as HTML rather than as extracted resources on purpose: run this way,
    `extract_resources` and the Living-Guideline-Tools tagging are exercised for real, so an
    extractor that stops matching a redesigned page is caught here too. Extracted JSON would
    have skipped precisely the code most likely to break.
    """
    state = _read_fixture()
    recorded = state.get("pages") or {}
    pages: Dict[str, str] = {}
    for url in CAPTURED_URLS:
        filename = recorded.get(url)
        if not filename:
            raise SystemExit(
                f"The fixture has no recording of {url}. Re-run with --capture."
            )
        path = FIXTURE_DIR / filename
        if not path.exists():
            raise SystemExit(f"Fixture page missing: {path}. Re-run with --capture.")
        pages[url] = path.read_text(encoding="utf-8")

    original = fetch_module.fetch_html
    fetch_module.fetch_html = lambda url, timeout=20: pages[url]
    try:
        fetched = fetch_all()
    finally:
        fetch_module.fetch_html = original

    stored = StoredFileSet(
        files=[
            StoredFile(
                source_url=row["sourceUrl"],
                title=row.get("title", ""),
                store_id=row.get("storeId", REDACTED_STORE_ID),
                file_id=row.get("fileId", ""),
                filename=row.get("filename", ""),
                uploaded_by=row.get("uploadedBy", UPLOADED_PIPELINE),
            )
            for row in state.get("vectorStoreFiles", [])
        ]
    )
    pairs = PairTable(
        pairs=[
            StoredPair(
                en_url=row["enUrl"],
                fr_url=row.get("frUrl") or None,
                fr_title=row.get("frTitle", ""),
                origin=row.get("origin", "auto"),
                source=row.get("source", ""),
                note=row.get("note", ""),
            )
            for row in state.get("resourcePairs", [])
        ]
    )
    return World(fetched=fetched, stored=stored, pairs=pairs)


def seed_live() -> World:
    return World(fetched=fetch_all(), stored=load_vector_store_files(), pairs=load_resource_pairs())


def capture() -> int:
    """Re-record the fixture from the live site and the live tables."""
    from core.scraper import fetch_html
    from scripts.content_pipeline.state import digest

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # Deduped by content, because `/ressources/` and `/ressources-en-francais/` currently serve
    # byte-identical HTML -- committing that twice is 95KB of noise. Recording the mapping means
    # the day they diverge, a re-capture just writes two files and nothing else has to change.
    pages: Dict[str, str] = {}
    by_content: Dict[str, str] = {}
    for url in CAPTURED_URLS:
        html = fetch_html(url)
        key = digest(html)
        if key in by_content:
            pages[url] = by_content[key]
            print(f"  {url}\n    -> identical to {by_content[key]}; not written twice")
            continue
        filename = PAGE_FILENAMES[url]
        (FIXTURE_DIR / filename).write_text(html, encoding="utf-8")
        by_content[key] = filename
        pages[url] = filename
        print(f"  wrote {filename} ({len(html):,} chars) <- {url}")

    for stale in FIXTURE_DIR.glob("listing-*.html"):
        if stale.name not in set(pages.values()):
            stale.unlink()
            print(f"  removed {stale.name} (no longer referenced)")

    stored = load_vector_store_files()
    if stored.error:
        raise SystemExit(f"Could not read vector_store_files: {stored.error}")
    pairs = load_resource_pairs()
    if pairs.error:
        raise SystemExit(f"Could not read resource_pairs: {pairs.error}")

    payload = {
        "_comment": (
            "Recorded by `python -m scripts.content_pipeline.simulate --capture`. Fuel IX store "
            "and file ids are redacted: the dry-run paths never dereference them."
        ),
        "pages": pages,
        "vectorStoreFiles": [
            {
                "sourceUrl": item.source_url,
                "title": item.title,
                "storeId": REDACTED_STORE_ID,
                "fileId": f"{REDACTED_FILE_PREFIX}{index:03d}",
                "filename": item.filename,
                "uploadedBy": item.uploaded_by,
            }
            for index, item in enumerate(stored.files)
        ],
        "resourcePairs": [
            {
                "enUrl": item.en_url,
                "frUrl": item.fr_url,
                "frTitle": item.fr_title,
                "origin": item.origin,
                "source": item.source,
                "note": item.note,
            }
            for item in pairs.pairs
        ],
    }
    STATE_FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {STATE_FIXTURE.name} "
          f"({len(payload['vectorStoreFiles'])} stored files, {len(payload['resourcePairs'])} pairs)")
    return 0


# --- running one scenario -------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    why: str
    mutate: Callable[[World], Optional[str]]
    expect: Dict[str, object]
    # The pairs sink costs a second diff and most scenarios are about the vector store.
    pairs: bool = False


def _flatten(vector: Dict[str, object], pair: Optional[Dict[str, object]]) -> Dict[str, object]:
    flat: Dict[str, object] = {
        "scraped": vector["scraped"],
        "added": len(vector["added"]),
        "removed": len(vector["removed"]),
        "review": len(vector["needsReview"]),
        "deferred": len(vector["deferred"]),
        "unchanged": vector["unchanged"],
        "refused": bool(vector["problems"]),
    }
    if pair is not None:
        flat.update(
            {
                "pairsAdded": len(pair["added"]),
                "pairsUpdated": len(pair["updated"]),
                "pairsRetired": len(pair["retired"]),
                "pairsUnchanged": pair["unchanged"],
                "pairsRefused": bool(pair["problems"]),
            }
        )
    return flat


def run_scenario(scenario: Scenario, base: World) -> tuple[bool, bool]:
    """Returns (matched, skipped)."""
    world = copy.deepcopy(base)
    note = scenario.mutate(world)
    if note == SKIP:
        print(f"  SKIP  {scenario.name}\n        no suitable candidate in this world")
        return True, True

    _install(world)
    vector = vector_store_module.sync(
        dry_run=True, english_tools=world.fetched.english_tools
    ).as_dict()
    pair = (
        pairing_module.sync_pairs(dry_run=True, fetched=world.fetched).as_dict()
        if scenario.pairs
        else None
    )

    actual = _flatten(vector, pair)
    mismatches = {
        key: (value, actual.get(key))
        for key, value in scenario.expect.items()
        if actual.get(key) != value
    }

    print(f"  {'PASS ' if not mismatches else 'FAIL '} {scenario.name}")
    print(f"        {scenario.why}")
    if note:
        print(f"        {note}")
    print(
        f"        vector: {actual['scraped']} scraped  +{actual['added']} -{actual['removed']} "
        f"?{actual['review']} …{actual['deferred']} ={actual['unchanged']}"
        + ("  REFUSED" if actual["refused"] else "")
    )
    for problem in vector["problems"]:
        print(f"          refusal: {problem}")
    if pair is not None:
        print(
            f"        pairs:  +{actual['pairsAdded']} ~{actual['pairsUpdated']} "
            f"-{actual['pairsRetired']} ={actual['pairsUnchanged']}"
            + ("  REFUSED" if actual["pairsRefused"] else "")
        )
        for problem in pair["problems"]:
            print(f"          refusal: {problem}")
    for key, (expected, got) in mismatches.items():
        print(f"        expected {key}={expected!r}, got {got!r}")
    for failure in list(vector["failures"]) + list((pair or {}).get("failures", [])):
        print(f"        ! {failure}")

    return not mismatches, False


# --- the scenarios ----------------------------------------------------------------------------------

SKIP = "__skip__"


def _fake_tool(number: str, slug: str) -> Resource:
    return Resource(
        title=f"Tool {number}: Simulated Tool",
        url=f"https://pedsconcussion.com/{slug}/",
        lang="en",
        source_page=fetch_module.TOOLS_RESOURCES_URL,
        tool_number=number,
        group=GROUP_LIVING_TOOL,
    )


def _fake_french(number: str, *, child: bool) -> Resource:
    suffix = "-pour-enfant" if child else ""
    return Resource(
        title=f"Outil {number} : Version Simulee{' pour enfant' if child else ''}",
        url=f"https://pedsconcussion.com/outil-{number.replace('.', '-')}-simule{suffix}/",
        lang="fr",
        source_page=FRENCH_RESOURCE_URLS[0],
        tool_number=number,
    )


def _pairing_candidate(world: World, *, child_marked: bool) -> Optional[Resource]:
    """An English tool a new French translation could plausibly pair to.

    Numbered, not already paired, not locked by a reviewer, and with no French resource already
    claiming its number -- otherwise the matcher has nothing to newly decide.
    """
    rows = world.pairs.by_url()
    taken = {key for key, row in rows.items() if row.locked or row.fr_url}
    fr_numbers = {item.tool_number for item in world.fetched.french_resources if item.tool_number}
    for resource in world.living():
        if not resource.tool_number or resource.tool_number in fr_numbers:
            continue
        if normalize_url(resource.url) in taken:
            continue
        if _is_child_variant(resource) is child_marked:
            return resource
    return None


def _mutate_control(_world: World) -> None:
    return None


def _mutate_new_tool(world: World) -> str:
    tool = _fake_tool("29.9", "tool-29-9-simulated")
    world.fetched.english_tools.append(tool)
    return f"published: {tool.url}"


def _mutate_retire_adopted(world: World) -> Optional[str]:
    for resource in world.living():
        row = world.stored_row(resource.url)
        if row is not None and not row.auto_removable:
            world.fetched.english_tools.remove(resource)
            return f"delisted (file is hand-made): {resource.url}"
    return SKIP


def _mutate_retire_pipeline(world: World) -> Optional[str]:
    """The auto-removal branch, which no live run can currently reach.

    Every row in `vector_store_files` is an adopted conversion today, so a vanished link always
    lands in needs-review. Flipping one row to pipeline-uploaded is the only way to see the
    branch that actually deletes.
    """
    for resource in world.living():
        row = world.stored_row(resource.url)
        if row is not None:
            row.uploaded_by = UPLOADED_PIPELINE
            world.fetched.english_tools.remove(resource)
            return f"delisted (pipeline-uploaded, so removable): {resource.url}"
    return SKIP


def _mutate_tool_moved(world: World) -> Optional[str]:
    for resource in world.living():
        if world.stored_row(resource.url) is not None:
            was = resource.url
            resource.url = was.rstrip("/") + "-v2/"
            return f"republished: {was}\n           -> {resource.url}"
    return SKIP


def _mutate_broken_selector(world: World) -> str:
    keep = world.living()[:3]
    world.fetched.english_tools = keep
    return "the listing came back with 3 tools instead of 27"


def _mutate_heading_renamed(world: World) -> str:
    for resource in world.fetched.english_tools:
        resource.group = ""
    return "the 'Living Guideline Tools' heading no longer matches, so nothing is tagged"


def _mutate_bulk_addition(world: World) -> str:
    for resource in world.fetched.english_tools:
        resource.group = GROUP_LIVING_TOOL
    return "the tagging selector widened to the whole page"


def _mutate_upload_cap(world: World) -> str:
    """Nine new tools: under the addition ratio, over the per-run upload ceiling."""
    for index in range(9):
        world.fetched.english_tools.append(_fake_tool(f"3{index}.1", f"tool-3{index}-1-simulated"))
    return "nine tools published at once"


def _mutate_new_translation(world: World) -> Optional[str]:
    target = _pairing_candidate(world, child_marked=False)
    if target is None:
        return SKIP
    world.fetched.french_resources.append(_fake_french(target.tool_number, child=False))
    return f"French published for Tool {target.tool_number}: {target.url}"


def _mutate_child_veto(world: World) -> Optional[str]:
    """The child-variant guard, exercised in both directions.

    `_is_child_variant` substring-matches "child" against title *and URL*, so a tool whose slug
    happens to contain the word -- CATCH2's is ".../tomography-for-childhood-head-injury/" -- is
    treated as paediatric even though the word is part of an instrument's proper name. A French
    translation without a matching marker is then vetoed. It fails safe (no wrong pair is
    published) but such a tool can never auto-pair, so it is pinned here rather than left to be
    rediscovered.
    """
    target = _pairing_candidate(world, child_marked=True)
    if target is None:
        return SKIP
    world.fetched.french_resources.append(_fake_french(target.tool_number, child=False))
    return (
        f"French published for Tool {target.tool_number} with no child/enfant marker,\n"
        f"           against an English tool the guard reads as paediatric:\n"
        f"           {target.url}"
    )


def _mutate_french_listing_empty(world: World) -> str:
    world.fetched.french_resources = []
    return "the French listing came back empty"


SCENARIOS: List[Scenario] = [
    Scenario(
        name="control",
        why="nothing changed upstream; the run must be a clean no-op",
        mutate=_mutate_control,
        expect={"added": 0, "removed": 0, "review": 0, "refused": False,
                "pairsAdded": 0, "pairsUpdated": 0, "pairsRetired": 0, "pairsRefused": False},
        pairs=True,
    ),
    Scenario(
        name="new-tool",
        why="the guideline publishes a tool; it must be picked up for upload",
        mutate=_mutate_new_tool,
        expect={"added": 1, "removed": 0, "review": 0, "refused": False},
    ),
    Scenario(
        name="tool-retired-adopted",
        why="a delisted tool whose file was made by hand is reported, never deleted",
        mutate=_mutate_retire_adopted,
        expect={"added": 0, "removed": 0, "review": 1, "refused": False},
    ),
    Scenario(
        name="tool-retired-pipeline",
        why="a delisted tool the pipeline uploaded is removable, and is removed",
        mutate=_mutate_retire_pipeline,
        expect={"added": 0, "removed": 1, "review": 0, "refused": False},
    ),
    Scenario(
        name="tool-moved",
        why="a tool republished at a new URL reads as one addition plus one departure",
        mutate=_mutate_tool_moved,
        expect={"added": 1, "review": 1, "refused": False},
    ),
    Scenario(
        name="broken-selector",
        why="a listing that lost most of its tools is a broken fetch and must be refused",
        mutate=_mutate_broken_selector,
        expect={"refused": True, "added": 0, "removed": 0},
    ),
    Scenario(
        name="heading-renamed",
        why="if the heading is gone the answer is 'nothing', and nothing is publishable",
        mutate=_mutate_heading_renamed,
        expect={"scraped": 0, "refused": True, "added": 0, "removed": 0},
    ),
    Scenario(
        name="bulk-addition",
        why="a selector matching the whole page must not dump 69 third-party docs in the store",
        mutate=_mutate_bulk_addition,
        expect={"refused": True, "added": 0},
    ),
    Scenario(
        name="upload-cap",
        why="a large legitimate change is spread across runs rather than timing out mid-upload",
        mutate=_mutate_upload_cap,
        expect={"added": 8, "deferred": 1, "refused": False},
    ),
    Scenario(
        name="new-translation",
        why="a newly translated tool becomes reachable in French",
        mutate=_mutate_new_translation,
        expect={"pairsAdded": 1, "pairsRefused": False},
        pairs=True,
    ),
    Scenario(
        name="child-variant-veto",
        why="a paediatric/adult mismatch is never auto-paired, even on an exact tool number",
        mutate=_mutate_child_veto,
        expect={"pairsAdded": 0, "pairsRefused": False},
        pairs=True,
    ),
    Scenario(
        name="french-listing-empty",
        why="an empty French listing must not retire every derived pair",
        mutate=_mutate_french_listing_empty,
        expect={"pairsRefused": True, "pairsRetired": 0},
        pairs=True,
    ),
]


# --- entrypoint ---------------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="content_pipeline.simulate", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--live", action="store_true",
                        help="seed from the live site and tables instead of the fixture")
    parser.add_argument("--capture", action="store_true",
                        help="re-record the fixture from live, then exit")
    parser.add_argument("--list", action="store_true", help="list scenario names and exit")
    parser.add_argument("-s", "--scenario", action="append", default=[],
                        help="run only this scenario (repeatable)")
    args = parser.parse_args(argv)

    if args.list:
        for scenario in SCENARIOS:
            print(f"  {scenario.name:24s} {scenario.why}")
        return 0

    if args.capture:
        print("Recording fixture from live…")
        return capture()

    selected = SCENARIOS
    if args.scenario:
        by_name = {scenario.name: scenario for scenario in SCENARIOS}
        unknown = [name for name in args.scenario if name not in by_name]
        if unknown:
            raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}. Try --list.")
        selected = [by_name[name] for name in args.scenario]

    print(f"Seeding from {'the live site and tables' if args.live else 'the recorded fixture'}…")
    base = seed_live() if args.live else seed_offline()
    if base.stored.error:
        raise SystemExit(f"Could not read vector_store_files: {base.stored.error}")
    if base.pairs.error:
        raise SystemExit(f"Could not read resource_pairs: {base.pairs.error}")
    if base.fetched.errors:
        for error in base.fetched.errors:
            print(f"  ! fetch: {error}")

    print(
        f"  baseline: {len(base.living())} living tools, "
        f"{len(base.fetched.french_resources)} French resources, "
        f"{len(base.stored.files)} stored files, {len(base.pairs.pairs)} pair rows\n"
    )

    failed: List[str] = []
    skipped = 0
    for scenario in selected:
        matched, was_skipped = run_scenario(scenario, base)
        skipped += 1 if was_skipped else 0
        if not matched:
            failed.append(scenario.name)
        print()

    total = len(selected)
    print(f"{total - len(failed) - skipped}/{total - skipped} scenarios matched"
          + (f", {skipped} skipped" if skipped else ""))
    if failed:
        # Live seeding is measured against fixture-calibrated expectations, so a mismatch there
        # means the world moved, not that the pipeline is wrong. Worth printing, not worth failing.
        label = "DRIFT" if args.live else "FAILED"
        print(f"{label}: {', '.join(failed)}")
        if args.live:
            print("  Seeded live; expectations are calibrated to the fixture. Re-record with "
                  "--capture if the site or tables have legitimately moved.")
            return 0
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
