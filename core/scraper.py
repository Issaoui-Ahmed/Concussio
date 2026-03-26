from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import re
import threading
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SECTION_INDEX_URL = "https://pedsconcussion.com/section/"
TOOLS_RESOURCES_URL = "https://pedsconcussion.com/tools-resources/"
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
TOOL_PDF_CACHE_TTL_SECONDS = 6 * 60 * 60
TOOL_PDF_EMPTY_CACHE_TTL_SECONDS = 15 * 60
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}

_tool_pdf_cache_lock = threading.Lock()
_tool_pdf_cache: Dict[str, Dict[str, object]] = {}


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


def _find_living_guideline_section_start(soup: BeautifulSoup):
    exact_target = _normalize_heading_text("Living Guideline Tools")

    for heading in soup.find_all(HEADING_TAGS):
        normalized = _normalize_heading_text(heading.get_text(" ", strip=True))
        if normalized == exact_target:
            return heading

    for heading in soup.find_all(HEADING_TAGS):
        normalized = _normalize_heading_text(heading.get_text(" ", strip=True))
        if "living guideline tools" in normalized:
            return heading

    for node in soup.find_all(True):
        if node.name in ("script", "style", "noscript"):
            continue
        normalized = _normalize_heading_text(node.get_text(" ", strip=True))
        if not normalized:
            continue
        if normalized == exact_target or "living guideline tools" in normalized:
            return node

    return None


def _fallback_extract_living_guideline_tools(
    soup: BeautifulSoup,
    base_url: str,
) -> List[Dict[str, str]]:
    tools: List[Dict[str, str]] = []
    seen_urls = set()

    keywords = (
        "concussion",
        "tool",
        "algorithm",
        "protocol",
        "diagnostic",
        "school",
        "return",
        "recognition",
        "assessment",
        "checklist",
        "letter",
        "monitor",
        "symptom",
        "sport",
        "activity",
        "physical",
        "acrm",
        "pecarn",
        "catch2",
        "scat",
        "scoat",
    )

    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        if not _is_candidate_http_url(url):
            continue
        if url in seen_urls:
            continue

        title = anchor.get_text(" ", strip=True) or url
        if len(title) < 6:
            continue

        haystack = f"{title} {url}".lower()
        score = 0
        if any(keyword in haystack for keyword in keywords):
            score += 20
        if "living guideline" in haystack:
            score += 10
        if _is_probable_pdf_url(url):
            score += 12
        if "/wp-content/uploads/" in url.lower():
            score += 8
        if "/tools-resources/" in url.lower() or "/publications/" in url.lower():
            score -= 20

        if score < 20:
            continue

        tools.append({"title": title, "url": url})
        seen_urls.add(url)

    return tools


def extract_living_guideline_tools(
    html: str,
    base_url: str = TOOLS_RESOURCES_URL,
) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    tools: List[Dict[str, str]] = []
    seen_urls = set()

    start_node = _find_living_guideline_section_start(soup)
    if start_node is not None:
        for anchor in start_node.find_all("a", href=True):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue

            url = urljoin(base_url, href)
            if url in seen_urls:
                continue

            title = anchor.get_text(" ", strip=True) or url
            tools.append({"title": title, "url": url})
            seen_urls.add(url)

        for sibling in start_node.next_siblings:
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

    if tools:
        return tools

    return _fallback_extract_living_guideline_tools(soup, base_url)


def _is_probable_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    return path.endswith(".pdf")


def _is_candidate_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _normalize_cache_key(url: str) -> str:
    return url.strip()


