#!/usr/bin/env python3
"""Create and inspect the persistent Social Media Agent configuration.

The OpenClaw image is one-click deployable, so configuration is collected in
the owner conversation and written to the persistent /var/lib/plow volume.
Only non-secret brand preferences live here; credentials remain in Latch.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
from typing import Any

import social_monitor


class ConfigInputError(ValueError):
    pass


def default_path() -> pathlib.Path:
    value = os.environ.get("SOCIAL_MEDIA_CONFIG")
    if value:
        return pathlib.Path(value).expanduser()
    home = pathlib.Path(os.environ.get("SOCIAL_HOME", "/var/lib/plow/social-media"))
    return home / "social-media.toml"


def _text(data: dict[str, Any], key: str, *, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigInputError(f"{key} must be a non-empty string")
    return value.strip()


def _strings(data: dict[str, Any], key: str, *, default: list[str]) -> list[str]:
    value = data.get(key, default)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ConfigInputError(f"{key} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _enabled(data: dict[str, Any], key: str, default: bool = True) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigInputError(f"{key} must be true or false")
    return value


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _array(values: list[str]) -> str:
    return "[" + ", ".join(_quoted(value) for value in values) + "]"


def render(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        raise ConfigInputError("configuration input must be a JSON object")
    company = _text(data, "company_name")
    aliases = _strings(data, "aliases", default=[])
    persona = _text(
        data,
        "persona_description",
        default="Professional, human, concise, and lightly humorous when appropriate.",
    )
    languages = _strings(data, "languages", default=["en"])
    if not languages:
        raise ConfigInputError("languages must contain at least one language")
    forbidden = _strings(
        data,
        "forbidden_topics",
        default=[
            "price or delivery promises",
            "personal data",
            "political positions without authorization",
            "legal or financial advice",
        ],
    )
    x_enabled = _enabled(data, "x_enabled")
    linkedin_enabled = _enabled(data, "linkedin_enabled")
    if not x_enabled and not linkedin_enabled:
        raise ConfigInputError("at least one platform must be enabled")
    x_terms = _strings(data, "x_search_terms", default=[])
    linkedin_terms = _strings(data, "linkedin_search_terms", default=[])
    return f'''schema_version = 1

[company]
name = {_quoted(company)}
aliases = {_array(aliases)}

[monitor]
max_items_per_platform = 10
max_browser_actions_per_platform = 20

[browser]
reuse_authenticated_session = true
keep_session_open_minutes = 120

[publishing]
x_min_interval_seconds = 60
linkedin_min_interval_seconds = 45
x_max_publications_per_24h = 25
linkedin_max_publications_per_24h = 25
x_error_344_backoff_seconds = [12]
post_fill_settle_seconds = 2

[platforms.x]
enabled = {str(x_enabled).lower()}
notifications_url = "https://x.com/notifications"
search_terms = {_array(x_terms)}

[platforms.linkedin]
enabled = {str(linkedin_enabled).lower()}
notifications_url = "https://www.linkedin.com/notifications/"
search_terms = {_array(linkedin_terms)}

[persona]
description = {_quoted(persona)}
languages = {_array(languages)}
use_emojis = "sparingly"
forbidden_topics = {_array(forbidden)}

[safety]
auto_publish = false
require_approval = true
escalate_complaints = true
escalate_crisis = true
'''


def write_atomic(path: pathlib.Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise ConfigInputError(
            f"configuration already exists at {path}; pass --force only after owner confirmation"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".social-media.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_json(source: str) -> dict[str, Any]:
    raw = sys.stdin.read() if source == "-" else pathlib.Path(source).read_text()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ConfigInputError("configuration input must be a JSON object")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="social-config")
    result.add_argument("--config", type=pathlib.Path, default=None)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--json", required=True)
    init.add_argument("--force", action="store_true")
    commands.add_parser("status")
    commands.add_parser("show")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    path = args.config or default_path()
    try:
        if args.command == "init":
            content = render(read_json(args.json))
            # Validate the exact serialized file before atomically replacing state.
            with tempfile.TemporaryDirectory() as folder:
                candidate = pathlib.Path(folder) / "social-media.toml"
                candidate.write_text(content)
                social_monitor.load_config(candidate)
            write_atomic(path, content, force=args.force)
            print(json.dumps({"ok": True, "configured": True, "path": str(path)}))
        elif args.command == "status":
            try:
                config = social_monitor.load_config(path)
                print(json.dumps({
                    "configured": True,
                    "path": str(path),
                    "company": config["company"]["name"],
                }, ensure_ascii=False))
            except (social_monitor.ConfigError, OSError) as exc:
                print(json.dumps({
                    "configured": False,
                    "path": str(path),
                    "reason": str(exc),
                }))
        elif args.command == "show":
            config = social_monitor.load_config(path)
            print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
    except (ConfigInputError, social_monitor.ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"social-config: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
