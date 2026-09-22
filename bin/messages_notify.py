#!/usr/bin/env python3
"""Send one review notification through macOS Messages via Plow/Latch."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import plow_relay

APPLESCRIPT = r'''
on run argv
  set targetHandle to item 1 of argv
  set messageBody to item 2 of argv
  tell application "Messages"
    set targetService to first service whose service type = iMessage
    set targetBuddy to buddy targetHandle of targetService
    send messageBody to targetBuddy
  end tell
end run
'''.strip()


class NotificationError(ValueError):
    pass


def read_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NotificationError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise NotificationError("payload must be a JSON object")
    return payload


def required(payload: dict[str, Any], key: str, limit: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NotificationError(f"{key} is required")
    value = value.strip()
    if len(value) > limit:
        raise NotificationError(f"{key} exceeds {limit} characters")
    return value


def render(payload: dict[str, Any]) -> str:
    draft_id = required(payload, "draft_id", 30)
    platform = required(payload, "platform", 30).lower()
    if platform not in {"x", "linkedin"}:
        raise NotificationError("platform must be x or linkedin")
    url = required(payload, "url", 2_000)
    parsed = urllib.parse.urlparse(url)
    allowed = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"} if platform == "x" \
        else {"linkedin.com", "www.linkedin.com"}
    if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed
            or parsed.username or parsed.password):
        raise NotificationError("url does not match platform")
    author = required(payload, "author", 120)
    category = required(payload, "category", 100)
    reply = required(payload, "suggested_reply", 700)
    display_url = url[:600]
    body = (
        f"Social Media Agent · {draft_id}\n"
        f"{platform.upper()} · {category} · {author}\n\n"
        f"Suggested reply:\n{reply}\n\n"
        f"Open: {display_url}\n"
        f"To decide, reply to the agent: APPROVE {draft_id}, "
        f"EDIT {draft_id}: <text>, or IGNORE {draft_id}."
    )
    if len(body) > 1_800:
        raise NotificationError("rendered notification exceeds Messages limit")
    return body


def send(recipient: str, body: str) -> None:
    code, output = plow_relay.run(
        ["osascript", "-e", APPLESCRIPT, recipient, body],
        timeout=90,
        goal="social-media-agent: send review notification with Messages",
    )
    if code:
        raise plow_relay.RelayError(f"Messages returned exit code {code}: {output.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="messages-notify")
    parser.add_argument("--json", default="-", metavar="PATH")
    args = parser.parse_args(argv)
    try:
        recipient = os.environ.get("SOCIAL_MESSAGES_RECIPIENT", "").strip()
        if not recipient:
            raise NotificationError("SOCIAL_MESSAGES_RECIPIENT is not configured")
        body = render(read_payload(args.json))
        send(recipient, body)
        print("Notification sent through Messages")
        return 0
    except (NotificationError, OSError, plow_relay.RelayError) as exc:
        print(f"messages-notify: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
