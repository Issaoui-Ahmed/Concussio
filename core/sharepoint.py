"""Write into one SharePoint folder through Microsoft Graph, signed in as the application.

Built for the CHEO study's chat log (`core.research_log`), where the folder is CHEO's and so is
the permission. The app proves who it is with a certificate: it signs a short-lived assertion
with the private key, and Microsoft Entra trades that for a Graph token. There is no user, no
password and no client secret anywhere in this flow.

What that token may touch is decided entirely on CHEO's side, in two steps that are easy to
conflate:

    consent      the app registration is granted Microsoft Graph `Sites.Selected`. On its own
                 this opens nothing: the token carries the permission, but no site has said yes.
    site grant   a SharePoint admin gives the app `write` on the one site holding the folder.

They fail differently -- no consent is a token without roles, no site grant is a 403 from the
site -- which is why the admin test (`research_log.run_delivery_test`) checks them separately.
"""

from __future__ import annotations

import base64
import binascii
import functools
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

LOGIN_BASE_URL = "https://login.microsoftonline.com"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

REQUEST_TIMEOUT_SECONDS = 15
# A token lasts about an hour. It is renewed a few minutes early so one never expires between
# leaving the cache and reaching Graph.
TOKEN_RENEW_MARGIN_SECONDS = 300
# Graph asks for a pause with 429/503 and a Retry-After header. One retry, capped: this runs
# inside a participant's chat request, which is not the place to sit out a long throttle.
MAX_RETRY_AFTER_SECONDS = 5

TENANT_ID = "SHAREPOINT_TENANT_ID"
CLIENT_ID = "SHAREPOINT_CLIENT_ID"
SITE_URL = "SHAREPOINT_SITE_URL"
FOLDER_PATH = "SHAREPOINT_FOLDER_PATH"
PRIVATE_KEY = "SHAREPOINT_CERT_PRIVATE_KEY_B64"
THUMBPRINT = "SHAREPOINT_CERT_THUMBPRINT"
SETTING_NAMES = (TENANT_ID, CLIENT_ID, SITE_URL, FOLDER_PATH, PRIVATE_KEY, THUMBPRINT)


class SharePointError(RuntimeError):
    """A step that failed, worded for whoever reads the admin test.

    `status` is the HTTP status when there was one. `code` is Graph's error code or Entra's
    AADSTS number -- what the test's hints key on.
    """

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    site_url: str
    # The library, then the folder inside it, as they read in the folder's address after the
    # site: .../sites/<site>/Files/My%20Folder is "Files/My Folder".
    folder_path: str
    private_key: rsa.RSAPrivateKey
    # SHA-1, upper-case hex, no separators: what Entra displays next to the certificate, and
    # what the assertion's `x5t` header encodes.
    thumbprint: str


@dataclass(frozen=True)
class Folder:
    drive_id: str
    item_id: str
    web_url: str


def setting(name: str) -> str:
    """Trimmed, because these are pasted into the Vercel env UI, where a trailing newline is
    invisible."""
    return (os.getenv(name) or "").strip()


def missing_settings() -> list[str]:
    return [name for name in SETTING_NAMES if not setting(name)]


def normalized_thumbprint(value: str) -> str:
    """Entra shows the thumbprint bare; certificate tools print it with colons. Both work."""
    return re.sub(r"[\s:]", "", value).upper()


def configured_folder_path() -> str:
    # Accepts the path copied straight out of an address bar, %20s and all.
    return unquote(setting(FOLDER_PATH)).strip("/")


@functools.lru_cache(maxsize=4)
def _load_private_key(encoded: str) -> rsa.RSAPrivateKey:
    """Cached: validating an RSA key costs milliseconds, and this runs on every exchange."""
    try:
        pem = base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SharePointError(f"{PRIVATE_KEY} is not valid base64.") from exc
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except (TypeError, ValueError) as exc:
        raise SharePointError(
            f"{PRIVATE_KEY} does not decode to an unencrypted PEM private key."
        ) from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise SharePointError(f"{PRIVATE_KEY} holds a {type(key).__name__}; it must be RSA.")
    return key


def load_settings() -> Settings:
    missing = missing_settings()
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        raise SharePointError(f"Not configured: {', '.join(missing)} {verb} empty.")

    thumbprint = normalized_thumbprint(setting(THUMBPRINT))
    if not re.fullmatch(r"[0-9A-F]{40}", thumbprint):
        raise SharePointError(
            f"{THUMBPRINT} should be the certificate's 40-character SHA-1 thumbprint, as Entra "
            "shows it."
        )

    site = urlsplit(setting(SITE_URL))
    if site.scheme != "https" or not site.hostname or not site.path.strip("/"):
        raise SharePointError(
            f"{SITE_URL} should look like https://<tenant>.sharepoint.com/sites/<site>."
        )

    return Settings(
        tenant_id=setting(TENANT_ID),
        client_id=setting(CLIENT_ID),
        site_url=setting(SITE_URL).rstrip("/"),
        folder_path=configured_folder_path(),
        private_key=_load_private_key(setting(PRIVATE_KEY)),
        thumbprint=thumbprint,
    )


