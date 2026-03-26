from __future__ import annotations

from datetime import datetime, timezone
import io
import os
import re
import sys
import textwrap
import unicodedata
import zipfile

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
import requests
from starlette.responses import StreamingResponse

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper import DEFAULT_HEADERS, ScrapingCache


app = FastAPI()
scraping_cache = ScrapingCache(refresh_interval_seconds=60)


@app.get("/")
@app.get("/api/scraping")
def scraping_endpoint(force: bool = False):
    scraping_cache.refresh(force)
    return scraping_cache.snapshot()


def _slugify_filename(raw: str, index: int) -> str:
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_only).strip("-._")
    if not slug:
        slug = f"tool-{index:02d}"
    return slug[:120]


def _unique_pdf_filename(base_name: str, index: int, seen: dict[str, int]) -> str:
    slug = _slugify_filename(base_name, index)
    count = seen.get(slug, 0) + 1
    seen[slug] = count
    if count > 1:
        slug = f"{slug}-{count}"
    return f"{slug}.pdf"


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_text_pdf(lines: list[str]) -> bytes:
    wrapped_lines: list[str] = []
    for line in lines:
        chunks = textwrap.wrap(line, width=95) or [""]
        wrapped_lines.extend(chunks)

    if not wrapped_lines:
        wrapped_lines = ["No content available."]

    lines_per_page = 45
    pages: list[list[str]] = [
        wrapped_lines[i : i + lines_per_page] for i in range(0, len(wrapped_lines), lines_per_page)
    ]

    object_map: dict[int, bytes] = {}
    object_map[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    page_ids: list[int] = []
    font_id = 3 + (len(pages) * 2)

    for page_index, page_lines in enumerate(pages):
        page_id = 3 + (page_index * 2)
        content_id = page_id + 1
        page_ids.append(page_id)

        commands = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
        for line_index, line in enumerate(page_lines):
            escaped_line = _escape_pdf_text(line)
            if line_index == 0:
                commands.append(f"({escaped_line}) Tj")
            else:
                commands.append(f"T* ({escaped_line}) Tj")
        commands.append("ET")
        stream_data = "\n".join(commands).encode("latin-1", errors="replace")

        object_map[content_id] = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode("ascii")
            + stream_data
            + b"\nendstream"
        )
        object_map[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    object_map[2] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")
    object_map[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    max_id = max(object_map)
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: dict[int, int] = {}
    for object_id in range(1, max_id + 1):
        payload = object_map[object_id]
        offsets[object_id] = output.tell()
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(payload)
        output.write(b"\nendobj\n")

    xref_offset = output.tell()
    output.write(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for object_id in range(1, max_id + 1):
        output.write(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))

    output.write(
        (
            f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return output.getvalue()


def _looks_like_pdf(url: str, content_type: str, content: bytes) -> bool:
    if content.startswith(b"%PDF-"):
        return True
    if "application/pdf" in content_type.lower():
        return True
    return url.lower().split("?")[0].endswith(".pdf")


def _fallback_pdf_bytes(title: str, url: str, body_text: str, error_message: str | None = None) -> bytes:
    lines: list[str] = [
        f"Living Guideline Tool: {title}",
        f"Source URL: {url or 'Unavailable'}",
        "",
    ]
    if error_message:
        lines.extend([f"Download error: {error_message}", ""])
    if body_text.strip():
        lines.extend(body_text.strip().splitlines())
    else:
        lines.append("No extractable text was available from this link.")
    return _build_text_pdf(lines)


def _tool_to_pdf_bytes(title: str, url: str) -> bytes:
    if not url:
        return _fallback_pdf_bytes(title, url, "", "Missing URL")

    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=90)
        response.raise_for_status()
        content = response.content
        content_type = response.headers.get("Content-Type", "")

        if _looks_like_pdf(url, content_type, content):
            return content

        text = ""
        if "html" in content_type.lower():
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text("\n", strip=True)
        else:
            text = response.text

        return _fallback_pdf_bytes(title, url, text)
    except Exception as exc:
        return _fallback_pdf_bytes(title, url, "", str(exc))


@app.get("/api/scraping/living-guideline-tools/download")
def download_living_guideline_tools_zip(force: bool = False):
    scraping_cache.refresh(force)
    snapshot = scraping_cache.snapshot()
    tools = snapshot.get("living_guideline_tools")

    if not isinstance(tools, list) or not tools:
        raise HTTPException(status_code=404, detail="No Living Guideline Tools are available to download.")

    zip_buffer = io.BytesIO()
    seen: dict[str, int] = {}

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, tool in enumerate(tools, start=1):
            title = ""
            source_url = ""
            pdf_url = ""
            if isinstance(tool, dict):
                raw_title = tool.get("title")
                raw_url = tool.get("url")
                raw_pdf_url = tool.get("pdf_url")
                title = raw_title if isinstance(raw_title, str) else ""
                source_url = raw_url if isinstance(raw_url, str) else ""
                pdf_url = raw_pdf_url if isinstance(raw_pdf_url, str) else ""
            if not title:
                title = f"Living Guideline Tool {index}"

            filename = _unique_pdf_filename(title, index, seen)
            target_url = pdf_url or source_url
            pdf_bytes = _tool_to_pdf_bytes(title, target_url)
            archive.writestr(f"living-guideline-tools/{filename}", pdf_bytes)

    zip_buffer.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    headers = {"Content-Disposition": f'attachment; filename="living-guideline-tools-{stamp}.zip"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)
