"""Pairing engine: propose EN->FR resource matches from fetched listings.

There are exactly two ways a resource gets a French counterpart:

    tool number   1.3 == 1.3             matched here, auto-accepted
    manual        a human paired them    recorded in pairs.json, never re-proposed
    nothing       -                      English fallback, marked "(en anglais)"

Deliberately no LLM and no cross-language fuzzy text matching. Translating titles to compare
them would introduce a nondeterministic step into a pipeline whose whole purpose is to be
auditable, and "these two titles look similar" is far too weak a signal to point a clinician
at a different document.

A third tier used to live here: shared language-invariant identifiers (SCAT6, PECARN, PHQ-9)
appearing on both sides. It was proposal-only and never auto-accepted, but it was still a
guess — SCAT6 and Child SCAT6 both say "scat6" — and it has been removed. A near-neighbour
document is a worse answer than the English original, so anything the tool number cannot
settle is now a human's call.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Sequence

from scripts.content_pipeline.fetch import Resource
from scripts.content_pipeline.pairs import Pair, PairSet
from scripts.content_pipeline.urls import normalize_url

TIER_TOOL_NUMBER = "tool-number"

# The only tier this engine produces. Kept as a tuple so the publish-time re-check in
# api/resource_links.py keeps reading as a membership test rather than an equality it would be
# easy to loosen by accident.
AUTO_TIERS = (TIER_TOOL_NUMBER,)


@dataclass
class Proposal:
    en: Resource
    fr: Resource
    tier: str
    evidence: str

    @property
    def auto(self) -> bool:
        return self.tier in AUTO_TIERS

    def to_pair(self) -> Pair:
        return Pair(
            en_url=self.en.url,
            fr_url=self.fr.url,
            fr_title=self.fr.title or None,
            source=self.tier,
            note=self.evidence,
        )


@dataclass
class MatchResult:
    auto: List[Proposal]
    unmatched_en: List[Resource]
    unmatched_fr: List[Resource]


# "Child"/"enfant" and adult variants must not cross-match: pairing the adult SCOAT6 to a
# paediatric one would point a clinician at the wrong instrument. This is the Child SCOAT6
# trap, generalized.
#
# This check is the *only* thing standing between that trap and a published pair — the
# hand-maintained veto list that used to back it up is gone, and tool numbers alone do not
# distinguish the variants. Weaken it and the Child SCOAT6 pairs itself to the adult French
# instrument.
_CHILD_MARKERS = ("child", "enfant", "pediatric", "pediatrique", "paediatric")


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _is_child_variant(resource: Resource) -> bool:
    subject = _strip_accents(f"{resource.title} {resource.url}").lower()
    return any(marker in subject for marker in _CHILD_MARKERS)


def _index_by_tool_number(resources: Sequence[Resource]) -> Dict[str, List[Resource]]:
    index: Dict[str, List[Resource]] = {}
    for resource in resources:
        if resource.tool_number:
            index.setdefault(resource.tool_number, []).append(resource)
    return index


def match_resources(
    english: Sequence[Resource],
    french: Sequence[Resource],
    existing: PairSet,
) -> MatchResult:
    """Propose pairings for English resources that don't already have one."""
    pair_index = existing.pair_index()

    # Only consider English resources that do not already have a pair.
    candidates = [
        resource
        for resource in english
        if normalize_url(resource.url) not in pair_index
    ]

    # French resources already used by an approved pair are spoken for.
    claimed_fr = {normalize_url(pair.fr_url) for pair in existing.pairs}
    available_fr = [
        resource for resource in french if normalize_url(resource.url) not in claimed_fr
    ]

    fr_by_number = _index_by_tool_number(available_fr)

    auto: List[Proposal] = []
    matched_fr: set[str] = set()

    # --- Tool number, the only tier ----------------------------------------------------
    for resource in candidates:
        if not resource.tool_number:
            continue
        siblings = fr_by_number.get(resource.tool_number, [])
        # Ambiguity is not a match. Two French docs claiming tool 6.1 means the listing
        # changed shape and a human needs to look.
        if len(siblings) != 1:
            continue
        counterpart = siblings[0]
        if normalize_url(counterpart.url) in matched_fr:
            continue
        # Child/adult variants must agree even when the numbers do.
        if _is_child_variant(resource) != _is_child_variant(counterpart):
            continue

        auto.append(
            Proposal(
                en=resource,
                fr=counterpart,
                tier=TIER_TOOL_NUMBER,
                evidence=f"Tool number {resource.tool_number} on both sides.",
            )
        )
        matched_fr.add(normalize_url(counterpart.url))

    proposed_en = {normalize_url(proposal.en.url) for proposal in auto}
    return MatchResult(
        auto=auto,
        unmatched_en=[
            resource for resource in candidates
            if normalize_url(resource.url) not in proposed_en
        ],
        unmatched_fr=[
            resource for resource in available_fr
            if normalize_url(resource.url) not in matched_fr
        ],
    )
