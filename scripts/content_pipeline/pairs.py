"""In-memory containers for EN->FR pairings.

These used to be backed by `data/resource-pairs.json`, a committed snapshot that only changed
when somebody ran the CLI locally. The pairing table in Supabase replaced it -- see
`scripts/content_pipeline/state.py` -- so nothing here reads or writes a file any more.

What is left is the shape the matcher speaks: `match_resources` takes a `PairSet` of decisions
already made, so it knows which English tools to skip and which French documents are spoken
for. Callers build one from the table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts.content_pipeline.urls import normalize_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Pair:
    """One English -> French resource mapping."""

    en_url: str
    fr_url: str
    fr_title: Optional[str] = None
    # How this pair was established: "tool-number" for a derived match, "admin" for a human's.
    source: str = "tool-number"
    note: str = ""


@dataclass
class PairSet:
    pairs: List[Pair] = field(default_factory=list)

    def pair_index(self) -> Dict[str, Pair]:
        return {normalize_url(pair.en_url): pair for pair in self.pairs}

    def has_pair(self, en_url: str) -> bool:
        return normalize_url(en_url) in self.pair_index()
