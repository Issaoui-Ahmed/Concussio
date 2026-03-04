from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SECTION_INDEX_URL = "https://pedsconcussion.com/section/"
TOOLS_RESOURCES_URL = "https://pedsconcussion.com/tools-resources/"
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


def fetch_html(url: str, timeout: int = 20) -> str:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def extract_section_links(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, str]] = []

    for article in soup.find_all("article", class_="section"):
        h2 = article.find("h2", class_="entry-title")
        if not h2:
            continue
        a_tag = h2.find("a", href=True)
        if not a_tag:
            continue
        results.append(
            {
                "title": a_tag.get_text(strip=True),
                "url": a_tag["href"],
            }
        )

    return results


def _normalize_heading_text(text: str) -> str:
    return " ".join(text.strip().rstrip(":").split()).lower()


def _find_living_guideline_heading(soup: BeautifulSoup):
    exact_target = _normalize_heading_text("Living Guideline Tools")

    for heading in soup.find_all(HEADING_TAGS):
        normalized = _normalize_heading_text(heading.get_text(" ", strip=True))
        if normalized == exact_target:
            return heading

    for heading in soup.find_all(HEADING_TAGS):
        normalized = _normalize_heading_text(heading.get_text(" ", strip=True))
        if "living guideline tools" in normalized:
            return heading

    return None


