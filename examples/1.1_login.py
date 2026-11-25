"""Logs in to a PSN account in the terminal and saves it, with its OAuth tokens, to
cache/psn_account.json. 1.3_register_console.py needs the account to pair with a console;
1.3_auto_register_console.py also needs the tokens to register without a PIN.

Usage:
    python examples/1.1_login.py

Prints the PSN login URL; open it in a browser, sign in, then paste the URL the
browser ends up on back into the terminal.
"""

from __future__ import annotations

import sys

import requests

from psn_auth import (
    PSN_ACCOUNT_FILE,
    PSNAccount,
    REDIRECT_URL,
    fetch_account,
    get_tokens,
    login_url,
    missing_scopes,
    parse_code,
    save_account,
)


def login() -> PSNAccount:
    """Print the login URL, read the redirect URL back and exchange it for the account and its tokens."""
    print("Open this URL in a browser and sign in to your PlayStation account:\n")
    print(login_url())
    print(
        "\nAfter signing in you land on a page that starts with "
        f"{REDIRECT_URL}\nCopy the full URL from the browser's address bar and paste it here."
    )
    redirect_url = input("\nRedirect URL: ").strip()
    tokens = get_tokens(parse_code(redirect_url))
    account = fetch_account(tokens.access_token)
    account.tokens = tokens
    return account


def main() -> None:
    try:
        psn_account = login()
    except (EOFError, ValueError, requests.RequestException) as e:
        print(f"Unable to retrieve login information: {e}")
        sys.exit(1)

    save_account(psn_account)
    print(f"PSN Account '{psn_account.online_id}'. Wrote {PSN_ACCOUNT_FILE}")
    if missing := missing_scopes(psn_account):
        print(
            f"Warning: the login did not grant {', '.join(missing)}, so 1.3_auto_register_console.py won't work. "
            "Was the login URL opened in full? Copy all of it into the browser's address bar."
        )


if __name__ == "__main__":
    main()
