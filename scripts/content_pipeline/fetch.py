"""Fetch stage: pull resource listings from pedsconcussion.com.

English recommendations and English tools already have working extractors in
``core.scraper``; this module adds the French resource listings, which had no coverage.

French recommendations are deliberately NOT fetched. One assistant per user type serves both
languages, answering in French from the English corpus, so a French corpus would mean either
twelve assistants or moving the corpus out of assistant instructions entirely. The `/fr/`
guideline pages also carry no `#rec-NNN` anchors, so a French answer could deep-link to a domain
page but never to an individual recommendation. Revisit only if French answer quality is raised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from core.scraper import DEFAULT_HEADERS, TOOLS_RESOURCES_URL, fetch_html  # noqa: F401
from scripts.content_pipeline.urls import normalize_url

# The French resources live on two pages, not one: /ressources/ is the main index and
# /ressources-en-francais/ is linked from /fr/. They overlap; results are deduped by URL.
FRENCH_RESOURCE_URLS = (
    "https://pedsconcussion.com/ressources/",
    "https://pedsconcussion.com/ressources-en-francais/",
)

# Site chrome that appears inside content containers on this theme. Matched against the
# lowercased link text; these are never resources.
_CHROME_TEXT = {
    "", "accueil", "home", "menu", "recherche", "search", "connexion", "login",
    "français", "francais", "english", "anglais", "version française",
    "retour", "back", "suivant", "précédent", "precedent", "next", "previous",
    "haut de page", "top", "partager", "share", "imprimer", "print",
    "facebook", "twitter", "linkedin", "instagram", "youtube",
    "politique de confidentialité", "privacy policy", "contact", "contactez-nous",
    "à propos", "a propos", "about", "plan du site", "sitemap",
}

# Hosts that are navigation rather than resources.
_CHROME_HOST_FRAGMENTS = ("facebook.", "twitter.", "x.com", "linkedin.", "instagram.", "youtube.")

# A resource link's text is a title, not a sentence. Anything much longer is prose that
# happens to be hyperlinked.
_MAX_TITLE_CHARS = 200


@dataclass
class Resource:
    """One listed resource: a human title and the URL it points at."""

    title: str
    url: str
    lang: str
    source_page: str = ""
    # Tool number ("6.1") when the title carries one. The strongest pairing key we have.
    tool_number: Optional[str] = None
    # Which block of the listing this came from: "living-tool" for the Living Guideline Tools
    # heading, "" for everything below it. Carries no pairing weight — it is provenance for a
    # human reading the admin view.
    group: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "lang": self.lang,
            "source_page": self.source_page,
            "tool_number": self.tool_number,
            "group": self.group,
        }


GROUP_LIVING_TOOL = "living-tool"


def living_tools(resources: Iterable["Resource"]) -> List["Resource"]:
    """Narrow a fetched English listing to the Living Guideline Tools block — the 27.

    The listing carries a second block below them, "Online Tools and Resources": CDC forms,
    CATT strategies, consensus statements, the SCAT/SCOAT instruments. That material is
    third-party, is not part of the guideline, and has no French counterpart on this site.
    96 in, 27 out.

    **Returns nothing when the heading is missing or empty. Deliberately.** This used to fall
    back to the unfiltered listing on the theory that an over-full table beats an empty one.
    That reasoning held for the pairing table, where a spurious row is visible and removable,
    and was badly wrong for the vector store, where it is not: the tagging keys off a heading a
    redesign could rename, and a rename would have handed all 96 resources to the store sync as
    if the guideline had published 69 new tools overnight.

    An empty result is a loud failure — every consumer floors on a minimum count and refuses —
    which is the right outcome. The job is to scrape what is under that heading. If the heading
    is not there, the answer is "nothing", not "everything".
    """
    return [resource for resource in resources if resource.group == GROUP_LIVING_TOOL]


@dataclass
class FetchResult:
    english_tools: List[Resource] = field(default_factory=list)
    french_resources: List[Resource] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# Titles: "Tool 2.5:", "Outil 6.1 —". Rare in practice — most anchor text carries no number.
_TITLE_NUMBER_RE = re.compile(
    r"\b(?:tool|outil)\s*[:\-—–]?\s*(\d{1,2})\.(\d{1,2})\b",
    re.IGNORECASE,
)

# Slugs, where the numbers actually live:
#   /tool-6-1-post-concussion-headache-algorithm/     -> 6.1
#   /outil-6-1-algorithme-de-gestion-...             -> 6.1
#   /wp-content/uploads/Outil-1.3-Algorithme-....pdf -> 1.3
#   /wp-content/uploads/2022/06/Tool-12.1-Academic-accomodations.pdf -> 12.1
#   /tool-10-1post-concussion-vision-...             -> 10.1  (no separator after the number)
#   /tool-8-2-2/                                     -> 8.2   (trailing -2 is WordPress's
#                                                              duplicate-slug suffix)
_SLUG_NUMBER_RE = re.compile(
    r"(?:tool|outil)[-_.\s]?(\d{1,2})[-_.](\d{1,2})",
    re.IGNORECASE,
)


def extract_tool_number(title: str, url: str = "") -> Optional[str]:
    """Pull a tool number from a title or, failing that, from the URL slug.

    This is the Tier 1 pairing key: ``Tool 6.1`` and ``Outil 6.1`` are the same document in
    two languages, and the number is language-independent.

    The URL is the more reliable source. On the live listings only 1 of 96 English anchors
    carries a number in its text, while the slugs carry them on both sides.
    """
    for pattern, subject in ((_TITLE_NUMBER_RE, title or ""), (_SLUG_NUMBER_RE, url or "")):
        match = pattern.search(subject)
        if match:
            return f"{int(match.group(1))}.{int(match.group(2))}"
    return None


def _is_chrome(title: str, url: str) -> bool:
    normalized = " ".join((title or "").split()).strip().lower()
    if normalized in _CHROME_TEXT:
        return True
    if len(normalized) > _MAX_TITLE_CHARS:
        return True

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True
    host = (parsed.netloc or "").lower()
    if any(fragment in host for fragment in _CHROME_HOST_FRAGMENTS):
        return True

    # A bare link to the resources index itself is navigation, not a resource.
    if url.rstrip("/") in {page.rstrip("/") for page in FRENCH_RESOURCE_URLS}:
        return True
    return False


def _clean_title(raw: str) -> str:
    """Collapse whitespace and drop trailing punctuation left by the listing markup.

    Titles arrive as `Fiche D'Information Post-Commotion Cérébrale:` — the colon belongs to
    the sentence around the link, not to the resource name.
    """
    collapsed = " ".join((raw or "").split())
    return collapsed.rstrip(" :;,.-–—")


def _content_root(soup: BeautifulSoup):
    """Narrow to the page's content area so headers/footers don't leak in.

    Falls back to the whole document: over-collecting is recoverable (chrome is filtered and
    pairing ignores unmatched entries), whereas selecting nothing loses the page silently.
    """
    for selector in ("main", "article", "div.entry-content", "div.content", "div#content"):
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup


def extract_resources(html: str, *, base_url: str, lang: str) -> List[Resource]:
    """Extract titled resource links from a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    root = _content_root(soup)

    resources: List[Resource] = []
    seen: set[str] = set()

    for anchor in root.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue

        url = urljoin(base_url, href)
        title = anchor.get_text(" ", strip=True)

        if _is_chrome(title, url):
            continue

        # Dedupe on the normalized URL: the live pages list the same resource under both
        # `http://WWW.pedsconcussion.com/reconnaissance/` and the https form.
        key = normalize_url(url)
        if key in seen:
            continue
        seen.add(key)

        resources.append(
            Resource(
                title=_clean_title(title),
                url=url,
                lang=lang,
                source_page=base_url,
                tool_number=extract_tool_number(title, url),
            )
        )

    return resources