def extract_living_guideline_tools(
    html: str,
    base_url: str = TOOLS_RESOURCES_URL,
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    heading = _find_living_guideline_heading(soup)
    if heading is None:
        return []

    tools: List[Dict[str, str]] = []
    seen_urls = set()

    for sibling in heading.next_siblings:
        if not getattr(sibling, "name", None):
            continue
        if sibling.name in HEADING_TAGS:
            break

        for anchor in sibling.find_all("a", href=True):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue

            url = urljoin(base_url, href)
            if url in seen_urls:
                continue

            title = anchor.get_text(" ", strip=True) or url
            tools.append({"title": title, "url": url})
            seen_urls.add(url)

    return tools


def _has_classes(tag, *needed: str) -> bool:
    classes = tag.get("class")
    if not classes:
        return False
    return all(name in classes for name in needed)


def _clean_recommendation_text(node) -> str:
    raw_text = node.get_text("\n", strip=True)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(lines)


def _find_recommendation_div(domain_div, next_domain_div):
    for candidate in domain_div.find_all_next("div"):
        if next_domain_div is not None and candidate is next_domain_div:
            break
        if _has_classes(candidate, "recommendations", "et_pb_toggle_item"):
            return candidate
    return None


def _collect_recommendation_content(
    recommendation_div,
    next_domain_div,
) -> List[object]:
    modules: List[object] = [recommendation_div]

    for candidate in recommendation_div.find_all_next("div"):
        if next_domain_div is not None and candidate is next_domain_div:
            break

        classes = candidate.get("class") or []
        if "et_pb_module" not in classes:
            continue

        # Keep top-level modules only to avoid nested duplicate content.
        if candidate.find_parent("div", class_=lambda c: c and "et_pb_module" in c.split()):
            continue

        # Stop before non-recommendation toggle sections.
        if "tools-resources" in classes or "references" in classes:
            break
        if "et_pb_toggle_item" in classes and "recommendations" not in classes:
            break

        # Keep recommendation body modules.
        if "et_pb_text" in classes:
            modules.append(candidate)

    return modules


def extract_domain_recommendations(
    html: str,
    section_title: str,
    section_url: str,
) -> Dict[str, Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: Dict[str, Dict[str, str]] = {}

    domain_divs = [
        div
        for div in soup.find_all("div")
        if _has_classes(div, "domain-name", "et_pb_text_align_left")
    ]

    for idx, domain_div in enumerate(domain_divs):
        span = domain_div.find("span", class_="domain-name")
        if not span:
            continue

        domain_name = span.get_text(strip=True)
        if not domain_name:
            continue

        next_domain_div = domain_divs[idx + 1] if idx + 1 < len(domain_divs) else None
        recommendation_div = _find_recommendation_div(
            domain_div=domain_div,
            next_domain_div=next_domain_div,
        )
        if not recommendation_div:
            continue

        recommendation_modules = _collect_recommendation_content(
            recommendation_div=recommendation_div,
            next_domain_div=next_domain_div,
        )

        recommendation_html = "\n".join(str(module) for module in recommendation_modules)
        recommendation_text_parts: List[str] = []
        for module in recommendation_modules:
            cleaned = _clean_recommendation_text(module)
            if cleaned:
                recommendation_text_parts.append(cleaned)
        recommendation_text = "\n\n".join(recommendation_text_parts)

        out[domain_name] = {
            "section_title": section_title,
            "section_url": section_url,
            "recommendation_html": recommendation_html,
            "recommendation_text": recommendation_text,
        }

    return out


def scrape_all_domain_recommendations(
    section_index_url: str = SECTION_INDEX_URL,
) -> Dict[str, Dict[str, str]]:
    index_html = fetch_html(section_index_url)
    section_links = extract_section_links(index_html)

    merged: Dict[str, Dict[str, str]] = {}
    for link in section_links:
        section_url = link.get("url")
        section_title = link.get("title", "")
        if not section_url:
            continue

        page_html = fetch_html(section_url)
        recommendations = extract_domain_recommendations(
            html=page_html,
            section_title=section_title,
            section_url=section_url,
        )

        for domain_name, payload in recommendations.items():
            if domain_name in merged and merged[domain_name] != payload:
                merged[f"{domain_name} [{section_url}]"] = payload
            else:
                merged[domain_name] = payload

    return merged


def scrape_living_guideline_tools(
    tools_resources_url: str = TOOLS_RESOURCES_URL,
) -> List[Dict[str, str]]:
    page_html = fetch_html(tools_resources_url)
    return extract_living_guideline_tools(page_html, base_url=tools_resources_url)


class ScrapingCache:
    def __init__(
        self,
        refresh_interval_seconds: int = 60,
        section_index_url: str = SECTION_INDEX_URL,
        tools_resources_url: str = TOOLS_RESOURCES_URL,
    ) -> None:
        self.refresh_interval_seconds = refresh_interval_seconds
        self.section_index_url = section_index_url
        self.tools_resources_url = tools_resources_url
        self._lock = threading.Lock()
        self._is_refreshing = False
        self._updated_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._data: Dict[str, Dict[str, str]] = {}
        self._living_guideline_tools: List[Dict[str, str]] = []

    def refresh(self, force: bool = False) -> bool:
        with self._lock:
            if self._is_refreshing:
                return False

            if not force and self._updated_at is not None:
                age_seconds = (datetime.now(timezone.utc) - self._updated_at).total_seconds()
                if age_seconds < self.refresh_interval_seconds:
                    return False

            self._is_refreshing = True

        try:
            scraped = scrape_all_domain_recommendations(self.section_index_url)
            living_guideline_tools = scrape_living_guideline_tools(self.tools_resources_url)
            with self._lock:
                self._data = scraped
                self._living_guideline_tools = living_guideline_tools
                self._updated_at = datetime.now(timezone.utc)
                self._last_error = None
            return True
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            return False
        finally:
            with self._lock:
                self._is_refreshing = False

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            rows = [
                {"domain": domain_name, **payload}
                for domain_name, payload in self._data.items()
            ]
            return {
                "updated_at": self._updated_at.isoformat() if self._updated_at else None,
                "refresh_interval_seconds": self.refresh_interval_seconds,
                "is_refreshing": self._is_refreshing,
                "last_error": self._last_error,
                "domain_count": len(rows),
                "domains": rows,
                "living_guideline_tools_count": len(self._living_guideline_tools),
                "living_guideline_tools": [
                    {"title": tool["title"], "url": tool["url"]}
                    for tool in self._living_guideline_tools
                ],
            }
