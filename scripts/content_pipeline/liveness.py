"""Liveness gate: probe URLs and classify what came back.

Status 200 is not sufficient. Two failure modes this catches that a plain status check does
not, both found in the wild on this content:

- **soft-404**: `5pconcussion.com/fr/scorecalculator` returns 200 and redirects to the site
  root. The page does not exist.
- **redirect-to-404-page**: `parinc.com/Products/Pkey/70` returns 200 at `parinc.com/404`.

Some publishers (CDC, BMJ, Elsevier) block scripted requests outright and return 403/429 for
URLs that are perfectly alive in a browser. Those hosts are allowlisted so the gate does not
fail the build over a bot policy.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import requests

from scripts.content_pipeline.urls import redirects_to_root

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Hosts that reject scripted traffic regardless of UA. Verified manually in a real browser
# on 2026-07-29: cdc.gov serves 403 to every scripted request, including its *current* URLs,
# so a 403 from these hosts carries no information about whether the page exists.
BOT_BLOCKED_HOSTS = (
    "cdc.gov",
    "bjsm.bmj.com",
    "archives-pmr.org",
    "sciencedirect.com",
    "linkinghub.elsevier.com",
)

OK = "ok"
BOT_BLOCKED = "bot-blocked"
SOFT_404 = "soft-404"
DEAD = "dead"
ERROR = "error"


@dataclass
class Probe:
    url: str
    status: Optional[int]
    final_url: str
    verdict: str
    detail: str = ""

    @property
    def is_failure(self) -> bool:
        return self.verdict in (SOFT_404, DEAD, ERROR)


def _is_bot_blocked_host(url: str) -> bool:
    return any(host in url for host in BOT_BLOCKED_HOSTS)


def probe_url(url: str, *, timeout: int = 30) -> Probe:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": BROWSER_UA},
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        status, final = response.status_code, response.url
        response.close()
    except Exception as exc:
        return Probe(url, None, "", ERROR, f"{type(exc).__name__}: {exc}")

    if status != 200:
        if _is_bot_blocked_host(url):
            return Probe(url, status, final, BOT_BLOCKED, "host blocks scripted requests")
        return Probe(url, status, final, DEAD, f"HTTP {status}")

    # 200, but did it actually land anywhere?
    if redirects_to_root(final) and not redirects_to_root(url):
        return Probe(url, status, final, SOFT_404, f"redirected to root: {final}")
    if final.rstrip("/").endswith("/404"):
        return Probe(url, status, final, SOFT_404, f"redirected to a 404 page: {final}")

    return Probe(url, status, final, OK)


def probe_all(urls: Iterable[str], *, workers: int = 8) -> List[Probe]:
    unique = sorted({url for url in urls if url})
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(probe_url, unique))


def summarize(probes: Iterable[Probe]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for probe in probes:
        counts[probe.verdict] = counts.get(probe.verdict, 0) + 1
    return counts