# --- Signing in -------------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_segment(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _client_assertion(settings: Settings) -> str:
    """The signed JWT Entra accepts in place of a client secret.

    Microsoft's certificate-credential format: RS256, the certificate's SHA-1 thumbprint in
    `x5t` (how Entra picks which of the app's certificates checks the signature), the token
    endpoint as audience, the app as issuer and subject. Ten minutes is plenty for one request.
    """
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "x5t": _b64url(bytes.fromhex(settings.thumbprint))}
    claims = {
        "aud": f"{LOGIN_BASE_URL}/{settings.tenant_id}/oauth2/v2.0/token",
        "iss": settings.client_id,
        "sub": settings.client_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }
    signing_input = f"{_json_segment(header)}.{_json_segment(claims)}"
    signature = settings.private_key.sign(
        signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
    )
    return f"{signing_input}.{_b64url(signature)}"


def _json_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


_AADSTS_RE = re.compile(r"AADSTS(\d+)")


def _entra_error(status: int, payload: Any) -> SharePointError:
    """Entra's refusal, cut to its first line: the rest is trace and correlation ids."""
    description = ""
    if isinstance(payload, dict):
        description = str(payload.get("error_description") or payload.get("error") or "").strip()
    message = description.splitlines()[0].strip() if description else ""
    match = _AADSTS_RE.search(description)
    return SharePointError(
        message or f"Microsoft Entra refused the sign-in (HTTP {status}).",
        status=status,
        code=f"AADSTS{match.group(1)}" if match else None,
    )


_token_lock = threading.Lock()
_tokens: dict[tuple[str, str, str], tuple[str, float]] = {}


def access_token(settings: Settings, *, fresh: bool = False) -> str:
    """An app-only Graph token, cached per warm instance.

    `fresh` skips the cache. The admin test asks for that: a token carries the permissions the
    app had when it was issued, so a cached one would still say "none" right after CHEO
    grants consent.
    """
    key = (settings.tenant_id, settings.client_id, settings.thumbprint)
    if not fresh:
        with _token_lock:
            cached = _tokens.get(key)
        if cached and cached[1] - time.time() > TOKEN_RENEW_MARGIN_SECONDS:
            return cached[0]

    try:
        response = requests.post(
            f"{LOGIN_BASE_URL}/{quote(settings.tenant_id, safe='')}/oauth2/v2.0/token",
            data={
                "client_id": settings.client_id,
                "scope": GRAPH_SCOPE,
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": _client_assertion(settings),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SharePointError(
            f"Could not reach Microsoft Entra ({exc.__class__.__name__})."
        ) from exc

    payload = _json_body(response)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if response.status_code != 200 or not isinstance(token, str):
        raise _entra_error(response.status_code, payload)

    try:
        lifetime = int(payload.get("expires_in", 3599))
    except (TypeError, ValueError):
        lifetime = 3599
    with _token_lock:
        _tokens[key] = (token, time.time() + lifetime)
    return token


def token_roles(token: str) -> list[str] | None:
    """The application permissions a token carries, or None when it cannot be read.

    Diagnostics only: Graph tokens are meant to be opaque to clients, so nothing may depend on
    this beyond the admin test explaining why a later step is about to fail.
    """
    try:
        body = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError):
        return None
    roles = claims.get("roles") if isinstance(claims, dict) else None
    return [role for role in roles if isinstance(role, str)] if isinstance(roles, list) else []


# --- Graph ------------------------------------------------------------------------------------


