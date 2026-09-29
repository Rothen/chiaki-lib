"""Pairs with a PS4/PS5 over the local network and writes
cache/host_registration.json, which the 1.4.x streaming examples can use directly.

Usage:
    python examples/1.3_register_console.py <host> <pin> [--ps4] [--console-pin PIN]

Needs the PSN account saved by 1.1_login.py. `pin` is the 8-digit code shown on
the console's Link Device screen (PS5: Settings > System > Remote Play > Link
Device; PS4: Settings > Remote Play Connection Settings > Add Device).
"""

import argparse
import json
import sys
from pathlib import Path

from chiaki_lib import Backend, Target


def main(host: str, pin: str, ps4: bool = False, console_pin: str = "") -> None:
    cache_dir = Path("./cache")
    psn_account_file = Path(cache_dir, "psn_account.json")
    registration_file = Path(cache_dir, "host_registration.json")

    if not psn_account_file.exists():
        print(f"PSN Account not found under {psn_account_file}. Run examples/1.1_login.py first")
        sys.exit(1)

    psn_account = json.loads(psn_account_file.read_text(encoding="utf-8"))

    target = Target.PS4_8 if ps4 else Target.PS5_1
    try:
        result = Backend().register_host(
            host=host,
            psn_id=psn_account["user_rpid"],
            pin=pin,
            cpin=console_pin,
            broadcast=False,
            target=target,
        )
    except RuntimeError as e:
        print(f"Registration failed: {e}")
        sys.exit(1)

    registration = {
        "host": host,
        "target": target.name,
        "regist_key": result.rp_regist_key,
        "nickname": result.server_nickname,
        "morning": result.rp_key.hex(),
        "initial_login_pin": "",
        "duid": "",
        "auto_regist": False,
        "fullscreen": False,
        "zoom": False,
        "stretch": False,
        "ps5": not ps4,
        "discover_timeout": 2.0,
    }
    registration_file.write_text(json.dumps(registration, indent=2), encoding="utf-8")
    print(f"Registered '{result.server_nickname}'. Wrote {registration_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pair with a PS4/PS5 over the local network.")
    parser.add_argument("host", help="IP address or hostname of the console.")
    parser.add_argument("pin", help="8-digit code from the console's Link Device screen.")
    parser.add_argument("--ps4", action="store_true", help="Register a PS4 instead of a PS5.")
    parser.add_argument("--console-pin", default="", help="Console PIN, if one is set.")
    args = parser.parse_args()
    main(host=args.host, pin=args.pin, ps4=args.ps4, console_pin=args.console_pin)