def _get_cached_pdf_urls(url: str) -> Optional[List[str]]:
    key = _normalize_cache_key(url)
    if not key:
        return None
    now = datetime.now(timezone.utc)
    with _tool_pdf_cache_lock:
        entry = _tool_pdf_cache.get(key)
        if not entry:
            return None
        fetched_at = entry.get("fetched_at")
        pdf_urls = entry.get("pdf_urls")
        if not isinstance(fetched_at, datetime) or not isinstance(pdf_urls, list):
            return None
        ttl = TOOL_PDF_CACHE_TTL_SECONDS if pdf_urls else TOOL_PDF_EMPTY_CACHE_TTL_SECONDS
        if (now - fetched_at).total_seconds() > ttl:
            return None
        return [url for url in pdf_urls if isinstance(url, str)]


def _set_cached_pdf_urls(url: str, pdf_urls: List[str]) -> None:
    key = _normalize_cache_key(url)
    if not key:
        return
    cleaned = [value for value in pdf_urls if isinstance(value, str) and value]
    with _tool_pdf_cache_lock:
        _tool_pdf_cache[key] = {
            "fetched_at": datetime.now(timezone.utc),
            "pdf_urls": cleaned,
        }


def _keyword_tokens(value: str) -> List[str]:
    parts = re.split(r"[^a-z0-9]+", value.lower())
    return [part for part in parts if len(part) >= 4]


def _pdf_relevance_score(tool_title: str, pdf_url: str) -> int:
    tokens = _keyword_tokens(tool_title)
    if not tokens:
        return 0
    haystack = pdf_url.lower()
    score = 0
    for token in tokens:
        if token in haystack:
            score += 1
    return score


def _collect_candidate_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[tuple[int, int, str]] = []
    seen = set()
    ordinal = 0

    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        if not _is_candidate_http_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)

        combined_text = " ".join(
            [
                anchor.get_text(" ", strip=True),
                (anchor.get("title") or "").strip(),
                (anchor.get("aria-label") or "").strip(),
            ]
        ).lower()

        score = 0
        if _is_probable_pdf_url(url):
            score += 100
        if "pdf" in combined_text:
            score += 40
        if "download" in combined_text:
            score += 30
        if "print" in combined_text:
            score += 10

        candidates.append((score, ordinal, url))
        ordinal += 1

    candidates.sort(key=lambda row: (-row[0], row[1]))
    return [url for _, _, url in candidates]


def _probe_url(url: str, timeout: int = 20) -> tuple[str, str, bool]:
    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        allow_redirects=True,
        stream=True,
    )
    response.raise_for_status()
    final_url = response.url or url
    content_type = (response.headers.get("Content-Type") or "").lower()
    first_chunk = b""
    try:
        for chunk in response.iter_content(chunk_size=16):
            if chunk:
                first_chunk = chunk
                break
    finally:
        response.close()

    is_pdf = (
        _is_probable_pdf_url(final_url)
        or "application/pdf" in content_type
        or first_chunk.startswith(b"%PDF-")
    )
    return final_url, content_type, is_pdf


def _fetch_html_page(url: str, timeout: int = 20) -> str:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text


def resolve_tool_pdf_links(
    tool_url: str,
    *,
    max_hops: int = 2,
    max_candidates_per_page: int = 25,
) -> List[str]:
    if not tool_url or not _is_candidate_http_url(tool_url):
        return []
    if _is_probable_pdf_url(tool_url):
        return [tool_url]

    queue: List[tuple[str, int]] = [(tool_url, 0)]
    visited = set()
    found_pdf_urls: List[str] = []
    seen_pdf_urls = set()

    while queue:
        current_url, depth = queue.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            final_url, content_type, is_pdf = _probe_url(current_url)
        except Exception:
            if _is_probable_pdf_url(current_url) and current_url not in seen_pdf_urls:
                seen_pdf_urls.add(current_url)
                found_pdf_urls.append(current_url)
            continue

        if is_pdf:
            if final_url not in seen_pdf_urls:
                seen_pdf_urls.add(final_url)
                found_pdf_urls.append(final_url)
            continue

        if depth >= max_hops:
            continue

        should_parse_html = "text/html" in content_type or "application/xhtml+xml" in content_type or not content_type
        if not should_parse_html:
            continue

        try:
            page_html = _fetch_html_page(final_url)
        except Exception:
            continue

        links = _collect_candidate_links(page_html, base_url=final_url)
        for next_url in links[:max_candidates_per_page]:
            if next_url not in visited:
                queue.append((next_url, depth + 1))

    return found_pdf_urls