def _retry_after(response: requests.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", "1"))
    except ValueError:
        seconds = 1.0
    return min(max(seconds, 1.0), MAX_RETRY_AFTER_SECONDS)


def _graph(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> requests.Response:
    """One Graph call, plus the two retries always worth making: a token that went stale
    early (401), and a throttle (429/503) that says how long to wait."""
    fresh_token = retried_auth = retried_throttle = False
    while True:
        token = access_token(settings, fresh=fresh_token)
        fresh_token = False
        try:
            response = requests.request(
                method,
                f"{GRAPH_BASE_URL}{path}",
                params=params,
                data=data,
                headers={**(headers or {}), "Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise SharePointError(
                f"Could not reach Microsoft Graph ({exc.__class__.__name__})."
            ) from exc

        if response.status_code == 401 and not retried_auth:
            retried_auth = fresh_token = True
            continue
        if response.status_code in (429, 503) and not retried_throttle:
            retried_throttle = True
            time.sleep(_retry_after(response))
            continue
        return response


def _graph_error(response: requests.Response, doing: str) -> SharePointError:
    payload = _json_body(response)
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    text = f"{doing} failed: HTTP {response.status_code}"
    if code:
        text += f" {code}"
    if message:
        text += f" ({message.rstrip('.')})"
    return SharePointError(f"{text}.", status=response.status_code, code=code)


def get_site(settings: Settings) -> dict[str, Any]:
    parts = urlsplit(settings.site_url)
    path = quote(unquote(parts.path.rstrip("/")))
    response = _graph(
        settings,
        "GET",
        f"/sites/{parts.hostname}:{path}",
        params={"$select": "id,displayName,webUrl"},
    )
    if response.status_code != 200:
        raise _graph_error(response, "Opening the site")
    return response.json()


def _find_library(settings: Settings, site_id: str, library: str) -> dict[str, Any]:
    response = _graph(
        settings, "GET", f"/sites/{site_id}/drives", params={"$select": "id,name,webUrl"}
    )
    if response.status_code != 200:
        raise _graph_error(response, "Listing the site's libraries")

    drives = [drive for drive in response.json().get("value") or [] if isinstance(drive, dict)]
    wanted = library.casefold()
    for drive in drives:
        # A library has two names: the one in its address, which is what the folder path is
        # copied from, and a display name that can differ from it. Either is accepted.
        address_name = unquote(urlsplit(str(drive.get("webUrl") or "")).path.rstrip("/"))
        address_name = address_name.rpartition("/")[2]
        if wanted in (address_name.casefold(), str(drive.get("name") or "").casefold()):
            return drive

    found = ", ".join(sorted(str(drive.get("name")) for drive in drives)) or "none"
    raise SharePointError(
        f"The site has no library called “{library}”. Libraries it does have: {found}.",
        status=404,
        code="libraryNotFound",
    )


_folder_lock = threading.Lock()
_folders: dict[tuple[str, str], Folder] = {}


def resolve_folder(settings: Settings, *, fresh: bool = False) -> Folder:
    """The configured folder as Graph ids: three lookups on a cold start, none after.

    `fresh` skips the cache -- for the admin test, and for recovering after the folder moved.
    """
    key = (settings.site_url, settings.folder_path)
    if not fresh:
        with _folder_lock:
            cached = _folders.get(key)
        if cached:
            return cached

    site = get_site(settings)
    library, _, inner = settings.folder_path.partition("/")
    drive = _find_library(settings, str(site["id"]), library)
    location = f"/drives/{drive['id']}/root" + (f":/{quote(inner)}" if inner else "")
    response = _graph(settings, "GET", location, params={"$select": "id,webUrl,folder"})
    if response.status_code == 404:
        raise SharePointError(
            f"There is no folder “{inner}” in the “{library}” library.",
            status=404,
            code="itemNotFound",
        )
    if response.status_code != 200:
        raise _graph_error(response, "Opening the folder")

    item = response.json()
    if "folder" not in item:
        raise SharePointError(
            f"“{inner}” in the “{library}” library is a file, not a folder."
        )

    folder = Folder(
        drive_id=str(drive["id"]),
        item_id=str(item["id"]),
        web_url=str(item.get("webUrl") or ""),
    )
    with _folder_lock:
        _folders[key] = folder
    return folder


def upload(
    settings: Settings,
    folder: Folder,
    filename: str,
    content: bytes,
    content_type: str = "application/json",
) -> dict[str, Any]:
    """Create `filename` in `folder`. Never overwrites: on a clash SharePoint picks a new name."""
    response = _graph(
        settings,
        "PUT",
        f"/drives/{folder.drive_id}/items/{folder.item_id}:/{quote(filename)}:/content"
        "?@microsoft.graph.conflictBehavior=rename",
        headers={"Content-Type": content_type},
        data=content,
    )
    if response.status_code not in (200, 201):
        raise _graph_error(response, "Writing the file")
    return response.json()


def write_file(settings: Settings, filename: str, content: bytes) -> tuple[dict[str, Any], Folder]:
    folder = resolve_folder(settings)
    try:
        return upload(settings, folder, filename, content), folder
    except SharePointError as exc:
        if exc.status != 404:
            raise
    # The cached folder id no longer resolves: the folder was moved, renamed or recreated since
    # this instance looked it up. Look again, once.
    folder = resolve_folder(settings, fresh=True)
    return upload(settings, folder, filename, content), folder


def download(settings: Settings, folder: Folder, item_id: str) -> bytes:
    # Graph answers with a redirect to a pre-authenticated download address. requests follows it
    # and drops the Authorization header on the way, since the host changes.
    response = _graph(settings, "GET", f"/drives/{folder.drive_id}/items/{item_id}/content")
    if response.status_code != 200:
        raise _graph_error(response, "Reading the file back")
    return response.content
