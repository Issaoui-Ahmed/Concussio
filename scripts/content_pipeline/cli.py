"""Pipeline entrypoint.

    python -m scripts.content_pipeline.cli refresh   # run all three sinks, as the cron does
    python -m scripts.content_pipeline.cli render    # regenerate the bundled offline fallback
    python -m scripts.content_pipeline.cli verify    # gates only, writes nothing (CI check)

`verify` is the one safe to run anywhere: it never writes and exits non-zero on a gate failure.

`refresh` is the same work `/api/cron/refresh` does nightly, exposed locally so it can be run
on demand and read. Each sink is independent -- one failing does not stop the others.
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from dotenv import load_dotenv

from scripts.content_pipeline import gates
from scripts.content_pipeline.pairs import Pair, PairSet
from scripts.content_pipeline.render import (
    DATA_TS_PATH,
    render_resource_links_data,
    write_if_changed,
)
from scripts.content_pipeline.state import load_resource_pairs

load_dotenv()


def _pair_set_from_table() -> PairSet:
    """The live pairing table as the matcher's container type. Suppressions are excluded."""
    table = load_resource_pairs()
    if table.error:
        raise SystemExit(f"Could not read the pairing table: {table.error}")
    return PairSet(
        pairs=[
            Pair(
                en_url=row.en_url,
                fr_url=row.fr_url or "",
                fr_title=row.fr_title or None,
                source=row.source or row.origin,
                note=row.note,
            )
            for row in table.resolvable()
        ]
    )


def _report(results: List[gates.GateResult]) -> bool:
    print("\n=== GATES ===")
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  [{mark}] {result.name}: {result.detail}")
    failed = [result for result in results if not result.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed.")
    return not failed


def cmd_render(_args: argparse.Namespace) -> int:
    pair_set = _pair_set_from_table()
    changed = write_if_changed(DATA_TS_PATH, render_resource_links_data(pair_set))
    print(f"{'wrote' if changed else 'unchanged'}: {DATA_TS_PATH}")
    print(f"  {len(pair_set.pairs)} pairs from the live table")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    pair_set = _pair_set_from_table()
    results = [
        gates.gate_pairs_wellformed(pair_set),
        gates.gate_child_variants_not_crossed(pair_set),
        gates.gate_generated_in_sync(pair_set),
        gates.gate_liveness(pair_set),
    ]
    return 0 if _report(results) else 1


def cmd_refresh(args: argparse.Namespace) -> int:
    """The same run the cron and the admin button perform, printed instead of returned."""
    from scripts.content_pipeline.refresh import (
        SINK_CORPUS,
        SINK_PAIRS,
        SINK_VECTOR_STORE,
        run_refresh,
    )
    from scripts.content_pipeline.state import TRIGGER_CLI, RunInFlight

    dry_run = args.dry_run

    # The corpus sink patches six production assistants, so it stays behind an explicit flag
    # here. The cron runs it nightly; a local run should not push clinical content by accident.
    sinks = [SINK_VECTOR_STORE, SINK_PAIRS]
    if args.corpus:
        sinks.insert(0, SINK_CORPUS)

    print(f"Refreshing ({'dry run' if dry_run else 'execute'})…")
    try:
        payload = run_refresh(dry_run=dry_run, sinks=sinks, trigger=TRIGGER_CLI)
    except RunInFlight as exc:
        print(f"REFUSED: {exc}")
        return 1

    results = payload.get("sinks") or {}
    if payload.get("fetchError"):
        print(f"  fetch error: {payload['fetchError']}")
    if payload.get("leaseError"):
        print(f"  note: {payload['leaseError']}")

    if SINK_VECTOR_STORE in results:
        vector = results[SINK_VECTOR_STORE]
        print("\n=== VECTOR STORE ===")
        print(f"  {vector.get('scraped', 0)} scraped, {vector.get('stored', 0)} stored, "
              f"{vector.get('unchanged', 0)} unchanged")
        for url in vector.get("added", []):
            print(f"  + add    {url}")
        for url in vector.get("removed", []):
            print(f"  - remove {url}")
        for url in vector.get("needsReview", []):
            print(f"  ? review {url}  (hand-made file; will not be removed automatically)")
        for url in vector.get("deferred", []):
            print(f"  … later  {url}  (over the per-run upload cap; next run continues)")
        for problem in vector.get("problems", []) + vector.get("failures", []):
            print(f"  ! {problem}")

    if SINK_PAIRS in results:
        pairs = results[SINK_PAIRS]
        print("\n=== PAIRS ===")
        print(f"  {pairs.get('english', 0)} EN / {pairs.get('french', 0)} FR, "
              f"{pairs.get('locked', 0)} manual rows untouched")
        for url in pairs.get("added", []):
            print(f"  + pair    {url}")
        for url in pairs.get("updated", []):
            print(f"  ~ repoint {url}")
        for url in pairs.get("retired", []):
            print(f"  - retire  {url}")
        print(f"  = unchanged {pairs.get('unchanged', 0)}")
        for problem in pairs.get("problems", []) + pairs.get("failures", []):
            print(f"  ! {problem}")

    if SINK_CORPUS in results:
        corpus = results[SINK_CORPUS]
        print("\n=== CORPUS ===")
        print(f"  {corpus.get('action')}: {corpus.get('domains', 0)} domains, "
              f"{corpus.get('recommendations', 0)} recommendations, hash "
              f"{corpus.get('previousHash') or '(none)'} -> {corpus.get('hash')}")
        for assistant in corpus.get("assistants", []):
            print(f"    {assistant.get('role')}: {assistant.get('status')}"
                  f"{' — ' + assistant['reason'] if assistant.get('reason') else ''}")
        for problem in corpus.get("problems", []):
            print(f"  ! {problem}")
    elif not args.corpus:
        print("\n=== CORPUS (skipped; pass --corpus to include) ===")

    # Keep the committed copy in step with what was just published. The cron cannot do this --
    # Vercel's filesystem is read-only -- so without a local run the file drifts, and it is what
    # local dev and `core/prompts.py` read by default.
    if args.corpus and not dry_run:
        from scripts.content_pipeline.corpus import CORPUS_PATH
        from scripts.content_pipeline.state import load_corpus_state

        state = load_corpus_state()
        if state.found and state.content:
            if write_if_changed(CORPUS_PATH, state.content):
                print(f"\n  wrote {CORPUS_PATH.name} ({len(state.content)} chars)")
            else:
                print(f"\n  {CORPUS_PATH.name} already matches what is published")

    if dry_run:
        print("\nDRY RUN -- nothing written.")
    return 0 if payload.get("ok") else 1


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="content_pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("render", help="regenerate the bundled offline fallback from the table")
    sub.add_parser("verify", help="run gates only; writes nothing")

    refresh = sub.add_parser("refresh", help="run the sinks, as the cron does")
    refresh.add_argument("--dry-run", action="store_true", help="report but write nothing")
    refresh.add_argument(
        "--corpus", action="store_true",
        help="include the corpus sink, which patches six production assistants",
    )

    args = parser.parse_args(argv)
    return {"render": cmd_render, "verify": cmd_verify, "refresh": cmd_refresh}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
