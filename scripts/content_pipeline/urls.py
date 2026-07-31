"""URL normalization — the Python twin of `normalizeUrl` in lib/i18n/resourceLinks.ts.

Both sides must agree, or the generated table will contain keys the frontend can never
match. The rules are identical: force https, drop `www.`, lowercase the host, strip a
trailing slash, keep path case (some hosts serve case-sensitive paths).
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_url(raw: str) -> str:
    """Canonical form for comparison. Returns the input stripped if it will not parse."""
    value = (raw or "").strip()
    if not value:
        return ""

    try:
        parts = urlsplit(value)
    except ValueError:
        return value

    if not parts.scheme or not parts.netloc:
        return value

    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, parts.query, parts.fragment))


def is_web_url(raw: str) -> bool:
    scheme = urlsplit((raw or "").strip()).scheme.lower()
    return scheme in ("http", "https")


def redirects_to_root(final_url: str) -> bool:
    """True when a redirect landed on a bare domain root.

    A soft-404 signature: `5pconcussion.com/fr/scorecalculator` returns 200 but lands on the
    site root, which a plain status check would happily accept.
    """
    parts = urlsplit((final_url or "").strip())
    return parts.path in ("", "/") and not parts.query
