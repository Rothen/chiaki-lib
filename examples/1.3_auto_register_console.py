"""Registers with a PS5 or PS4 through PSN, without the PIN from its Link Device screen (chiaki-ng's
"automatic registration"), and writes cache/host_registration.json like 1.3_register_console.py does.

Usage:
    python examples/1.3_auto_register_console.py [name] [--ps4] [--timeout SECONDS] [--verbose]

Needs the PSN account and tokens saved by 1.1_login.py (log in again if you did before it saved
tokens). Picks the PS5 called `name` among those linked to the account, or the only one there is;
lists them otherwise. With --ps4 it registers the account's primary PS4 instead, the only PS4 PSN
can reach.

The console must be signed in to the account, have Remote Play enabled, and be on or in rest mode
with "Stay connected to the internet" on. It need not be on the same network: everything goes
through PSN. The streaming examples then connect to it over the local network as usual.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

import requests

from chiaki_lib import Backend, ChiakiPySession, ChiakiPySessionConnectInfo, QuitReason, Settings, Target, quit_reason_string
from psn_auth import PSN_ACCOUNT_FILE, fresh_access_token, load_account, missing_scopes

REGISTRATION_FILE = Path("./cache", "host_registration.json")


def pick_ps5(access_token: str, name: str | None) -> tuple[str, str]:
    """The duid and name of the account's PS5 called `name`, or of its only one. Exits otherwise."""
    devices = [d for d in Backend.list_psn_devices(access_token) if d.remoteplay_enabled]
    matches = [d for d in devices if name is None or d.name == name]
    if len(matches) == 1:
        return matches[0].duid, matches[0].name
    if not devices:
        print("No PS5 with Remote Play enabled is linked to this PSN account.")
    else:
        reason = f"No PS5 called '{name}'." if name else "Several PS5s, pick one by name."
        print(f"{reason} The account's PS5s:")
        for device in devices:
            print(f"  {device.name}")
    sys.exit(1)


def auto_register(settings: Settings, duid: str, ps5: bool, timeout: float) -> dict[str, Any]:
    """Register with the console `duid` through a PSN session and return what it handed out."""
    connect_info = ChiakiPySessionConnectInfo(
        settings=settings,
        target=Target.PS5_1 if ps5 else Target.PS4_10,
        host="",
        nickname="",
        regist_key="",
        morning="",
        initial_login_pin="",
        duid=duid,
        auto_regist=True,
        fullscreen=False,
        zoom=False,
        stretch=False,
    )
    session = ChiakiPySession(connect_info)

    done = threading.Event()
    registered: dict[str, Any] = {}
    quit_reasons: list[QuitReason] = []
    errors: list[BaseException] = []

    # Both run on chiaki's session thread: hand everything, failures included, over to this one.
    def on_registered(host) -> None:
        try:
            # Copy everything out right away: the event only lives as long as this call.
            registered.update(
                target=host.target.name,
                nickname=host.server_nickname,
                regist_key=host.rp_regist_key,
                morning=host.rp_key,
                mac=host.server_mac,
            )
        except BaseException as e:
            errors.append(e)
        finally:
            done.set()

    def on_quit(reason: QuitReason) -> None:
        quit_reasons.append(reason)
        done.set()

    subscriptions = [
        session.on_auto_regist_succeeded().subscribe(on_registered),
        session.on_session_quit().subscribe(on_quit),
    ]
    try:
        print("Connecting to the console through PSN...")
        session.connect_psn_connection(duid, ps5)
        print("Registering...")
        session.start()
        if not done.wait(timeout):
            raise TimeoutError(f"The console did not answer within {timeout:.0f} seconds")
        if errors:
            raise RuntimeError(f"The console registered, but reading its registration failed: {errors[0]!r}")
        if not registered:
            raise ConnectionError(f"Registration failed: {quit_reason_string(quit_reasons[0])}")
        return registered
    finally:
        for subscription in subscriptions:
            subscription.unsubscribe()
        session.stop()


def main(name: str | None, ps4: bool, timeout: float) -> None:
    try:
        account = load_account()
        if missing := missing_scopes(account):
            print(f"The saved PSN login lacks {', '.join(missing)}. Run examples/1.1_login.py again")
            sys.exit(1)
        access_token = fresh_access_token(account)
    except FileNotFoundError:
        print(f"PSN Account not found under {PSN_ACCOUNT_FILE}. Run examples/1.1_login.py first")
        sys.exit(1)
    except (ValueError, requests.RequestException) as e:
        print(f"No usable PSN tokens ({e}). Run examples/1.1_login.py again")
        sys.exit(1)

    if ps4:
        duid, device_name = Backend.psn_main_ps4_duid(), name
    else:
        try:
            duid, device_name = pick_ps5(access_token, name)
        except RuntimeError as e:
            print(e)
            sys.exit(1)

    settings = Settings()
    settings.set_psn_auth_token(access_token)
    settings.set_psn_account_id(account.user_rpid)
    try:
        result = auto_register(settings, duid, ps5=not ps4, timeout=timeout)
    except (RuntimeError, ConnectionError, TimeoutError) as e:
        print(e)
        sys.exit(1)

    # PSN always reaches the account's primary PS4, which need not be the one meant.
    if ps4 and device_name and result["nickname"] != device_name:
        print(f"Registered '{result['nickname']}', the account's primary PS4, not '{device_name}'. Nothing written.")
        sys.exit(1)

    registration = {
        # The streaming examples find the console's address on the local network by its nickname.
        "host": "",
        "target": result["target"],
        "regist_key": result["regist_key"],
        "nickname": result["nickname"],
        "morning": result["morning"],
        "initial_login_pin": "",
        # Empty: the streaming examples connect over the local network. A PSN session takes `psn_duid`.
        "duid": "",
        "psn_duid": duid,
        "auto_regist": False,
        "fullscreen": False,
        "zoom": False,
        "stretch": False,
        "ps5": not ps4,
        "discover_timeout": 2.0,
    }
    REGISTRATION_FILE.parent.mkdir(exist_ok=True)
    REGISTRATION_FILE.write_text(json.dumps(registration, indent=2), encoding="utf-8")
    print(f"Registered '{result['nickname']}' ({result['mac']}). Wrote {REGISTRATION_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register with a PS5/PS4 through PSN, without a PIN.")
    parser.add_argument("name", nargs="?", help="The console's name; optional if the account has one PS5.")
    parser.add_argument("--ps4", action="store_true", help="Register the account's primary PS4 instead of a PS5.")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for the console once connected.")
    parser.add_argument("--verbose", action="store_true", help="Show chiaki's log of the PSN connection and registration.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(name)s %(levelname)s: %(message)s")
    main(name=args.name, ps4=args.ps4, timeout=args.timeout)
