"""The chat log for the CHEO REB study: what one record holds, and where it goes.

The approved protocol fixes the contents: "a randomly generated session ID, a timestamp, and the
user type selected (e.g., clinician, youth, coach) in addition to the content of the
conversation." `build_record` produces those fields and nothing else. Language, response time,
IP address and whatever else a request happens to carry stay out: adding a field is a protocol
amendment for the REB to approve first, not a code change.

One record per exchange, one JSON file per record, written into CHEO's SharePoint folder
(`core.sharepoint`) by the same request that produced the answer. The session ID is what ties a
conversation's records together: the browser makes one per chat and sends it with every turn.

The protocol also promises the logs are never stored anywhere else, which rules out the usual
safety nets. No local copy, no retry queue, no conversation text in this server's own logs. A
record that cannot be delivered is reported by its error alone, then dropped.

Nothing here reads participant records back out of CHEO. The only file the app ever reads from
that folder is the test record `run_delivery_test` has just written itself.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import unquote

from core import sharepoint
from core.sharepoint import SharePointError

logger = logging.getLogger(__name__)

# Chat logging is switched on per deployment, apart from being configured, so that a machine
# holding the certificate -- a developer's laptop, a preview deployment -- does not send its own
# test chats into the study folder. The admin test works either way.
SWITCH = "SHAREPOINT_LOG_CHATS"

TEST_FILE_PREFIX = "TEST_"
TEST_USER_TYPE = "Healthcare Professional"
TEST_QUESTION = (
    "Connection test from the Concussio admin page. This is not a participant conversation, "
    "and the file can be deleted."
)
TEST_ANSWER = "If this file is in the study folder, the chatbot's logs are reaching it."

# What CHEO was asked for. A broader Sites.* role would work too; it is reported rather than
# refused, because whether it is acceptable is CHEO's call, not this code's.
REQUESTED_ROLE = "Sites.Selected"


def chat_logging_on() -> bool:
    return (os.getenv(SWITCH) or "").strip().lower() in {"1", "true", "yes", "on"}


def new_session_id() -> str:
    return str(uuid.uuid4())


def clean_session_id(value: str | None) -> str | None:
    """The browser's session ID in canonical form, or None if it is not a UUID. It ends up in a
    file name, so nothing else gets through."""
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def build_record(
    *,
    session_id: str,
    received_at: datetime,
    user_type: str,
    question: str,
    answer: str | None,
) -> dict[str, Any]:
    """One exchange, in the protocol's fields and no others.

    `answer` is None when the chatbot failed to produce one. The question was still asked, and
    which questions fail is part of what quality assurance needs to see.
    """
    return {
        "session_id": session_id,
        "timestamp": received_at.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "user_type": user_type,
        "question": question,
        "answer": answer,
    }


def encode(record: dict[str, Any]) -> bytes:
    # Unescaped, so French reads as French when someone opens the file in SharePoint.
    return json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")


def file_name(record: dict[str, Any], *, test: bool = False) -> str:
    """`2026-10-01T14-03-22.418Z_<session id>.json`: sorts by time, groups by conversation, and
    has no character SharePoint forbids -- hence dashes, not colons, in the time."""
    name = f"{record['timestamp'].replace(':', '-')}_{record['session_id']}.json"
    return f"{TEST_FILE_PREFIX}{name}" if test else name


@dataclass(frozen=True)
class Delivery:
    name: str
    item_id: str
    web_url: str
    size: int
    folder: sharepoint.Folder
    content: bytes


def deliver(record: dict[str, Any], *, test: bool = False) -> Delivery:
    """Write one record into the study folder. Raises SharePointError when it did not land."""
    settings = sharepoint.load_settings()
    content = encode(record)
    item, folder = sharepoint.write_file(settings, file_name(record, test=test), content)
    return Delivery(
        name=str(item.get("name") or ""),
        item_id=str(item["id"]),
        web_url=str(item.get("webUrl") or ""),
        size=int(item.get("size") or len(content)),
        folder=folder,
        content=content,
    )


def log_exchange(
    *,
    session_id: str | None,
    received_at: datetime,
    user_type: str,
    question: str,
    answer: str | None,
) -> None:
    """Record one chat exchange, if chat logging is on here. Never raises.

    Runs inside the participant's request, once the answer is ready and before it is sent, so
    the record is in CHEO's folder by the time the answer is on screen. Deferring it past the
    response would save a second, but a serverless function can be frozen the moment its
    response is out, and a log write that might not happen is not a log.

    A failed delivery is reported and dropped. It never costs the participant the answer.
    """
    if not chat_logging_on():
        return

    record = build_record(
        # A missing or malformed ID still gets a record, just one that can't be linked to the
        # rest of its conversation.
        session_id=clean_session_id(session_id) or new_session_id(),
        received_at=received_at,
        user_type=user_type,
        question=question,
        answer=answer,
    )
    try:
        deliver(record)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        # The error alone. No part of the record goes into this server's logs, not even the
        # session ID: the protocol promises CHEO holds the only copy.
        logger.error("Research log record NOT delivered: %s", exc)


def _colons(thumbprint: str) -> str:
    """The thumbprint as it was emailed to CHEO, pairs separated by colons."""
    return ":".join(thumbprint[index:index + 2] for index in range(0, len(thumbprint), 2))


def status() -> dict[str, Any]:
    """What /admin/research-log shows before anyone runs the test. No network calls."""
    return {
        "chatLogging": chat_logging_on(),
        "missing": sharepoint.missing_settings(),
        "destination": {
            "siteUrl": sharepoint.setting(sharepoint.SITE_URL),
            "folderPath": sharepoint.configured_folder_path(),
            "tenantId": sharepoint.setting(sharepoint.TENANT_ID),
            "clientId": sharepoint.setting(sharepoint.CLIENT_ID),
            "thumbprint": _colons(
                sharepoint.normalized_thumbprint(sharepoint.setting(sharepoint.THUMBPRINT))
            ),
        },
    }


# --- The connection test ----------------------------------------------------------------------


def _check_settings(ctx: dict[str, Any]) -> str:
    ctx["settings"] = sharepoint.load_settings()
    return "Every value is set, and the certificate's private key loads."


def _check_token(ctx: dict[str, Any]) -> str:
    ctx["token"] = sharepoint.access_token(ctx["settings"], fresh=True)
    return "Microsoft Entra accepted the certificate and issued a Graph token."


def _check_permission(ctx: dict[str, Any]) -> str:
    roles = sharepoint.token_roles(ctx["token"])
    if roles is None:
        return (
            "The token's permissions could not be read. The next steps show whether they suffice."
        )
    if not roles:
        raise SharePointError("The token carries no application permissions.", code="noRoles")
    if REQUESTED_ROLE in roles:
        return f"The token carries {REQUESTED_ROLE}."
    return (
        f"The token carries {', '.join(roles)} rather than {REQUESTED_ROLE}. The next steps show "
        "whether that is enough."
    )


def _check_site(ctx: dict[str, Any]) -> str:
    site = sharepoint.get_site(ctx["settings"])
    name = site.get("displayName") or "the site"
    return f"Opened “{name}”: {site.get('webUrl') or ctx['settings'].site_url}"


def _check_folder(ctx: dict[str, Any]) -> str:
    folder = sharepoint.resolve_folder(ctx["settings"], fresh=True)
    return f"Found {unquote(folder.web_url) or ctx['settings'].folder_path}"


def _check_write(ctx: dict[str, Any]) -> str:
    # The same two calls a chat exchange makes, so what lands is byte-for-byte what a
    # participant's exchange would produce. Only the content and the TEST_ prefix differ.
    record = build_record(
        session_id=new_session_id(),
        received_at=datetime.now(timezone.utc),
        user_type=TEST_USER_TYPE,
        question=TEST_QUESTION,
        answer=TEST_ANSWER,
    )
    ctx["delivery"] = delivery = deliver(record, test=True)
    return (
        f"Wrote {delivery.name} ({delivery.size:,} bytes) through the code every chat exchange "
        "uses."
    )


def _check_readback(ctx: dict[str, Any]) -> str:
    delivery: Delivery = ctx["delivery"]
    ctx["stored"] = stored = sharepoint.download(ctx["settings"], delivery.folder, delivery.item_id)
    if stored != delivery.content:
        raise SharePointError(
            "The file in SharePoint is not identical to what the app sent.", code="mismatch"
        )
    return "The file in SharePoint is identical, byte for byte, to what the app sent."


_TEST_STEPS: tuple[tuple[str, str, Callable[[dict[str, Any]], str]], ...] = (
    ("settings", "Settings", _check_settings),
    ("token", "Sign in to Microsoft", _check_token),
    ("permission", "Permission on the token", _check_permission),
    ("site", "Open the site", _check_site),
    ("folder", "Find the folder", _check_folder),
    ("write", "Write a test record", _check_write),
    ("readback", "Read it back from SharePoint", _check_readback),
)

_TOKEN_HINTS = {
    "AADSTS7000112": (
        "The app registration is switched off. CHEO keeps it off until safelisting is approved, "
        "so this is expected until they say it's done."
    ),
    "AADSTS700016": (
        "Entra has no app with this client ID in this tenant. Check SHAREPOINT_CLIENT_ID and "
        "SHAREPOINT_TENANT_ID."
    ),
    "AADSTS90002": "No such tenant. Check SHAREPOINT_TENANT_ID.",
    "AADSTS900023": "SHAREPOINT_TENANT_ID is not a valid tenant ID.",
    "AADSTS700027": (
        "The app registration has no certificate matching this key. CHEO needs to upload the "
        "certificate with thumbprint {thumbprint}, and SHAREPOINT_CERT_PRIVATE_KEY_B64 must be "
        "its private key."
    ),
    "AADSTS700024": "Entra rejected the assertion's time window. Check this machine's clock.",
}


def _hint(step: str, exc: Exception, ctx: dict[str, Any]) -> str | None:
    """What to do about a failure, where the error alone does not make that obvious."""
    status = getattr(exc, "status", None)
    if step == "settings":
        return (
            "Set it in .env to test locally, or in the Vercel project env for a deployment "
            "(a change there takes a redeploy)."
        )
    if step == "token":
        hint = _TOKEN_HINTS.get(getattr(exc, "code", None) or "")
        if hint and ctx.get("settings"):
            hint = hint.format(thumbprint=_colons(ctx["settings"].thumbprint))
        return hint
    if step == "permission":
        return (
            "CHEO has not yet granted admin consent for Microsoft Graph Sites.Selected to the app."
        )
    if step == "site" and status == 403:
        return (
            "The app signs in but has no grant on this site yet. CHEO needs to give it write on "
            "the site, a separate step from consenting to Sites.Selected."
        )
    if step == "site" and status == 404:
        return "Nothing at SHAREPOINT_SITE_URL. Check the address."
    if step == "folder" and status == 404:
        return (
            "SHAREPOINT_FOLDER_PATH is the library, then the folder, as they read in the "
            "folder's address after the site: for example Files/My Folder."
        )
    if step == "write" and status == 403:
        return (
            "The app can read the site but not write to it: CHEO's site grant needs to be write, "
            "not read."
        )
    return None


def run_delivery_test() -> dict[str, Any]:
    """Prove the whole path, one step at a time, stopping at the first that fails.

    The record is written with `deliver` -- the function every chat exchange goes through -- and
    then read back and compared, so a pass means the bytes in CHEO's folder are exactly what a
    participant's exchange would put there. The file stays, named TEST_..., so CHEO can see it
    arrive too.
    """
    ctx: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    failed = False

    for key, label, check in _TEST_STEPS:
        if failed:
            steps.append({"key": key, "label": label, "status": "skipped"})
            continue
        started = time.perf_counter()
        try:
            detail, outcome, hint = check(ctx), "ok", None
        except Exception as exc:  # noqa: BLE001 -- a failure is the result, never a 500
            failed = True
            detail, outcome = str(exc) or exc.__class__.__name__, "failed"
            hint = _hint(key, exc, ctx)
        steps.append(
            {
                "key": key,
                "label": label,
                "status": outcome,
                "detail": detail,
                "hint": hint,
                "ms": round((time.perf_counter() - started) * 1000),
            }
        )

    delivery: Delivery | None = ctx.get("delivery")
    stored: bytes | None = ctx.get("stored")
    return {
        "ok": not failed,
        "chatLogging": chat_logging_on(),
        "steps": steps,
        "file": (
            {"name": delivery.name, "webUrl": delivery.web_url, "size": delivery.size}
            if delivery
            else None
        ),
        "stored": stored.decode("utf-8", errors="replace") if stored is not None else None,
    }
