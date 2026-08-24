"""The API half of the demo password gate.

The front end asks for the password before it renders anything (`lib/demoAccess.ts`) and, once
it matches, hands the browser an httpOnly cookie holding
`sha256("concussio-demo-access:<password>")`. This module recomputes that value from the same
DEMO_PASSWORD environment variable, so the two halves of the app agree on who is let in with no
second secret to keep in sync.

Without this, the page gate would be the whole of the protection and `/api/chat` would remain a
public, billable endpoint for anyone who reads the network tab once.
"""

from __future__ import annotations

import hashlib
import hmac
import os

COOKIE_NAME = "concussio_demo_access"

# The chatbot itself: the three endpoints that answer visitors and spend model credits.
#
# Deliberately not listed: /api/cron/refresh, which carries its own CRON_SECRET, and the
# /api/admin, /api/fuelix, /api/scraping and /api/resource-links tooling, which is reached from
# /admin pages that sit behind the same gate. Adding a path here requires that every caller of
# it be a browser holding the cookie -- the batch tool under /admin posts to /api/chat, which is
# why /admin is gated too.
GATED_PATHS = frozenset({"/api/chat", "/api/followups", "/api/translate"})


def access_token(password: str) -> str:
    return hashlib.sha256(f"concussio-demo-access:{password}".encode("utf-8")).hexdigest()


def configured_password() -> str | None:
    """Trimmed to match the front end, which trims for the same reason: the value is pasted
    into a Vercel environment variable, where a trailing newline is invisible."""
    password = (os.getenv("DEMO_PASSWORD") or "").strip()
    return password or None


def denial_for(path: str, cookie: str | None) -> tuple[int, str] | None:
    """The status and message to answer with, or None to let the request through."""
    if path not in GATED_PATHS:
        return None

    password = configured_password()
    if not password:
        # Fails closed, like the page gate: an unset variable locks the prototype rather than
        # quietly serving it to the open internet.
        return 503, "DEMO_PASSWORD is not configured; the chatbot is locked."

    if not cookie or not hmac.compare_digest(cookie, access_token(password)):
        return 401, "Enter the demo password to use the chatbot."

    return None
