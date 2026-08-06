"""Keep the EN->FR pairing table in step with both listings.

    python -m scripts.content_pipeline.pairing            # dry run
    python -m scripts.content_pipeline.pairing --execute   # apply

Scrape the English Living Guideline Tools and the French resources, match them on tool number,
and write the result to `resource_pairs`. The app resolves French links straight out of that
table, so a run here is what makes a newly translated tool reachable.

`origin` decides who may write each row, and the rule is asymmetric on purpose:

    origin='auto'    derived by the matcher. Rebuilt on every run: re-derived, or retired when
                     the listing stops supporting it.
    origin='manual'  a person decided it in /admin/scraping. Never read, written or retired
                     here -- a refresh must not undo a human's call.

A manual row with a null fr_url is a suppression ("this tool has no French counterpart"), and
it removes the tool from the candidate set entirely, so the matcher cannot keep re-proposing
something a reviewer already rejected.

Auto rows are rebuilt rather than accumulated. Appending would make the table a ratchet: a pair
would only ever enter it, so a tool the site stopped listing would keep its mapping forever and
no run could retire one. A mirror can shrink; a ledger cannot.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

from scripts.content_pipeline.fetch import FetchResult, fetch_all, living_tools
from scripts.content_pipeline.match import TIER_TOOL_NUMBER, match_resources
from scripts.content_pipeline.pairs import Pair, PairSet
from scripts.content_pipeline.state import (
    ORIGIN_AUTO,
    PairTable,
    StoredPair,
    delete_auto_pair,
    load_resource_pairs,
    upsert_auto_pair,
)
from scripts.content_pipeline.urls import normalize_url

load_dotenv()

# Floors mirroring the vector-store sync. An empty French listing is a fetch failure, and
# acting on it would retire every derived pair in one run.
MIN_ENGLISH_TOOLS = 20
MIN_FRENCH_RESOURCES = 10


@dataclass
class PairSyncReport:
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    retired: List[str] = field(default_factory=list)
    unchanged: int = 0
    locked: int = 0
    english: int = 0
    french: int = 0
    problems: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    dry_run: bool = True

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.retired)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.failures

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "english": self.english,
            "french": self.french,
            "added": self.added,
            "updated": self.updated,
            "retired": self.retired,
            "unchanged": self.unchanged,
            "locked": self.locked,
            "problems": self.problems,
            "failures": self.failures,
            "dryRun": self.dry_run,
        }


def sync_pairs(*, dry_run: bool = True, fetched: Optional[FetchResult] = None) -> PairSyncReport:
    """Rebuild the derived pairings from both listings.

    `fetched` accepts an already-fetched pair of listings so a caller running several sinks
    fetches each page once. Omit it and this fetches its own.
    """
    report = PairSyncReport(dry_run=dry_run)

    if fetched is None:
        fetched = fetch_all()
    for error in fetched.errors:
        report.failures.append(f"fetch: {error}")

    english = living_tools(fetched.english_tools)
    french = fetched.french_resources
    report.english, report.french = len(english), len(french)

    if len(english) < MIN_ENGLISH_TOOLS:
        report.problems.append(f"only {len(english)} English tools (need >= {MIN_ENGLISH_TOOLS})")
    if len(french) < MIN_FRENCH_RESOURCES:
        report.problems.append(f"only {len(french)} French resources (need >= {MIN_FRENCH_RESOURCES})")
    if report.problems:
        return report

    table = load_resource_pairs()
    if table.error:
        report.problems.append(f"state: {table.error}")
        return report

    rows = table.by_url()
    locked = {key: row for key, row in rows.items() if row.locked}
    report.locked = len(locked)

    # A locked tool is out of the running entirely -- whether it was paired or suppressed, the
    # decision is made. Its French document is handed to the matcher as claimed so nothing else
    # can be pointed at it.
    candidates = [item for item in english if normalize_url(item.url) not in locked]
    claimed = PairSet(
        pairs=[
            Pair(en_url=row.en_url, fr_url=row.fr_url or "", fr_title=row.fr_title or None)
            for row in locked.values()
            if row.fr_url
        ]
    )

    result = match_resources(candidates, french, claimed)

    desired: Dict[str, StoredPair] = {}
    for proposal in result.auto:
        # Re-checked rather than assumed: this path writes to the table the app reads, so only
        # an exact tool-number match may publish itself.
        if proposal.tier != TIER_TOOL_NUMBER:
            continue
        desired[normalize_url(proposal.en.url)] = StoredPair(
            en_url=proposal.en.url,
            fr_url=proposal.fr.url,
            fr_title=proposal.fr.title or "",
            origin=ORIGIN_AUTO,
            source=proposal.tier,
            note=proposal.evidence,
        )

    current_auto = {key: row for key, row in rows.items() if not row.locked}

    for key, pair in desired.items():
        existing = current_auto.get(key)
        if existing is None:
            report.added.append(pair.en_url)
        elif (existing.fr_url or "") != pair.fr_url or (existing.fr_title or "") != pair.fr_title:
            report.updated.append(pair.en_url)
        else:
            report.unchanged += 1
            continue
        if not dry_run:
            try:
                upsert_auto_pair(pair)
            except Exception as exc:
                report.failures.append(f"upsert {pair.en_url}: {exc}")

    for key, row in current_auto.items():
        if key in desired:
            continue
        report.retired.append(row.en_url)
        if not dry_run:
            try:
                delete_auto_pair(row.en_url)
            except Exception as exc:
                report.failures.append(f"retire {row.en_url}: {exc}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply changes. Defaults to dry run.")
    args = parser.parse_args()

    report = sync_pairs(dry_run=not args.execute)
    print(f"Pairing sync ({'EXECUTE' if args.execute else 'DRY RUN'})")
    print(f"  {report.english} EN tools, {report.french} FR resources, "
          f"{report.locked} manual rows untouched")

    for url in report.added:
        print(f"  + pair    {url}")
    for url in report.updated:
        print(f"  ~ repoint {url}")
    for url in report.retired:
        print(f"  - retire  {url}")
    print(f"  = unchanged {report.unchanged}")

    for problem in report.problems:
        print(f"  REFUSED: {problem}")
    for failure in report.failures:
        print(f"  FAILED:  {failure}")

    if not args.execute and report.changed:
        print("\nDRY RUN -- nothing written. Re-run with --execute to apply.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
