"""Logs in to a PSN account in the terminal and saves it to cache/psn_account.json,
which 1.3_register_console.py needs to pair with a console.

Usage:
    python examples/1.1_login.py

Prints the PSN login URL; open it in a browser, sign in, then paste the URL the
browser ends up on back into the terminal.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

CLIENT_ID = "ba495a24-818c-472b-b12d-ff231c1b5745"
CLIENT_SECRET = "mvaiZkRsAsI1IBkY"
REDIRECT_URL = "https://remoteplay.dl.playstation.net/remoteplay/redirect"
LOGIN_URL = (
    "https://auth.api.sonyentertainmentnetwork.com/"
    "2.0/oauth/authorize?service_entity=urn:service-entity:psn"
    f"&response_type=code&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URL}"
    "&scope=psn:clientapp referenceDataService:countryConfig.read pushNotification:webSocket.desktop.connect sessionManager:remotePlaySession.system.update"
    "&request_locale=en_US"
    "&ui=pr"
    "&service_logo=ps"
    "&layout_type=popup"
    "&smcid=remoteplay"
    "&prompt=always"
    "&PlatformPrivacyWs1=minimal&"
)
TOKEN_URL = "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/token"
TOKEN_BODY = "grant_type=authorization_code" "&code={}" f"&redirect_uri={REDIRECT_URL}&"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


@dataclass
class PSNAccount:
    """A signed-in PSN account. `user_rpid` is the base64 account-ID `register_host()` expects
    as `psn_id` for a PS5 (or a PS4 in "PS4 8.0" mode); `online_id` is what an older PS4
    expects there instead."""

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


def parse_code(redirect_url: str) -> str:
    """Extract the OAuth `code` from the URL PSN's login page redirects to."""
    if not redirect_url.startswith(REDIRECT_URL):
        raise ValueError(f"URL does not start with {REDIRECT_URL}")
    code = parse_qs(urlparse(redirect_url).query).get("code")
    if not code or len(code[0]) <= 1:
        raise ValueError("URL carries no code")
    return code[0]


def get_token(code: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        headers=HEADERS,
        data=TOKEN_BODY.format(code).encode("ascii"),
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=3,
    )
    if resp.status_code != 200:
        raise ValueError(f"Error getting token: HTTP {resp.status_code}")
    token = resp.json().get("access_token")
    if token is None:
        raise ValueError("Response carries no access token")
    return token


def fetch_account(token: str) -> PSNAccount:
    resp = requests.get(
        f"{TOKEN_URL}/{token}",
        headers=HEADERS,
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=3,
    )
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


def login() -> PSNAccount:
    """Print the login URL, read the redirect URL back and exchange it for the account."""
    print("Open this URL in a browser and sign in to your PlayStation account:\n")
    print(LOGIN_URL)
    print(
        "\nAfter signing in you land on a page that starts with "
        f"{REDIRECT_URL}\nCopy the full URL from the browser's address bar and paste it here."
    )
    redirect_url = input("\nRedirect URL: ").strip()
    return fetch_account(get_token(parse_code(redirect_url)))


def main() -> None:
    cache_dir = Path("./cache")
    cache_dir.mkdir(exist_ok=True)
    psn_account_file = Path(cache_dir, "psn_account.json")

    try:
        psn_account = login()
    except (EOFError, ValueError, requests.RequestException) as e:
        print(f"Unable to retrieve login information: {e}")
        sys.exit(1)

    psn_account_file.write_text(json.dumps(asdict(psn_account), indent=2), encoding="utf-8")
    print(f"PSN Account '{psn_account.online_id}'. Wrote {psn_account_file}")


if __name__ == "__main__":
    main()
