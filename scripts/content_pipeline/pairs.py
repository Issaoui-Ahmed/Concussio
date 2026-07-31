"""The EN->FR pair set — a snapshot of the last good scrape.

**Nothing in here is hand-written.** `cli refresh` rebuilds the whole file from the live
listings on every run: the Living Guideline Tools on the English side, `/ressources/` on the
French side, and the tool-number matches between them. Editing it by hand would survive
exactly until the next refresh.

It is a cache, not a source of truth — the runtime map in `api/resource_links.py` re-derives
the same pairs live and only falls back to this file when the fetch fails. Its real job is to
keep `render` deterministic and offline, so the generated `resourceLinks.data.ts` can be
diffed in a PR without a network round-trip.

Two kinds of entry:

- ``pairs``       — EN->FR mappings the matcher derived. Rendered into the app.
- ``french_urls`` — every URL on the French listings. Prevents the UI marking a French
                    document "(en anglais)".

The file used to carry hand-curated pairs alongside the derived ones. Three of them pointed
outside the Living Guideline Tools section, which is what produced the synthetic "alias" rows
in the admin workbench and made its English column read 30 against a 27-tool scrape. Pairs a
person makes now live in the Supabase override store instead, where they are visible, dated,
and removable.

There is deliberately no "never pair these" list. An earlier design carried one, on the theory
that a plausible-but-wrong French candidate needed an explicit veto. Measured against the live
listings it turned out to be redundant: the matcher's own guards — the child/adult variant
check, and the rule that an ambiguous identifier is not a match — already decline every case the
veto list covered. A second mechanism that never fires is not safety, it is something else to
keep in sync.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts.content_pipeline.urls import normalize_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAIRS_PATH = PROJECT_ROOT / "data" / "resource-pairs.json"


@dataclass
class Pair:
    """One approved English -> French resource mapping."""

    en_url: str
    fr_url: str
    fr_title: Optional[str] = None
    # How this pair was established: "tool-number", "curated", "title-similarity".
    source: str = "curated"
    # Free-text note for anything a reviewer needs to know later.
    note: str = ""

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"en_url": self.en_url, "fr_url": self.fr_url}
        if self.fr_title:
            payload["fr_title"] = self.fr_title
        payload["source"] = self.source
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass
class PairSet:
    pairs: List[Pair] = field(default_factory=list)
    french_urls: List[str] = field(default_factory=list)

    # --- lookups (normalized) ---------------------------------------------------------
    def pair_index(self) -> Dict[str, Pair]:
        return {normalize_url(pair.en_url): pair for pair in self.pairs}

    def has_pair(self, en_url: str) -> bool:
        return normalize_url(en_url) in self.pair_index()

    # --- io ---------------------------------------------------------------------------
    def to_json(self) -> str:
        payload = {
            "_comment": (
                "GENERATED - do not hand-edit. Snapshot of the last good scrape of "
                "pedsconcussion.com, rebuilt in full by `python -m scripts.content_pipeline.cli "
                "refresh`. Pairs are tool-number matches over the Living Guideline Tools "
                "section; french_urls is the French listing. To add a pair a scrape cannot "
                "derive, use /admin/scraping - it persists in the override store, not here."
            ),
            "pairs": [pair.as_dict() for pair in sorted(self.pairs, key=lambda p: p.en_url)],
            "french_urls": sorted(self.french_urls),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def load(cls, path: Path = PAIRS_PATH) -> "PairSet":
        # An absent snapshot is a valid state, not an error: it is what a fresh checkout looks
        # like before the first refresh. Every consumer already handles an empty set — the
        # runtime map re-derives its pairs live — so failing here would only turn a recoverable
        # cold start into a crash.
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            pairs=[
                Pair(
                    en_url=item["en_url"],
                    fr_url=item["fr_url"],
                    fr_title=item.get("fr_title"),
                    source=item.get("source", "curated"),
                    note=item.get("note", ""),
                )
                for item in data.get("pairs", [])
            ],
            french_urls=list(data.get("french_urls", [])),
        )

    def save(self, path: Path = PAIRS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
