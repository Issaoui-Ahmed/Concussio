"""The API half of the admin password, for the endpoints that cannot stay open.

Once someone types ADMIN_PASSWORD, `lib/adminAccessAction.ts` gives the browser an httpOnly cookie
holding `sha256("concussio-admin-access:<password>")` on path "/", so it rides along with API
calls too. This module recomputes that value from the same variable, exactly as
`api/demo_access.py` does for the demo cookie. Nothing new to type and no second secret to sync.

Most admin endpoints are still open, by decision (see the README). These are not:

    /api/admin/research-log/*   writes into CHEO's SharePoint, a system that is not ours to
                                leave open to anyone who finds the URL.
    /api/chat, "log": false     keeps the batch tool's test questions out of the study log. A
                                participant sending it must not be able to drop their own
                                exchanges from the study, so it only counts from an admin.
"""

from __future__ import annotations

import hashlib
import hmac
import os

COOKIE_NAME = "concussio_admin_access"


def access_token(password: str) -> str:
    return hashlib.sha256(f"concussio-admin-access:{password}".encode("utf-8")).hexdigest()


def configured_password() -> str | None:
    """Trimmed to match the front end, which trims for the same reason: a trailing newline
    pasted into a Vercel variable is invisible."""
    password = (os.getenv("ADMIN_PASSWORD") or "").strip()
    return password or None


def is_admin(cookie: str | None) -> bool:
    """Fails closed: with no ADMIN_PASSWORD set, nobody is an admin."""
    password = configured_password()
    if not password or not cookie:
        return False
    return hmac.compare_digest(cookie, access_token(password))
