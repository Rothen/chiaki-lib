"""PSN sign-in, shared by 1.1_login.py and 1.3_auto_register_console.py: the OAuth login URL,
exchanging the code it ends with for tokens, refreshing those, and the account they belong to.
Everything is kept in cache/psn_account.json.

The flow is chiaki-ng's (gui/include/psnaccountid.h, gui/src/psntoken.cpp).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests

from chiaki_lib import Backend

CLIENT_ID = "ba495a24-818c-472b-b12d-ff231c1b5745"
CLIENT_SECRET = "mvaiZkRsAsI1IBkY"
REDIRECT_URL = "https://remoteplay.dl.playstation.net/remoteplay/redirect"
SCOPE = (
    "psn:clientapp referenceDataService:countryConfig.read "
    "pushNotification:webSocket.desktop.connect sessionManager:remotePlaySession.system.update"
)
AUTHORIZE_URL = (
    "https://auth.api.sonyentertainmentnetwork.com/"
    "2.0/oauth/authorize?service_entity=urn:service-entity:psn"
    f"&response_type=code&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URL}"
    # Percent-encoded: with literal spaces, terminals and copy-paste cut the URL off after the
    # first scope, and PSN then grants only psn:clientapp, which PSN sessions get a 401 with.
    f"&scope={quote(SCOPE)}"
    "&request_locale=en_US"
    "&ui=pr"
    "&service_logo=ps"
    "&layout_type=popup"
    "&smcid=remoteplay"
    "&prompt=always"
    "&PlatformPrivacyWs1=minimal&"
)
TOKEN_URL = "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/token"
PSN_ACCOUNT_FILE = Path("./cache", "psn_account.json")
# Refresh the access token when it expires within this many seconds, like chiaki-ng does.
REFRESH_MARGIN_SECONDS = 60


@dataclass
class PSNTokens:
    """The OAuth tokens of a signed-in account. `access_token` is what Settings.set_psn_auth_token()
    and Backend.list_psn_devices() take; it expires at `expires_at` (Unix time), after which
    `refresh_token` gets a new one."""

    access_token: str
    refresh_token: str
    expires_at: float


@dataclass
class PSNAccount:
    """A signed-in PSN account. `user_rpid` is the base64 account-ID `register_host()` and
    Settings.set_psn_account_id() expect for a PS5 (or a PS4 in "PS4 8.0" mode); `online_id` is
    what an older PS4 expects there instead."""

    scopes: str
    expiration: str
    client_id: str
    dcim_id: str
    grant_type: str
    user_id: str
    user_uuid: str
    online_id: str
    country_code: str
    language_code: str
    community_domain: str
    is_sub_account: bool
    user_rpid: str
    credentials: str
    tokens: PSNTokens | None = None


def login_url() -> str:
    """The URL to sign in at. chiaki-ng adds a fresh device ID for this client to it."""
    return f"{AUTHORIZE_URL}duid={Backend.generate_client_device_uid()}&"


def parse_code(redirect_url: str) -> str:
    """Extract the OAuth `code` from the URL PSN's login page redirects to."""
    if not redirect_url.startswith(REDIRECT_URL):
        raise ValueError(f"URL does not start with {REDIRECT_URL}")
    code = parse_qs(urlparse(redirect_url).query).get("code")
    if not code or len(code[0]) <= 1:
        raise ValueError("URL carries no code")
    return code[0]


def _request_tokens(form: dict[str, str], previous_refresh_token: str = "") -> PSNTokens:
    resp = requests.post(
        TOKEN_URL,
        data={**form, "scope": SCOPE, "redirect_uri": REDIRECT_URL},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=10,
    )
    if resp.status_code != 200:
        raise ValueError(f"Error getting token: HTTP {resp.status_code}")
    info = resp.json()
    if "access_token" not in info:
        raise ValueError("Response carries no access token")
    return PSNTokens(
        access_token=info["access_token"],
        refresh_token=info.get("refresh_token", previous_refresh_token),
        expires_at=time.time() + int(info.get("expires_in", 0)),
    )


def get_tokens(code: str) -> PSNTokens:
    """Exchange the `code` from the login redirect for tokens."""
    return _request_tokens({"grant_type": "authorization_code", "code": code})


def refresh_tokens(tokens: PSNTokens) -> PSNTokens:
    """Get a new access token with the refresh token."""
    return _request_tokens({"grant_type": "refresh_token", "refresh_token": tokens.refresh_token}, tokens.refresh_token)


def fetch_account(access_token: str) -> PSNAccount:
    """The account `access_token` belongs to."""
    resp = requests.get(f"{TOKEN_URL}/{access_token}", auth=(CLIENT_ID, CLIENT_SECRET), timeout=10)
    if resp.status_code != 200:
        raise ValueError(f"Error getting account: HTTP {resp.status_code}")

    info = resp.json()
    user_id = info["user_id"]
    return PSNAccount(
        scopes=info["scopes"],
        expiration=info["expiration"],
        client_id=info["client_id"],
        dcim_id=info["dcim_id"],
        grant_type=info["grant_type"],
        user_id=user_id,
        user_uuid=info["user_uuid"],
        online_id=info["online_id"],
        country_code=info["country_code"],
        language_code=info["language_code"],
        community_domain=info["community_domain"],
        is_sub_account=info["is_sub_account"],
        user_rpid=base64.b64encode(int(user_id).to_bytes(8, "little")).decode(),
        credentials=hashlib.sha256(user_id.encode()).hexdigest(),
    )


def save_account(account: PSNAccount) -> None:
    PSN_ACCOUNT_FILE.parent.mkdir(exist_ok=True)
    PSN_ACCOUNT_FILE.write_text(json.dumps(asdict(account), indent=2), encoding="utf-8")


def load_account() -> PSNAccount:
    """The account 1.1_login.py saved. Raises FileNotFoundError if there is none."""
    data: dict[str, Any] = json.loads(PSN_ACCOUNT_FILE.read_text(encoding="utf-8"))
    tokens = data.pop("tokens", None)
    return PSNAccount(**data, tokens=PSNTokens(**tokens) if tokens else None)


def missing_scopes(account: PSNAccount) -> list[str]:
    """The scopes PSN sessions need that the account's token was not granted."""
    granted = set(account.scopes.split())
    return [scope for scope in SCOPE.split() if scope not in granted]


def fresh_access_token(account: PSNAccount) -> str:
    """The account's access token, refreshed first (and saved) if it is about to expire.
    Raises ValueError if the account has no tokens or they can't be refreshed: log in again then."""
    if account.tokens is None:
        raise ValueError("The saved PSN account has no tokens")
    if account.tokens.expires_at - time.time() < REFRESH_MARGIN_SECONDS:
        account.tokens = refresh_tokens(account.tokens)
        save_account(account)
    return account.tokens.access_token
