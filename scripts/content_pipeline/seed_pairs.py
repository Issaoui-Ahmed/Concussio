"""One-time seed: lift the hand-verified pairs out of lib/i18n/resourceLinks.ts into
data/resource-pairs.json, after which the .ts becomes generated output.

Run: python -m scripts.content_pipeline.seed_pairs

Parsing the existing .ts rather than retyping the table is deliberate — every one of these
French URLs was probed live, and retyping them by hand would risk a typo that silently
breaks a link the verification already blessed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.content_pipeline.pairs import Pair, PairSet, PAIRS_PATH, PROJECT_ROOT

TS_PATH = PROJECT_ROOT / "lib" / "i18n" / "resourceLinks.ts"

# Entries in the .ts are `[key]: { url: ..., title: ... }` where key and url may be either a
# double-quoted string or a `${PEDS}/...` template literal.
_ENTRY_RE = re.compile(
    r"""
    (?:\[\s*)?                                  # optional computed-key bracket
    [`"](?P<en>https?://[^`"]+)[`"]             # English URL (key)
    \s*\]?\s*:\s*\{                             # ]: {
    (?P<body>[^}]*)                             # entry body
    \}
    """,
    re.VERBOSE,
)
_URL_RE = re.compile(r"url:\s*[`\"](?P<url>https?://[^`\"]+)[`\"]")
_TITLE_RE = re.compile(r"title:\s*\"(?P<title>(?:[^\"\\]|\\.)*)\"")

# Findings from the 2026-07-29 hand-verification pass, kept as a note rather than as data.
#
# These three English resources each have a plausible French near-match that is WRONG. They were
# once carried as an explicit veto list; that mechanism has been removed, and re-measuring
# against the live listings confirmed the matcher declines all three unaided — the first on the
# child/adult variant check, the other two because neither carries a tool number or an
# unambiguous shared identifier. The reasoning is recorded here because it is expensive to
# rediscover, and because it is what to check first if any of them ever does acquire a pair:
#
#   /scoat-child/                     No French Child SCOAT6 exists. /scoat-enfant-fr/ is a 404,
#                                     and /scoat-fr/ is the ADULT instrument.
#   cattonline return-to-sport        The French index labels 'Retour au sport' but links the
#                                     return-to-ACTIVITY file.
#   5pconcussion /en/scorecalculator  /fr/scorecalculator resolves to the site root. There is no
#                                     French 5P calculator.


def parse_ts(source: str) -> tuple[list[Pair], list[str]]:
    peds = "https://pedsconcussion.com"

    # Drop comments so the documented-but-absent URLs in the NOTE blocks aren't parsed as data.
    #
    # ONLY whole-line comments. A naive `//.*` also eats the `//` in `https://`, truncating
    # every absolute URL value to `"https:` — which silently dropped all eight third-party
    # pairs on the first run. Every comment in resourceLinks.ts is its own line, so anchoring
    # to line start is both sufficient and safe.
    code = re.sub(r"(?m)^[ \t]*//.*$", "", source).replace("${PEDS}", peds)

    # Only the RESOURCES object holds pairs; ALREADY_FRENCH is a flat list after it.
    resources_start = code.find("const RESOURCES")
    already_start = code.find("const ALREADY_FRENCH")
    if resources_start < 0 or already_start < 0:
        raise SystemExit("Could not locate RESOURCES / ALREADY_FRENCH in resourceLinks.ts")

    resources_src = code[resources_start:already_start]
    already_src = code[already_start:]

    pairs: list[Pair] = []
    for match in _ENTRY_RE.finditer(resources_src):
        body = match.group("body")
        url_match = _URL_RE.search(body)
        if not url_match:
            continue
        title_match = _TITLE_RE.search(body)
        title = title_match.group("title").replace('\\"', '"') if title_match else None
        pairs.append(
            Pair(
                en_url=match.group("en"),
                fr_url=url_match.group("url"),
                fr_title=title,
                source="curated",
                note="Verified live 2026-07-29.",
            )
        )

    # Literal entries in ALREADY_FRENCH (the spread of RESOURCES values is runtime, and is
    # reconstructed from `pairs` instead).
    french = re.findall(r"^\s*[`\"](https?://[^`\"]+)[`\"],\s*$", already_src, re.MULTILINE)
    return pairs, french


def main() -> int:
    if PAIRS_PATH.exists():
        print(f"{PAIRS_PATH} already exists - refusing to overwrite the reviewed set.")
        return 1

    pairs, literal_french = parse_ts(TS_PATH.read_text(encoding="utf-8"))
    if not pairs:
        print("Parsed zero pairs - aborting rather than writing an empty source of truth.")
        return 1

    # Every French target is itself French, plus the literals already listed.
    french_urls = sorted({pair.fr_url for pair in pairs} | set(literal_french))

    pair_set = PairSet(pairs=pairs, french_urls=french_urls)
    pair_set.save()

    print(f"Wrote {PAIRS_PATH}")
    print(f"  pairs:       {len(pair_set.pairs)}")
    print(f"  french_urls: {len(pair_set.french_urls)}")
    titled = sum(1 for pair in pair_set.pairs if pair.fr_title)
    print(f"  with FR title: {titled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
