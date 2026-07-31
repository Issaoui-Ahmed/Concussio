"""Render `all_rec_markdown.md` from the live site.

The file was originally copied from pedsconcussion.com, so regenerating it is a refresh, not
a rewrite — there is no hand-authored content to preserve.

The catch is that `core.scraper` exposes recommendations two ways and only one is usable
here: `recommendation_text` is `get_text()`, which flattens away every link, image and bold
run. The corpus needs all of those (the tool links are the whole point), so this module
converts `recommendation_html` to Markdown instead.

Style is tuned to match the existing file, which was itself produced by an HTML-to-Markdown
pass: ATX headings, `*` bullets, inline links and images retained. Matching it keeps the
switchover diff readable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from markdownify import MarkdownConverter

from core.scraper import SECTION_INDEX_URL, scrape_all_domain_recommendations
from scripts.content_pipeline.pairs import PROJECT_ROOT

CORPUS_PATH = PROJECT_ROOT / "all_rec_markdown.md"

# Recommendation numbers as they appear at the start of a line: 2.1, 2.1a, 14.1.
RECOMMENDATION_NUMBER_RE = re.compile(r"^\s*(\d{1,2}\.\d{1,2}[a-z]?)\s*$", re.MULTILINE)
URL_RE = re.compile(r'https?://[^\s)\]"\'<>]+')


class _CorpusConverter(MarkdownConverter):
    """Keeps images and links; the guideline's evidence levels are rendered as images."""

    class Options(MarkdownConverter.DefaultOptions):
        heading_style = "ATX"
        bullets = "*"
        strip_document = "strip"


def html_to_markdown(html: str) -> str:
    markdown = _CorpusConverter().convert(html)
    # Collapse the run of blank lines the converter leaves between modules.
    markdown = re.sub(r"\n{4,}", "\n\n\n", markdown)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    return markdown.strip()


@dataclass
class CorpusStats:
    domains: int = 0
    recommendation_numbers: Set[str] = field(default_factory=set)
    urls: Set[str] = field(default_factory=set)
    characters: int = 0


def analyze(markdown: str) -> CorpusStats:
    return CorpusStats(
        domains=len(re.findall(r"^## ", markdown, re.MULTILINE)),
        recommendation_numbers=set(RECOMMENDATION_NUMBER_RE.findall(markdown)),
        urls={match.rstrip(".,;") for match in URL_RE.findall(markdown)},
        characters=len(markdown),
    )


def render_corpus(domains: Dict[str, Dict[str, str]]) -> str:
    """Assemble the full corpus markdown from scraped domains.

    The scraped HTML already carries its own `##### Recommendations` heading, so only the
    domain title is added here — emitting one would duplicate it.
    """
    blocks: List[str] = []
    for domain_name, payload in domains.items():
        body = html_to_markdown(payload.get("recommendation_html", ""))
        if not body:
            continue
        blocks.append(f"## {domain_name}\n\n{body}")
    return "\n\n".join(blocks).strip() + "\n"


def fetch_corpus(
    section_index_url: str = SECTION_INDEX_URL,
) -> tuple[str, Dict[str, Dict[str, str]]]:
    """Scrape and render. Returns (markdown, domains).

    URLs are reproduced exactly as the site publishes them. Link rot in the source is the
    site owner's to fix, not ours to paper over — rewriting here would mean the corpus no
    longer matches what pedsconcussion.com actually says. Dead links are *reported* by the
    liveness gate so they can be raised with the client.
    """
    domains = scrape_all_domain_recommendations(section_index_url)
    return render_corpus(domains), domains


def compare(generated: str, current: str) -> Dict[str, object]:
    """Coverage comparison between the generated corpus and the committed one.

    This is a correctness check on the *scraper*, not a curation check: anything present in
    the committed copy but absent from a fresh scrape means the extractor is missing content
    that the site still publishes.
    """
    new_stats, old_stats = analyze(generated), analyze(current)

    missing_numbers = sorted(old_stats.recommendation_numbers - new_stats.recommendation_numbers)
    added_numbers = sorted(new_stats.recommendation_numbers - old_stats.recommendation_numbers)
    missing_urls = sorted(old_stats.urls - new_stats.urls)
    added_urls = sorted(new_stats.urls - old_stats.urls)

    return {
        "domains": (old_stats.domains, new_stats.domains),
        "characters": (old_stats.characters, new_stats.characters),
        "recommendations": (
            len(old_stats.recommendation_numbers),
            len(new_stats.recommendation_numbers),
        ),
        "urls": (len(old_stats.urls), len(new_stats.urls)),
        "missing_recommendations": missing_numbers,
        "added_recommendations": added_numbers,
        "missing_urls": missing_urls,
        "added_urls": added_urls,
    }
