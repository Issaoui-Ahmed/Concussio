"""Published resource titles for response formatting; never derive titles from filenames."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[([^\]\n]+)\]\(<?(https?://[^\s)<>]+)>?\)")
TOOL_NUMBER_RE = re.compile(r"\b(?:Tool|Outil)[\s_-]*(\d{1,2})[._-](\d{1,2})(?!\d)", re.I)


@dataclass(frozen=True)
class Tool:
    number: str
    title: str
    url: str

    @property
    def label(self) -> str:
        return f"Tool {self.number}: {self.title}"


def tool_number(text: str) -> str | None:
    match = TOOL_NUMBER_RE.search(unquote(text))
    return f"{int(match[1])}.{int(match[2])}" if match else None


def url_key(url: str) -> tuple[str, str]:
    parts = urlsplit(unquote(url.strip("<>")))
    return parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/")


def _title(title: str, number: str) -> str:
    title = re.sub(r"^(?:Tool|Outil)\s*\d+[.\d]*\s*[:–—-]?\s*", "", title, flags=re.I)
    title = " ".join(title.replace("**", "").split())
    # Jenny's requested public label, for the document published under a Template filename.
    if number == "12.2":
        return "Letter of Accommodation from the Concussion Care Team to the School"
    return title


def tools_from_corpus(corpus: str) -> dict[str, Tool]:
    tools = {}
    for line in corpus.splitlines():
        end = 0
        for match in LINK_RE.finditer(line):
            # Do not accidentally give a later unrelated link the preceding tool's number.
            number = tool_number(match[1]) or tool_number(match[2]) or tool_number(line[end:match.start()])
            if number:
                tools[number] = Tool(number, _title(match[1], number), match[2])
            end = match.end()
    return tools


@lru_cache(maxsize=1)
def _bundled_tools() -> dict[str, Tool]:
    return tools_from_corpus((ROOT / "all_rec_markdown.md").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _published_tools(bucket: int) -> dict[str, Tool]:
    # This table is maintained by the existing content refresh. An outage uses the bundled
    # corpus; no web scraping or guessed PDF paths on the chat request path.
    from scripts.content_pipeline.state import is_configured, load_vector_store_files

    tools = dict(_bundled_tools())
    if is_configured():
        for item in load_vector_store_files().files:
            number = tool_number(item.title) or tool_number(item.source_url)
            if number and item.title:
                tools[number] = Tool(number, _title(item.title, number), item.source_url)
    return tools


def response_tools() -> dict[str, Tool]:
    return _published_tools(int(time.monotonic() // 300))
