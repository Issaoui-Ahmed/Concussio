"""Keep the Fuel IX vector store in step with the Living Guideline Tools listing.

    python -m scripts.content_pipeline.vector_store            # dry run
    python -m scripts.content_pipeline.vector_store --execute  # apply

The comparison is on the LINK, never on file content. `vector_store_files` holds the link set
as of the last run; a fresh scrape is diffed against it and only the difference is acted on:

    link appeared  -> fetch the document as published, upload, attach, record the row
    link vanished  -> remove the file, drop the row -- but only if the pipeline uploaded it
    link unchanged -> nothing at all, no request made

Content hashing would be the obvious alternative and it is wrong here. The 27 adopted files are
hand-made .txt extractions of pages that serve HTML, so comparing downloaded bytes against them
reports "changed" on every run, forever. The link set is the only key where "same" means same.

TWO SAFETY PROPERTIES, both structural rather than conventional:

1. A file is touchable only if `vector_store_files` has a row for it. The combined store also
   holds ten research papers and an IPV supplement, all curated by hand with no upstream link.
   They have no rows, so no scrape result can reach them -- not because of a filename prefix
   somebody could rename away, but because the mapping does not exist.

2. A vanished link retires its file only when the pipeline uploaded it. Removal is permanent:
   `DELETE /vector_stores/{store}/files/{id}` destroys the file object, and `GET
   /files/{id}/content` is a 404 on this API, so a file can be neither detached-but-kept nor
   archived first. Both were checked against the live service. A pipeline file is re-fetchable
   from its URL so losing one costs a download; the 27 adopted files are hand-made .txt
   conversions that exist nowhere else, so those are reported for a human and never removed
   automatically.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit

import requests
from dotenv import load_dotenv

from core.scraper import DEFAULT_HEADERS
from scripts.content_pipeline.fetch import Resource, fetch_english_tools, living_tools
from scripts.content_pipeline.state import (
    StoredFile,
    StoredFileSet,
    UPLOADED_PIPELINE,
    forget_vector_store_file,
    load_vector_store_files,
    record_vector_store_file,
)
from scripts.content_pipeline.urls import normalize_url

load_dotenv()

COMBINED_STORE_NAME = "ConcussCare Coach Knowledge Base"

# A listing that comes back near-empty means the fetch or the page structure broke, not that the
# guideline retired its tools. Publishing that would strip the copilots' retrieval corpus.
MIN_TOOLS = 20

# How much of the stored set a single run may retire. A real edit removes one or two tools; a
# broken selector removes all of them, and this is what turns that into a refusal.
MAX_REMOVAL_RATIO = 0.25

# The same guard in the other direction. Nothing legitimate adds a third of the tool set at
# once; a selector that starts matching the wrong block does exactly that. Without this, a
# heading rename used to mean 69 third-party documents landing in the clinical corpus.
MAX_ADDITION_RATIO = 0.35

# Ceiling on uploads per run, independent of the ratio gate. Each addition is a download plus an
# upload, and this runs inside a Vercel function capped at 300s -- a large legitimate change
# could otherwise time out halfway and leave the store half-written. Rows are recorded per file,
# so whatever does not fit is simply picked up by the next run.
MAX_UPLOADS_PER_RUN = 8

_EXTENSION_BY_TYPE = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


# --- Fuel IX client ---------------------------------------------------------------------------


def _api() -> Tuple[str, Dict[str, str]]:
    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("FUELIX_API_KEY is not set.")
    base = (os.getenv("FUELIX_API_BASE_URL") or "https://api.fuelix.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    product = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product:
        headers["product-id"] = product
    return base, headers


def request(method: str, path: str, **kwargs):
    base, headers = _api()
    if "json" in kwargs:
        headers = {**headers, "Content-Type": "application/json"}
    response = requests.request(method, f"{base}{path}", headers=headers, timeout=120, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"Fuel IX {method} {path} -> {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError:
        return {}


def _data(payload) -> List[dict]:
    items = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def resolve_store_id(name: str = COMBINED_STORE_NAME) -> Optional[str]:
    """Resolved by name, or pinned via FUELIX_TOOLS_VECTOR_STORE_ID.

    By name rather than by a hard-coded id so a store rebuilt under the same name is still
    found; by env var when someone needs to point a run at a copy.
    """
    configured = (os.getenv("FUELIX_TOOLS_VECTOR_STORE_ID") or "").strip()
    if configured:
        return configured
    for store in _data(request("GET", "/vector_stores", params={"limit": 100})):
        if str(store.get("name", "")).strip().lower() == name.lower():
            return str(store.get("id"))
    return None


def store_file_ids(store_id: str) -> set:
    return {str(entry.get("id", "")) for entry in _data(
        request("GET", f"/vector_stores/{store_id}/files", params={"limit": 100})
    )}


# --- fetching the document ---------------------------------------------------------------------


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (value or "").strip()).strip("-")
    return (cleaned[:70] or "tool").lower()


def _extension(url: str, content_type: str) -> str:
    """Extension for the uploaded file, preferring what the server said it served."""
    base = (content_type or "").split(";")[0].strip().lower()
    if base in _EXTENSION_BY_TYPE:
        return _EXTENSION_BY_TYPE[base]
    path = unquote(urlsplit(url or "").path)
    match = re.search(r"(\.[A-Za-z0-9]{2,5})$", path.rstrip("/"))
    return match.group(1).lower() if match else ".html"


@dataclass
class Document:
    content: bytes
    filename: str
    content_type: str


# Page furniture that is not part of the tool. Removed before the text is extracted, so a
# retrieval hit can never be the cookie banner or the site's own navigation.
_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "form", "noscript", "iframe", "svg")
_STRIP_SELECTORS = (
    "#comments", ".comments", ".sidebar", "#sidebar", ".widget", ".menu", ".site-header",
    ".site-footer", ".breadcrumb", ".breadcrumbs", ".share", ".social", ".cookie",
    ".screen-reader-text", "[role=navigation]", "[aria-hidden=true]",
)


def extract_main_content(html: str, url: str) -> Optional[str]:
    """Reduce a tool page to just its content, as Markdown.

    A fetched page is ~94KB of HTML, most of it navigation, footer and cookie banner. Uploading
    that whole thing makes every one of those fragments retrievable text sitting beside the
    27 clean extractions a human made -- so a search for a symptom could match the site's menu.

    Markdown rather than plain text because the structure is worth keeping: headings, lists and
    link targets are what make a tool answerable. Same converter the recommendations corpus
    uses, for the same reason.

    Returns None when nothing usable survives, which the caller treats as a failed fetch rather
    than uploading an empty document.
    """
    from bs4 import BeautifulSoup

    from scripts.content_pipeline.corpus import html_to_markdown

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    for selector in _STRIP_SELECTORS:
        try:
            for node in soup.select(selector):
                node.decompose()
        except Exception:
            # A selector this parser will not accept is not worth failing the upload over.
            continue

    root = None
    for selector in ("main", "article", "div.entry-content", "div.content", "div#content"):
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None:
        root = soup.body or soup

    markdown = html_to_markdown(str(root))
    # Guard against a selector that matched an empty wrapper: a couple of hundred characters is
    # a nav remnant, not a clinical tool.
    return markdown if len(markdown.strip()) >= 200 else None


def fetch_document(resource: Resource) -> Optional[Document]:
    """Fetch a tool, reduced to its content. Returns None if it cannot be had.

    PDFs are uploaded byte for byte -- a PDF already *is* the document, with no page furniture
    to strip. HTML pages are reduced to their main content first.
    """
    try:
        response = requests.get(resource.url, headers=DEFAULT_HEADERS, timeout=120)
        response.raise_for_status()
    except Exception as exc:
        print(f"    ! download failed: {resource.url} ({type(exc).__name__}: {exc})")
        return None

    if not response.content:
        print(f"    ! download returned no bytes: {resource.url}")
        return None

    content_type = (response.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
    slug = _slug(resource.title)

    if content_type == "text/html" or _extension(resource.url, content_type) == ".html":
        markdown = extract_main_content(response.text, resource.url)
        if markdown is None:
            print(f"    ! no usable content extracted: {resource.url}")
            return None
        body = f"# {resource.title}\n\nSource: {resource.url}\n\n{markdown}\n"
        return Document(
            content=body.encode("utf-8"),
            filename=f"{slug}.md",
            content_type="text/markdown",
        )

    return Document(
        content=response.content,
        filename=f"{slug}{_extension(resource.url, content_type)}",
        content_type=(content_type or "application/octet-stream"),
    )


# --- the sync -----------------------------------------------------------------------------------


@dataclass
class SyncReport:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    # Links that vanished but whose file is a hand-made conversion. Reported, never acted on.
    needs_review: List[str] = field(default_factory=list)
    # New links this run did not get to, held back by MAX_UPLOADS_PER_RUN. Not a failure.
    deferred: List[str] = field(default_factory=list)
    unchanged: int = 0
    failures: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    scraped: int = 0
    stored: int = 0
    store_id: str = ""
    dry_run: bool = True

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.failures

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "storeId": self.store_id,
            "scraped": self.scraped,
            "stored": self.stored,
            "added": self.added,
            "removed": self.removed,
            "needsReview": self.needs_review,
            "deferred": self.deferred,
            "unchanged": self.unchanged,
            "failures": self.failures,
            "problems": self.problems,
            "dryRun": self.dry_run,
        }


def plan(
    scraped: Sequence[Resource], stored: StoredFileSet
) -> Tuple[List[Resource], List[StoredFile], List[StoredFile], int]:
    """Diff the scraped link set against the stored one. Pure; makes no requests.

    Returns (to_add, to_remove, needs_review, unchanged). Vanished links split by whether their
    file can be replaced if the removal turns out to be wrong -- see `StoredFile.auto_removable`.
    """
    stored_index = stored.by_url()
    scraped_index = {normalize_url(item.url): item for item in scraped}

    to_add = [item for key, item in scraped_index.items() if key not in stored_index]
    vanished = [item for key, item in stored_index.items() if key not in scraped_index]
    unchanged = len(set(scraped_index) & set(stored_index))

    to_remove = [item for item in vanished if item.auto_removable]
    needs_review = [item for item in vanished if not item.auto_removable]
    return to_add, to_remove, needs_review, unchanged


def gate(
    scraped: Sequence[Resource],
    stored: StoredFileSet,
    vanished: Sequence[StoredFile],
    appeared: Sequence[Resource] = (),
) -> List[str]:
    """Reasons to refuse. Empty means the diff looks like a real content change.

    Guards both directions. The removal ratio counts every vanished link, not just the
    removable ones -- a listing that lost most of its tools is a broken fetch whether or not
    this run would act on it. The addition ratio is the mirror, and it is the one that was
    missing: a selector that starts matching the wrong block of the page shows up as a burst of
    new tools, not as an error.
    """
    problems: List[str] = []
    if len(scraped) < MIN_TOOLS:
        problems.append(f"only {len(scraped)} tools scraped (need >= {MIN_TOOLS})")
    if stored.files and len(vanished) > max(1, int(len(stored.files) * MAX_REMOVAL_RATIO)):
        problems.append(
            f"{len(vanished)} of {len(stored.files)} links vanished "
            f"(> {int(MAX_REMOVAL_RATIO * 100)}%); refusing to act on a suspect listing"
        )
    if stored.files and len(appeared) > max(1, int(len(stored.files) * MAX_ADDITION_RATIO)):
        problems.append(
            f"{len(appeared)} new links against {len(stored.files)} stored "
            f"(> {int(MAX_ADDITION_RATIO * 100)}%); refusing a bulk upload"
        )
    return problems


def sync(*, dry_run: bool = True, english_tools: Optional[Sequence[Resource]] = None) -> SyncReport:
    """Bring the store in step with the tool listing.

    `english_tools` accepts an already-fetched listing so a caller running several sinks fetches
    the page once. Omit it and this fetches its own.
    """
    report = SyncReport(dry_run=dry_run)

    if english_tools is None:
        scraped_all, errors = fetch_english_tools()
        for error in errors:
            report.failures.append(f"fetch: {error}")
        scraped_all = list(scraped_all)
    else:
        scraped_all = list(english_tools)

    scraped = living_tools(scraped_all)
    report.scraped = len(scraped)

    stored = load_vector_store_files()
    if stored.error:
        report.problems.append(f"state: {stored.error}")
        return report
    report.stored = len(stored.files)

    to_add, to_remove, needs_review, unchanged = plan(scraped, stored)
    report.unchanged = unchanged
    report.needs_review = [item.source_url for item in needs_review]

    report.problems.extend(gate(scraped, stored, to_remove + needs_review, to_add))
    if report.problems:
        return report

    # Bounded per run so a large legitimate change cannot time out mid-upload. What is left
    # over is not lost -- the next run diffs against the rows this one wrote and continues.
    if len(to_add) > MAX_UPLOADS_PER_RUN:
        report.deferred = [item.url for item in to_add[MAX_UPLOADS_PER_RUN:]]
        to_add = to_add[:MAX_UPLOADS_PER_RUN]

    if not to_add and not to_remove:
        return report

    store_id = resolve_store_id()
    if not store_id:
        report.problems.append(f'vector store "{COMBINED_STORE_NAME}" not found')
        return report
    report.store_id = store_id

    for resource in to_add:
        report.added.append(resource.url)
        if dry_run:
            continue
        document = fetch_document(resource)
        if document is None:
            report.failures.append(f"download: {resource.url}")
            report.added.remove(resource.url)
            continue
        try:
            uploaded = request(
                "POST", "/files",
                files={
                    "file": (document.filename, document.content, document.content_type),
                    "purpose": (None, "assistants"),
                },
            )
            file_id = str(uploaded.get("id", "")) if isinstance(uploaded, dict) else ""
            if not file_id:
                raise RuntimeError("upload returned no file id")
            request("POST", f"/vector_stores/{store_id}/files", json={"file_id": file_id})
            record_vector_store_file(
                StoredFile(
                    source_url=resource.url,
                    title=resource.title,
                    store_id=store_id,
                    file_id=file_id,
                    filename=document.filename,
                    uploaded_by=UPLOADED_PIPELINE,
                )
            )
        except Exception as exc:
            report.failures.append(f"upload {resource.url}: {exc}")
            report.added.remove(resource.url)

    for entry in to_remove:
        report.removed.append(entry.source_url)
        if dry_run:
            continue
        try:
            # This destroys the file object, not just the attachment -- there is no
            # detach-without-delete on this API. Only reached for pipeline-uploaded files,
            # which the next run can re-fetch from `entry.source_url`.
            request("DELETE", f"/vector_stores/{entry.store_id or store_id}/files/{entry.file_id}")
            forget_vector_store_file(entry.source_url)
        except Exception as exc:
            report.failures.append(f"detach {entry.source_url}: {exc}")
            report.removed.remove(entry.source_url)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply changes. Defaults to dry run.")
    args = parser.parse_args()

    report = sync(dry_run=not args.execute)
    print(f"Vector store sync ({'EXECUTE' if args.execute else 'DRY RUN'})")
    print(f"  scraped {report.scraped} tools, {report.stored} stored, {report.unchanged} unchanged")

    for url in report.added:
        print(f"  + add    {url}")
    for url in report.removed:
        print(f"  - remove {url}")
    for url in report.needs_review:
        print(f"  ? review {url}")
        print("           link is gone, but its file was made by hand and cannot be rebuilt.")
    for url in report.deferred:
        print(f"  … later  {url}  (over the {MAX_UPLOADS_PER_RUN}-upload cap; next run picks it up)")
    if not report.changed and not report.needs_review:
        print("  no link changes")

    for problem in report.problems:
        print(f"  REFUSED: {problem}")
    for failure in report.failures:
        print(f"  FAILED:  {failure}")

    if args.execute and report.changed and report.ok:
        print("\nApplied.")
    elif not args.execute and report.changed:
        print("\nDRY RUN -- nothing changed. Re-run with --execute to apply.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