def enrich_living_guideline_tool(tool: Dict[str, str]) -> Dict[str, object]:
    title = tool.get("title", "")
    url = tool.get("url", "")
    cached_pdf_urls = _get_cached_pdf_urls(url)
    if cached_pdf_urls is not None:
        pdf_urls = cached_pdf_urls
    else:
        # Fast path first: shallow crawl with fewer candidates.
        pdf_urls = resolve_tool_pdf_links(url, max_hops=1, max_candidates_per_page=12)
        # Fallback path only when needed.
        if not pdf_urls:
            pdf_urls = resolve_tool_pdf_links(url, max_hops=2, max_candidates_per_page=20)
        _set_cached_pdf_urls(url, pdf_urls)

    if len(pdf_urls) > 1:
        pdf_urls = sorted(
            pdf_urls,
            key=lambda candidate: _pdf_relevance_score(title, candidate),
            reverse=True,
        )
    return {
        "title": title,
        "url": url,
        "pdf_url": pdf_urls[0] if pdf_urls else None,
        "pdf_urls": pdf_urls,
    }


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

    def scrape_single_section(link: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        section_url = link.get("url")
        section_title = link.get("title", "")
        if not section_url:
            return {}

        page_html = fetch_html(section_url)
        return extract_domain_recommendations(
            html=page_html,
            section_title=section_title,
            section_url=section_url,
        )

    ordered_section_payloads: List[Optional[Dict[str, Dict[str, str]]]] = [None] * len(section_links)
    worker_count = min(6, max(1, len(section_links)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(scrape_single_section, link): index
            for index, link in enumerate(section_links)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                ordered_section_payloads[index] = future.result()
            except Exception:
                ordered_section_payloads[index] = {}

    merged: Dict[str, Dict[str, str]] = {}
    for recommendations in ordered_section_payloads:
        if not recommendations:
            continue
        for domain_name, payload in recommendations.items():
            if domain_name in merged and merged[domain_name] != payload:
                section_url = payload.get("section_url", "")
                merged[f"{domain_name} [{section_url}]"] = payload
            else:
                merged[domain_name] = payload

    return merged


def scrape_living_guideline_tools(
    tools_resources_url: str = TOOLS_RESOURCES_URL,
) -> List[Dict[str, object]]:
    page_html = fetch_html(tools_resources_url)
    tools = extract_living_guideline_tools(page_html, base_url=tools_resources_url)

    if not tools:
        return []

    enriched: List[Optional[Dict[str, object]]] = [None] * len(tools)
    worker_count = min(6, max(1, len(tools)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(enrich_living_guideline_tool, tool): idx
            for idx, tool in enumerate(tools)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            tool = tools[idx]
            try:
                enriched[idx] = future.result()
            except Exception:
                enriched[idx] = {
                    "title": tool.get("title", ""),
                    "url": tool.get("url", ""),
                    "pdf_url": None,
                    "pdf_urls": [],
                }

    return [item for item in enriched if item is not None]


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
        self._living_guideline_tools: List[Dict[str, object]] = []

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
                if living_guideline_tools:
                    self._living_guideline_tools = living_guideline_tools
                    self._last_error = None
                else:
                    if self._living_guideline_tools:
                        self._last_error = (
                            "Living Guideline Tools extraction returned no links; "
                            "kept previous cached list."
                        )
                    else:
                        self._last_error = "Living Guideline Tools extraction returned no links."
                self._updated_at = datetime.now(timezone.utc)
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
                    dict(tool)
                    for tool in self._living_guideline_tools
                ],
            }
