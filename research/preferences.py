"""Terminal settings controls through the journal's authenticated, validated API."""

import argparse
import http.cookiejar
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure")
    configure.add_argument("file", help="JSON settings file, or - for stdin")
    commands.add_parser("show")
    commands.add_parser("generate")
    schedule = commands.add_parser("schedule")
    schedule.add_argument("time", help="HH:MM in Europe/London, or off")
    args = parser.parse_args()
    payload = None
    if args.command == "configure":
        payload = json.loads(sys.stdin.read() if args.file == "-" else Path(args.file).read_text())
        required = {
            "prompt",
            "topics",
            "sources",
            "exclude",
            "maximum_items",
            "lookback_days",
            "schedule",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("Use the exact fields in research/settings.example.json.")
    if (
        args.command == "schedule"
        and args.time != "off"
        and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", args.time)
    ):
        raise ValueError("Use HH:MM in Europe/London, or off.")
    root = Path(os.environ.get("HERMES_HOME", "/opt/data")) / "research"
    token = (root / "journal/admin-token").read_text().strip()
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(route, body=None):
        # Internal Compose service; Host matches the journal's explicit local allowlist.
        req = Request(
            "http://journal:8097/api/" + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Host": "localhost:8097", "Content-Type": "application/json"},
        )
        with opener.open(req, timeout=20) as response:
            return json.load(response)

    request("login", {"token": token})
    try:
        if args.command == "configure":
            request("settings", payload)
            print("Settings saved. No research was started.")
        elif args.command == "show":
            print(json.dumps(request("settings"), indent=2))
        elif args.command == "generate":
            request("generate", {})
            print(
                "Research queued. Read the result in your journal; generation may take several minutes."
            )
        else:
            current = request("settings")
            current["schedule"]["enabled"] = args.time != "off"
            if args.time != "off":
                current["schedule"]["time"] = args.time
            request("settings", current)
            print("Schedule saved (Europe/London).")
    finally:
        request("logout", {})


if __name__ == "__main__":
    try:
        main()
    except HTTPError as exc:
        print(
            f"Journal refused the request (HTTP {exc.code}). Check settings, worker readiness, or an existing run.",
            file=sys.stderr,
        )
        sys.exit(1)
    except (OSError, ValueError, URLError):
        print(
            "Could not apply settings. Check the JSON file and that both services are running.",
            file=sys.stderr,
        )
        sys.exit(1)