def fetch_french_resources(urls: Iterable[str] = FRENCH_RESOURCE_URLS) -> tuple[List[Resource], List[str]]:
    """Fetch and merge the French resource listings. Returns (resources, errors)."""
    merged: Dict[str, Resource] = {}
    errors: List[str] = []

    for page_url in urls:
        try:
            html = fetch_html(page_url)
        except Exception as exc:
            # One page failing must not lose the other; the caller's gates decide whether a
            # partial result is acceptable.
            errors.append(f"{page_url}: {type(exc).__name__}: {exc}")
            continue

        for resource in extract_resources(html, base_url=page_url, lang="fr"):
            # First page wins: /ressources/ is the canonical index.
            merged.setdefault(resource.url, resource)

    return list(merged.values()), errors


def fetch_english_tools(url: str = TOOLS_RESOURCES_URL) -> tuple[List[Resource], List[str]]:
    """Fetch the English tools/resources index using the same extractor as the French side.

    ``core.scraper.extract_living_guideline_tools`` targets only the "Living Guideline Tools"
    heading; the pairing engine needs the full listing, including the "Online Tools and
    Resources" block below it. Both extractors run over the *same* fetched HTML, so tagging
    which entries are Living Guideline Tools costs no extra request.
    """
    try:
        html = fetch_html(url)
    except Exception as exc:
        return [], [f"{url}: {type(exc).__name__}: {exc}"]

    resources = extract_resources(html, base_url=url, lang="en")

    # Which entries sit under the "Living Guideline Tools" heading. This is no longer mere
    # provenance -- `living_tools()` returns exactly these and nothing else -- so a failure here
    # is reported rather than swallowed. The extractor keys off a heading a redesign could
    # rename, and that is precisely the case the caller's floors need to see.
    errors: List[str] = []
    try:
        from core.scraper import extract_living_guideline_tools

        living = {
            normalize_url(str(tool.get("url", "")))
            for tool in extract_living_guideline_tools(html, url)
        }
        for resource in resources:
            if normalize_url(resource.url) in living:
                resource.group = GROUP_LIVING_TOOL
        if not living:
            errors.append(
                f"{url}: the 'Living Guideline Tools' heading yielded no tools "
                f"({len(resources)} resources listed on the page). The heading may have been "
                f"renamed or restructured."
            )
    except Exception as exc:
        errors.append(f"{url}: could not identify Living Guideline Tools: {type(exc).__name__}: {exc}")

    return resources, errors


def fetch_all() -> FetchResult:
    english, english_errors = fetch_english_tools()
    french, french_errors = fetch_french_resources()
    return FetchResult(
        english_tools=english,
        french_resources=french,
        errors=english_errors + french_errors,
    )
