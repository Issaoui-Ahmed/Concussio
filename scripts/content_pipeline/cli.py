"""Pipeline entrypoint.

    python -m scripts.content_pipeline.cli render     # regenerate artefacts from reviewed data
    python -m scripts.content_pipeline.cli verify     # gates only, changes nothing (CI check)
    python -m scripts.content_pipeline.cli refresh    # fetch -> match -> render (CI refresh job)

`verify` is the one safe to run anywhere: it never writes and exits non-zero on a gate failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from scripts.content_pipeline import gates
from scripts.content_pipeline.corpus import CORPUS_PATH, fetch_corpus
from scripts.content_pipeline.fetch import fetch_all, living_tools
from scripts.content_pipeline.match import match_resources
from scripts.content_pipeline.pairs import PAIRS_PATH, PairSet
from scripts.content_pipeline.urls import normalize_url
from scripts.content_pipeline.render import (
    DATA_TS_PATH,
    MANIFEST_PATH,
    build_manifest,
    classify_changes,
    describe_changes,
    load_manifest,
    render_resource_links_data,
    write_if_changed,
)

CHANGES_SUMMARY_PATH = MANIFEST_PATH.parent / "last-change-summary.md"


def _report(results: List[gates.GateResult]) -> bool:
    print("\n=== GATES ===")
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  [{mark}] {result.name}: {result.detail}")
    failed = [result for result in results if not result.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed.")
    return not failed


def cmd_render(_args: argparse.Namespace) -> int:
    pair_set = PairSet.load()
    changed = write_if_changed(DATA_TS_PATH, render_resource_links_data(pair_set))
    print(f"{'wrote' if changed else 'unchanged'}: {DATA_TS_PATH}")

    manifest = build_manifest(pair_set)
    manifest_changed = write_if_changed(
        MANIFEST_PATH, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"{'wrote' if manifest_changed else 'unchanged'}: {MANIFEST_PATH}")
    print(f"  {len(pair_set.pairs)} pairs, {manifest['unit_count']} manifest units")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    pair_set = PairSet.load()
    results = [
        gates.gate_pairs_wellformed(pair_set),
        gates.gate_child_variants_not_crossed(pair_set),
        gates.gate_generated_in_sync(pair_set),
        gates.gate_liveness(pair_set),
    ]
    return 0 if _report(results) else 1


def cmd_refresh(args: argparse.Namespace) -> int:
    print("Fetching recommendations…")
    corpus_markdown, domains = fetch_corpus()
    print(f"  {len(domains)} domains, {len(corpus_markdown)} chars")

    print("Fetching resources…")
    fetched = fetch_all()
    print(
        f"  {len(fetched.english_tools)} EN resources, "
        f"{len(fetched.french_resources)} FR resources"
    )
    for error in fetched.errors:
        print(f"  fetch error: {error}")

    previous_set = PairSet.load()
    previous = load_manifest()

    entry_gates = [
        gates.gate_corpus_sane(corpus_markdown, domains, previous),
        gates.gate_fetch_sane(fetched, previous),
    ]
    if not all(gate.passed for gate in entry_gates):
        _report(entry_gates)
        print("\nAborting: refusing to render from a suspect fetch. Last good state is intact.")
        return 1

    # Narrowed to the Living Guideline Tools before matching, exactly as the runtime map and
    # the admin report are. Matching over the full 96 would let this job write a pair for a
    # resource the admin view does not list — which the report could then only render as a
    # synthetic placeholder row, and nobody could act on.
    english = living_tools(fetched.english_tools)
    print(f"\nMatching… ({len(english)} living guideline tools of {len(fetched.english_tools)})")
    result = match_resources(english, fetched.french_resources, PairSet())
    print(f"  {len(result.auto)} auto, {len(result.unmatched_en)} unmatched EN")

    # Rebuilt from the scrape, not appended to what was already on disk. Appending made the file
    # a ratchet: a pair only ever entered it, so a resource the site stopped listing kept its
    # mapping forever and no run could retire one. A mirror can shrink; a ledger cannot.
    #
    # Every pair written here is a tool-number match; `source` records that, so the admin table
    # can tell them apart from pairs a human made in the UI. Anything the tool number does not
    # settle is left unmatched for a reviewer rather than guessed at.
    pair_set = PairSet(
        pairs=[proposal.to_pair() for proposal in result.auto],
        french_urls=sorted({resource.url for resource in fetched.french_resources}),
    )
    for proposal in result.auto:
        print(f"  + auto:   {proposal.en.title[:46]} -> {proposal.fr.title[:46]}")

    dropped = {normalize_url(p.en_url) for p in previous_set.pairs} - {
        normalize_url(p.en_url) for p in pair_set.pairs
    }
    for key in sorted(dropped):
        print(f"  - dropped: {key} (no longer derivable from the listing)")

    if not args.dry_run:
        pair_set.save()
        print(f"  updated {PAIRS_PATH} ({len(pair_set.pairs)} pairs)")

    manifest = build_manifest(
        pair_set,
        [resource.as_dict() for resource in fetched.english_tools],
        [resource.as_dict() for resource in fetched.french_resources],
    )
    changes = classify_changes(previous, manifest)
    summary = describe_changes(changes, manifest)

    print("\n=== CHANGES ===")
    print(summary)

    results = [
        gates.gate_pairs_wellformed(pair_set),
        gates.gate_child_variants_not_crossed(pair_set),
        gates.gate_liveness(pair_set),
    ]
    if not _report(results):
        print("\nAborting: gates failed, nothing written.")
        return 1

    if args.dry_run:
        print("\nDRY RUN — nothing written.")
        return 0

    write_if_changed(DATA_TS_PATH, render_resource_links_data(pair_set))
    write_if_changed(MANIFEST_PATH, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_if_changed(CHANGES_SUMMARY_PATH, summary + "\n")

    corpus_changed = write_if_changed(CORPUS_PATH, corpus_markdown)
    print(f"{'wrote' if corpus_changed else 'unchanged'}: {CORPUS_PATH.name}")

    # Tier A = pure link maintenance. A corpus change is always Tier B (clinical content).
    # Pairings no longer force Tier B on their own: the only kind this pipeline can produce is
    # an exact tool-number match, which is the definition of link maintenance.
    tier_a = not corpus_changed
    print(f"\nTier: {'A (auto-mergeable)' if tier_a else 'B (needs review)'}")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="content_pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("render", help="regenerate artefacts from reviewed data")
    sub.add_parser("verify", help="run gates only; writes nothing")

    refresh = sub.add_parser("refresh", help="fetch, match, render")
    refresh.add_argument("--dry-run", action="store_true", help="report but write nothing")

    args = parser.parse_args(argv)
    return {"render": cmd_render, "verify": cmd_verify, "refresh": cmd_refresh}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
