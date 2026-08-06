"""Safety gates. Every one is a hard failure that aborts the run and leaves the last good
state committed.

The gate that matters most is `gate_fetch_sane`. A site redesign does not raise an exception —
it quietly returns zero rows, and a pipeline without this check would faithfully publish an
empty guideline to six assistants. `core/scraper.py:648` already carries a hand-written guard
of the same shape; this formalizes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from scripts.content_pipeline.fetch import FetchResult
from scripts.content_pipeline.liveness import BOT_BLOCKED, OK, probe_all
from scripts.content_pipeline.pairs import PairSet
from scripts.content_pipeline.render import DATA_TS_PATH, render_resource_links_data
from scripts.content_pipeline.urls import is_web_url, normalize_url

# A fetch returning fewer than this many resources means the page shape changed, not that the
# site deleted its content. Tuned against the observed live counts (96 EN / 35 FR).
MIN_ENGLISH_RESOURCES = 40
MIN_FRENCH_RESOURCES = 15

# How far a count may fall from the last known-good run before we stop and ask.
MAX_SHRINK_RATIO = 0.10

# Corpus floors. Observed live on 2026-07-29: 18 domains, 112 numbered recommendations,
# ~152k chars. Set well below those so normal editorial change passes and a broken scrape
# does not.
MIN_DOMAINS = 12
MIN_RECOMMENDATIONS = 90
MIN_CORPUS_CHARS = 100_000


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


def gate_fetch_sane(fetched: FetchResult) -> GateResult:
    """Shrink guard: refuse to proceed from a fetch that looks like a broken selector.

    Absolute floors only. The run-over-run comparison that used to live here read
    `data/content-manifest.json`, which no longer exists -- each sink now carries its own
    proportional guard against the state it actually writes (`vector_store.MAX_REMOVAL_RATIO`,
    and the floors in `pairing`), which is a truer comparison than a shared manifest was.
    """
    problems: List[str] = []

    if len(fetched.english_tools) < MIN_ENGLISH_RESOURCES:
        problems.append(
            f"only {len(fetched.english_tools)} EN resources (expected >= {MIN_ENGLISH_RESOURCES})"
        )
    if len(fetched.french_resources) < MIN_FRENCH_RESOURCES:
        problems.append(
            f"only {len(fetched.french_resources)} FR resources (expected >= {MIN_FRENCH_RESOURCES})"
        )
    if fetched.errors:
        problems.append(f"{len(fetched.errors)} fetch error(s): {fetched.errors[0]}")

    if problems:
        return GateResult("fetch-sane", False, "; ".join(problems))
    return GateResult(
        "fetch-sane",
        True,
        f"{len(fetched.english_tools)} EN / {len(fetched.french_resources)} FR resources",
    )


def gate_corpus_sane(markdown: str, domains: Dict[str, object]) -> GateResult:
    """Shrink guard for the recommendations corpus.

    `core/scraper.py:561` swallows a failed section fetch into an empty dict, so a network
    blip or a changed selector silently removes a whole section's recommendations rather than
    raising. Nothing downstream would notice — this is the check that does.
    """
    from scripts.content_pipeline.corpus import analyze

    stats = analyze(markdown)
    problems: List[str] = []

    if len(domains) < MIN_DOMAINS:
        problems.append(f"only {len(domains)} domains (expected >= {MIN_DOMAINS})")
    if len(stats.recommendation_numbers) < MIN_RECOMMENDATIONS:
        problems.append(
            f"only {len(stats.recommendation_numbers)} numbered recommendations "
            f"(expected >= {MIN_RECOMMENDATIONS})"
        )
    if stats.characters < MIN_CORPUS_CHARS:
        problems.append(f"corpus is only {stats.characters} chars (expected >= {MIN_CORPUS_CHARS})")

    # Any domain that rendered empty means its section failed to scrape.
    empty = [name for name, payload in domains.items()
             if not str(payload.get("recommendation_html", "")).strip()]
    if empty:
        problems.append(f"{len(empty)} domain(s) rendered empty: {empty[:3]}")

    # Run over run, against what was actually published rather than a committed file. A
    # store outage leaves `baseline` None, which correctly means "no comparison available"
    # rather than "no shrink".
    baseline = None
    try:
        from scripts.content_pipeline.state import load_corpus_state

        state = load_corpus_state()
        if state.found and not state.error:
            baseline = state.meta.get("recommendations")
    except Exception:
        baseline = None

    if isinstance(baseline, int) and baseline:
        if len(stats.recommendation_numbers) < baseline * (1 - MAX_SHRINK_RATIO):
            problems.append(
                f"recommendation count fell {baseline} -> {len(stats.recommendation_numbers)} "
                f"(>{MAX_SHRINK_RATIO:.0%} drop from what was last published)"
            )

    if problems:
        return GateResult("corpus-sane", False, "; ".join(problems))
    return GateResult(
        "corpus-sane",
        True,
        f"{len(domains)} domains, {len(stats.recommendation_numbers)} recommendations, "
        f"{stats.characters} chars",
    )


def gate_pairs_wellformed(pair_set: PairSet) -> GateResult:
    """Structural checks on the reviewed data itself."""
    problems: List[str] = []
    seen: set[str] = set()

    for pair in pair_set.pairs:
        if not is_web_url(pair.en_url) or not is_web_url(pair.fr_url):
            problems.append(f"non-web URL in pair: {pair.en_url} -> {pair.fr_url}")
        key = normalize_url(pair.en_url)
        if key in seen:
            problems.append(f"duplicate English key: {pair.en_url}")
        seen.add(key)
        if normalize_url(pair.fr_url) == key:
            problems.append(f"pair maps a URL to itself: {pair.en_url}")

    if problems:
        return GateResult("pairs-wellformed", False, "; ".join(problems[:5]))
    return GateResult("pairs-wellformed", True, f"{len(pair_set.pairs)} pairs, no structural issues")


def gate_child_variants_not_crossed(pair_set: PairSet) -> GateResult:
    """A paediatric resource must never be paired with an adult one, or vice versa.

    This replaces a gate that checked a hand-maintained veto list. The veto list is gone, so the
    thing worth asserting is no longer "did we honour the list" but the harm the list existed to
    prevent: the Child SCOAT6 pointing at the adult French instrument. Unlike the list, this
    catches the case for resources nobody thought to enumerate.
    """
    from scripts.content_pipeline.fetch import Resource
    from scripts.content_pipeline.match import _is_child_variant

    def as_resource(url: str, title: str) -> Resource:
        return Resource(title=title or "", url=url, lang="")

    crossed = [
        f"{pair.en_url} -> {pair.fr_url}"
        for pair in pair_set.pairs
        if _is_child_variant(as_resource(pair.en_url, ""))
        != _is_child_variant(as_resource(pair.fr_url, pair.fr_title or ""))
    ]
    if crossed:
        return GateResult(
            "child-variants-not-crossed",
            False,
            f"paediatric/adult mismatch in {len(crossed)} pair(s): {'; '.join(crossed[:3])}",
        )
    return GateResult(
        "child-variants-not-crossed",
        True,
        f"{len(pair_set.pairs)} pairs, no paediatric/adult crossover",
    )


def gate_generated_in_sync(pair_set: PairSet) -> GateResult:
    """The committed generated file must match what the reviewed data renders.

    Catches someone hand-editing the generated .ts, and catches a render that was never
    re-run after the JSON changed.
    """
    expected = render_resource_links_data(pair_set)
    if not DATA_TS_PATH.exists():
        return GateResult("generated-in-sync", False, f"{DATA_TS_PATH.name} does not exist")
    actual = DATA_TS_PATH.read_text(encoding="utf-8")
    if actual != expected:
        return GateResult(
            "generated-in-sync",
            False,
            f"{DATA_TS_PATH.name} is stale — run `cli render`",
        )
    return GateResult("generated-in-sync", True, f"{DATA_TS_PATH.name} matches the reviewed data")


def gate_liveness(pair_set: PairSet) -> GateResult:
    """Every URL the app will emit must resolve. Soft-404s count as dead."""
    urls = [pair.en_url for pair in pair_set.pairs] + [pair.fr_url for pair in pair_set.pairs]
    probes = probe_all(urls)
    bad = [probe for probe in probes if probe.verdict not in (OK, BOT_BLOCKED)]
    if bad:
        detail = "; ".join(f"{probe.url} ({probe.detail})" for probe in bad[:5])
        return GateResult("liveness", False, f"{len(bad)}/{len(probes)} dead: {detail}")
    blocked_count = sum(1 for probe in probes if probe.verdict == BOT_BLOCKED)
    suffix = f" ({blocked_count} bot-blocked, treated as live)" if blocked_count else ""
    return GateResult("liveness", True, f"{len(probes)}/{len(probes)} live{suffix}")
