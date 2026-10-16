#!/usr/bin/env python3
"""Two small jobs for slack-catchup that a model gets wrong when it does them by hand.

  since      turn "yesterday", "last-workday", "3d", "monday" or a date into the Slack
             `oldest` timestamp and the `after:` date a search needs
  permalink  build a Slack message link from a workspace, a channel ID and a message ts

Usage:
    slack_helpers.py since last-workday [--tz America/New_York]
    slack_helpers.py permalink --workspace acme --channel C0123456789 --ts 1760000000.000200
    slack_helpers.py permalink --workspace acme --batch < messages.json

`since` accepts: Nh, Nd (a rolling window back from now), today, yesterday, last-workday,
a weekday name (the most recent one before today), YYYY-MM-DD, or YYYY-MM-DDTHH:MM.
Date-only forms start at 00:00 in the chosen time zone.

Exit codes: 0 ok, 2 unusable input (the message names the input and the fix).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# datetime.weekday() of today (Monday is 0) -> days back to the last workday
FRIDAY_OFFSET = {5: 1, 6: 2, 0: 3}
TS_PATTERN = re.compile(r"^\d{10}\.\d{6}$")
# Slack IDs for channels (C), private channels (G) and DMs (D) are an uppercase letter plus
# at least eight uppercase letters or digits.
CHANNEL_PATTERN = re.compile(r"^[CGD][A-Z0-9]{8,}$")
HOST_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class InputError(ValueError):
    """The caller passed something this script cannot use."""


def zone(name: str | None) -> tzinfo:
    if name is None:
        local = datetime.now().astimezone().tzinfo
        assert local is not None
        return local
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as err:
        raise InputError(
            f"unknown time zone '{name}'. Use an IANA name such as America/New_York."
        ) from err


def midnight(day: datetime) -> datetime:
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_since(spec: str, now: datetime) -> datetime:
    """Return the start of the window described by `spec`, in now's time zone."""
    text = spec.strip().lower()
    rolling = re.fullmatch(r"(\d+)\s*([hd])", text)
    if rolling:
        amount, unit = int(rolling.group(1)), rolling.group(2)
        return now - (timedelta(hours=amount) if unit == "h" else timedelta(days=amount))
    if text == "today":
        return midnight(now)
    if text == "yesterday":
        return midnight(now) - timedelta(days=1)
    if text == "last-workday":
        back = FRIDAY_OFFSET.get(now.weekday(), 1)
        return midnight(now) - timedelta(days=back)
    if text in WEEKDAYS:
        back = (now.weekday() - WEEKDAYS.index(text)) % 7 or 7
        return midnight(now) - timedelta(days=back)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(spec.strip(), fmt).replace(tzinfo=now.tzinfo)
        except ValueError:
            continue
    raise InputError(
        f"cannot read '{spec}' as a start time. Use Nh, Nd, today, yesterday, last-workday, "
        "a weekday name, YYYY-MM-DD or YYYY-MM-DDTHH:MM."
    )


def since_report(spec: str, now: datetime) -> dict[str, str]:
    start = resolve_since(spec, now)
    if start > now:
        raise InputError(f"'{spec}' resolves to {start.isoformat()}, which is in the future.")
    return {
        "spec": spec,
        "oldest": f"{start.timestamp():.6f}",
        "oldest_iso": start.isoformat(timespec="minutes"),
        # Slack's `after:` is date-granular and exclusive, so step back a day and filter the
        # results by `oldest` afterward.
        "search_after": (start.date() - timedelta(days=1)).isoformat(),
        "tz": str(now.tzinfo),
    }


def workspace_host(workspace: str) -> str:
    """Accept `acme`, `acme.slack.com` or a full Slack URL; return `acme.slack.com`."""
    text = workspace.strip().lower()
    text = re.sub(r"^https?://", "", text).split("/")[0]
    text = text.removesuffix(".slack.com")
    if not HOST_PATTERN.match(text):
        raise InputError(
            f"cannot read workspace '{workspace}'. Pass the subdomain (acme) or a URL like "
            "https://acme.slack.com."
        )
    return f"{text}.slack.com"


def permalink(workspace: str, channel: str, ts: str, thread_ts: str | None = None) -> str:
    if not CHANNEL_PATTERN.match(channel):
        raise InputError(f"'{channel}' is not a channel ID (it looks like C0123456789).")
    for label, value in (("ts", ts), ("thread_ts", thread_ts)):
        if value is not None and not TS_PATTERN.match(value):
            raise InputError(f"{label} '{value}' must look like 1760000000.000200.")
    base = f"https://{workspace_host(workspace)}/archives/{channel}/p{ts.replace('.', '')}"
    if thread_ts and thread_ts != ts:
        return f"{base}?thread_ts={thread_ts}&cid={channel}"
    return base


def run_permalink(args: argparse.Namespace) -> int:
    if args.batch:
        try:
            items = json.load(sys.stdin)
        except json.JSONDecodeError as err:
            raise InputError(
                f"stdin is not JSON ({err}). Pass a list of {{channel, ts, thread_ts?}}."
            ) from err
        if not isinstance(items, list):
            raise InputError("stdin JSON must be a list of {channel, ts, thread_ts?} objects.")
        links = [
            {
                **item,
                "url": permalink(
                    args.workspace, item["channel"], item["ts"], item.get("thread_ts")
                ),
            }
            for item in items
        ]
        print(json.dumps(links, indent=2))
        return 0
    if not args.channel or not args.ts:
        raise InputError("pass --channel and --ts, or --batch with a JSON list on stdin.")
    print(permalink(args.workspace, args.channel, args.ts, args.thread_ts))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = parser.add_subparsers(dest="command", required=True)

    since = sub.add_parser("since", help="resolve a start time")
    since.add_argument("spec")
    since.add_argument("--tz", help="IANA zone; default is this machine's zone")
    since.add_argument("--now", help="override the current time (YYYY-MM-DDTHH:MM) for tests")

    link = sub.add_parser("permalink", help="build a message link")
    link.add_argument("--workspace", required=True)
    link.add_argument("--channel")
    link.add_argument("--ts")
    link.add_argument("--thread-ts", dest="thread_ts")
    link.add_argument("--batch", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "since":
            tz = zone(args.tz)
            if args.now:
                try:
                    now = datetime.strptime(args.now, "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
                except ValueError as err:
                    raise InputError("--now must look like 2026-10-14T09:30.") from err
            else:
                now = datetime.now(tz)
            print(json.dumps(since_report(args.spec, now), indent=2))
            return 0
        return run_permalink(args)
    except (InputError, KeyError) as err:
        message = f"missing field {err} in a batch item" if isinstance(err, KeyError) else err
        print(f"slack_helpers.py: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
