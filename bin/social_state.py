#!/usr/bin/env python3
"""Durable state and approval ledger for the Social Media Agent.

Standard-library only. The CLI is intentionally small so both scheduled agent
turns and operators can use the same state transitions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import re
import sqlite3
import sys
import tomllib
import urllib.parse
from typing import Any

PLATFORMS = {"x", "linkedin"}
STATUSES = {"new", "drafted", "notified", "approved", "published", "ignored", "error"}
TERMINAL_STATUSES = {"published", "ignored"}
TRANSITIONS = {
    "new": {"drafted", "ignored", "error"},
    "drafted": {"notified", "approved", "ignored", "error"},
    "notified": {"approved", "ignored", "error"},
    "approved": {"published", "error"},
    "error": {"new", "drafted", "notified", "approved", "ignored"},
    "published": set(),
    "ignored": set(),
}
SCHEMA_VERSION = 3
DIRECT_MESSAGE_TYPES = {"dm", "direct_message", "direct-message", "message", "inbound_message"}
PUBLISH_ATTEMPT_OUTCOMES = {"rate_limited", "failed", "uncertain"}
MAX_DRAFT_LENGTHS = {"x": 280, "linkedin": 700}
DEFAULT_PUBLISHING_POLICY = {
    "x": {
        "min_interval_seconds": 60,
        "max_publications_per_24h": 25,
        "error_344_backoff_seconds": [12],
    },
    "linkedin": {
        "min_interval_seconds": 45,
        "max_publications_per_24h": 25,
        "error_344_backoff_seconds": [],
    },
}


class StateError(ValueError):
    pass


def _ensure_column(
    db: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Add one backward-compatible column to an existing ledger."""
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def default_db_path() -> pathlib.Path:
    if value := os.environ.get("SOCIAL_STATE_DB"):
        return pathlib.Path(value).expanduser()
    home = pathlib.Path(os.environ.get("HERMES_HOME", pathlib.Path.home() / ".hermes"))
    return home / "state" / "social-media.sqlite3"


def default_config_path() -> pathlib.Path:
    if value := os.environ.get("SOCIAL_MEDIA_CONFIG"):
        return pathlib.Path(value).expanduser()
    home = pathlib.Path(os.environ.get("HERMES_HOME", pathlib.Path.home() / ".hermes"))
    return home / "social-media.toml"


def connect(path: pathlib.Path | None = None) -> sqlite3.Connection:
    path = path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS interactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL CHECK(platform IN ('x','linkedin')),
          external_id TEXT NOT NULL,
          url TEXT NOT NULL,
          author TEXT NOT NULL,
          content TEXT NOT NULL,
          interaction_type TEXT NOT NULL,
          sentiment TEXT NOT NULL DEFAULT 'unknown',
          priority TEXT NOT NULL DEFAULT 'normal',
          detected_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'new',
          drafts_json TEXT,
          recommended_index INTEGER,
          rationale TEXT,
          risk TEXT,
          notified_at TEXT,
          approved_at TEXT,
          approval_cycle INTEGER NOT NULL DEFAULT 0,
          published_at TEXT,
          published_text TEXT,
          published_url TEXT,
          published_parent_external_id TEXT,
          error TEXT,
          UNIQUE(platform, external_id)
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          interaction_id INTEGER NOT NULL REFERENCES interactions(id),
          event_type TEXT NOT NULL,
          detail TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS platform_state (
          platform TEXT PRIMARY KEY CHECK(platform IN ('x','linkedin')),
          last_processed_id TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS publication_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          interaction_id INTEGER NOT NULL REFERENCES interactions(id),
          platform TEXT NOT NULL CHECK(platform IN ('x','linkedin')),
          approval_cycle INTEGER NOT NULL DEFAULT 0,
          outcome TEXT NOT NULL CHECK(outcome IN ('success','rate_limited','failed','uncertain')),
          error_code TEXT,
          detail TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS interactions_status_idx
          ON interactions(status, priority, detected_at);
        CREATE INDEX IF NOT EXISTS publication_attempts_platform_idx
          ON publication_attempts(platform, created_at);
        CREATE INDEX IF NOT EXISTS publication_attempts_interaction_idx
          ON publication_attempts(interaction_id, created_at);
        """
    )
    _ensure_column(db, "interactions", "approval_cycle", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "interactions", "published_url", "TEXT")
    _ensure_column(db, "interactions", "published_parent_external_id", "TEXT")
    _ensure_column(db, "publication_attempts", "approval_cycle", "INTEGER NOT NULL DEFAULT 0")
    db.execute(
        "INSERT INTO metadata(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    db.commit()
    return db


def _clean_text(value: Any, field: str, *, max_len: int = 20_000) -> str:
    if not isinstance(value, str):
        raise StateError(f"{field} must be a string")
    value = value.strip()
    if not value:
        raise StateError(f"{field} must not be empty")
    if len(value) > max_len:
        raise StateError(f"{field} exceeds {max_len} characters")
    return value


def _clean_detail(value: Any, field: str = "detail") -> str:
    text = _clean_text(value, field, max_len=2_000)
    text = re.sub(r"\bplow_[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = re.sub(
        r"(?i)\b(password|token|totp|verification[_ -]?code)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    return text


def _validate_url(platform: str, value: Any) -> str:
    url = _clean_text(value, "url", max_len=4_000)
    parsed = urllib.parse.urlparse(url)
    allowed = {"x": {"x.com", "www.x.com", "twitter.com", "www.twitter.com"},
               "linkedin": {"linkedin.com", "www.linkedin.com"}}
    if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed[platform]
            or parsed.username or parsed.password):
        raise StateError(f"url must be an HTTPS {platform} URL")
    return url


def _is_direct_message(interaction_type: str) -> bool:
    return interaction_type.strip().lower() in DIRECT_MESSAGE_TYPES


def _x_status_id(url: str) -> str | None:
    """Extract the status ID from a canonical X/Twitter URL."""
    parts = [urllib.parse.unquote(part) for part in urllib.parse.urlparse(url).path.split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == "status" and re.fullmatch(r"[0-9]+", parts[index + 1]):
            return parts[index + 1]
    return None


def _x_url_handle(url: str) -> str | None:
    parts = [urllib.parse.unquote(part) for part in urllib.parse.urlparse(url).path.split("/") if part]
    if len(parts) >= 3 and parts[1].casefold() == "status":
        return f"@{parts[0]}"
    return None


def normalize_interaction(data: dict[str, Any]) -> dict[str, str]:
    if not isinstance(data, dict):
        raise StateError("interaction must be a JSON object")
    platform = _clean_text(data.get("platform"), "platform", max_len=20).lower()
    if platform not in PLATFORMS:
        raise StateError("platform must be x or linkedin")
    external_id = _clean_text(data.get("external_id"), "external_id", max_len=500)
    author = _clean_text(data.get("author"), "author", max_len=500)
    interaction_type = _clean_text(
        data.get("interaction_type", "mention"), "interaction_type", max_len=100
    )
    url = _validate_url(platform, data.get("url"))
    if platform == "x" and not _is_direct_message(interaction_type):
        handle_match = re.search(r"@[A-Za-z0-9_]{1,30}", author)
        if not handle_match:
            raise StateError("public X interactions require an @handle in author")
        status_id = _x_status_id(url)
        if status_id is None:
            raise StateError("public X interactions require a canonical /status/<id> URL")
        if external_id != status_id:
            raise StateError("public X external_id must match the status ID in url")
        url_handle = _x_url_handle(url)
        if url_handle and url_handle.casefold() != handle_match.group(0).casefold():
            raise StateError("public X author handle must match the canonical status URL")
    return {
        "platform": platform,
        "external_id": external_id,
        "url": url,
        "author": author,
        "content": _clean_text(data.get("content"), "content"),
        "interaction_type": interaction_type,
        "sentiment": _clean_text(data.get("sentiment", "unknown"), "sentiment", max_len=50),
        "priority": _clean_text(data.get("priority", "normal"), "priority", max_len=50),
        "detected_at": _clean_text(data.get("detected_at", utcnow()), "detected_at", max_len=100),
    }


def display_id(row_id: int) -> str:
    return f"SM-{row_id:06d}"


def parse_ref(ref: str | int) -> int:
    if isinstance(ref, int):
        return ref
    match = re.fullmatch(r"(?:SM-)?0*([1-9][0-9]*)", str(ref).strip(), re.I)
    if not match:
        raise StateError("interaction id must look like SM-000001")
    return int(match.group(1))


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["draft_id"] = display_id(result["id"])
    if result.get("drafts_json"):
        result["drafts"] = json.loads(result.pop("drafts_json"))
    else:
        result.pop("drafts_json", None)
        result["drafts"] = []
    result["required_mention"] = required_mention(
        result["platform"], result["author"], result["interaction_type"]
    )
    return result


def required_mention(platform: str, author: str, interaction_type: str) -> str | None:
    """Return the prefix every public reply must carry.

    Direct messages already identify the recipient through the conversation and
    must not be made awkward with an @-mention. Public X and LinkedIn replies do
    need one, both for clarity and to satisfy the owner's engagement policy.
    """
    if _is_direct_message(interaction_type):
        return None
    if platform == "x":
        match = re.search(r"@[A-Za-z0-9_]{1,30}", author)
        return match.group(0) if match else None
    name = author.strip()
    return name if name.startswith("@") else f"@{name}"


def _starts_with_mention(text: str, mention: str) -> bool:
    if not text.casefold().startswith(mention.casefold()):
        return False
    if len(text) == len(mention):
        return True
    return not (text[len(mention)].isalnum() or text[len(mention)] == "_")


def ingest(db: sqlite3.Connection, raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    data = normalize_interaction(raw)
    now = utcnow()
    before = db.execute(
        "SELECT id,status FROM interactions WHERE platform=? AND external_id=?",
        (data["platform"], data["external_id"]),
    ).fetchone()
    db.execute(
        """
        INSERT INTO interactions(
          platform, external_id, url, author, content, interaction_type,
          sentiment, priority, detected_at, last_seen_at
        ) VALUES(:platform,:external_id,:url,:author,:content,:interaction_type,
                 :sentiment,:priority,:detected_at,:last_seen_at)
        ON CONFLICT(platform,external_id) DO UPDATE SET
          url=CASE WHEN interactions.status='new' THEN excluded.url ELSE interactions.url END,
          author=CASE WHEN interactions.status='new' THEN excluded.author ELSE interactions.author END,
          content=CASE WHEN interactions.status='new' THEN excluded.content ELSE interactions.content END,
          interaction_type=CASE WHEN interactions.status='new' THEN excluded.interaction_type ELSE interactions.interaction_type END,
          sentiment=CASE WHEN interactions.status='new' THEN excluded.sentiment ELSE interactions.sentiment END,
          priority=CASE WHEN interactions.status='new' THEN excluded.priority ELSE interactions.priority END,
          detected_at=CASE WHEN interactions.status='new' THEN excluded.detected_at ELSE interactions.detected_at END,
          last_seen_at=excluded.last_seen_at
        """,
        {**data, "last_seen_at": now},
    )
    row = db.execute(
        "SELECT * FROM interactions WHERE platform=? AND external_id=?",
        (data["platform"], data["external_id"]),
    ).fetchone()
    assert row is not None
    if before is None:
        db.execute(
            "INSERT INTO events(interaction_id,event_type,detail,created_at) VALUES(?,?,?,?)",
            (row["id"], "ingested", None, now),
        )
    db.commit()
    return row_dict(row), before is None


def get(db: sqlite3.Connection, ref: str | int) -> dict[str, Any]:
    row = db.execute("SELECT * FROM interactions WHERE id=?", (parse_ref(ref),)).fetchone()
    if row is None:
        raise StateError(f"interaction {ref} not found")
    return row_dict(row)


def set_draft(db: sqlite3.Connection, ref: str, payload: dict[str, Any]) -> dict[str, Any]:
    drafts = payload.get("drafts")
    if not isinstance(drafts, list) or not 1 <= len(drafts) <= 3:
        raise StateError("drafts must contain between one and three strings")
    recommended = payload.get("recommended_index", 0)
    if not isinstance(recommended, int) or not 0 <= recommended < len(drafts):
        raise StateError("recommended_index is outside drafts")
    current = get(db, ref)
    if current["status"] in TERMINAL_STATUSES | {"approved"}:
        raise StateError(f"cannot draft an interaction in {current['status']} state")
    max_length = MAX_DRAFT_LENGTHS[current["platform"]]
    drafts = [_clean_text(item, "draft", max_len=max_length) for item in drafts]
    mention = current["required_mention"]
    if mention is not None:
        missing = [index + 1 for index, draft in enumerate(drafts)
                   if not _starts_with_mention(draft, mention)]
        if missing:
            numbers = ", ".join(str(index) for index in missing)
            raise StateError(
                f"public reply draft(s) {numbers} must start with mention {mention!r}"
            )
    now = utcnow()
    db.execute(
        """UPDATE interactions SET drafts_json=?, recommended_index=?, rationale=?,
           risk=?, status='drafted', error=NULL WHERE id=?""",
        (json.dumps(drafts, ensure_ascii=False), recommended,
         str(payload.get("rationale", ""))[:2_000], str(payload.get("risk", "normal"))[:100],
         current["id"]),
    )
    db.execute(
        "INSERT INTO events(interaction_id,event_type,detail,created_at) VALUES(?,?,?,?)",
        (current["id"], "drafted", f"{len(drafts)} option(s)", now),
    )
    db.commit()
    return get(db, current["id"])


def publication_target(current: dict[str, Any]) -> dict[str, Any]:
    """Return an exact, platform-specific target contract for browser publication."""
    base = {
        "external_id": current["external_id"],
        "canonical_url": current["url"],
        "author": current["author"],
        "source_text": current["content"],
        "interaction_type": current["interaction_type"],
        "required_mention": current["required_mention"],
    }
    if current["platform"] == "x" and not _is_direct_message(current["interaction_type"]):
        status_id = _x_status_id(current["url"])
        if status_id is None or status_id != current["external_id"]:
            raise StateError("stored X target does not match its canonical status URL")
        return {
            **base,
            "locator": {
                "kind": "x_status_article",
                "status_id": status_id,
                "href_suffix": f"/status/{status_id}",
                "must_match_articles": 1,
            },
        }
    return {
        **base,
        "locator": {
            "kind": "conversation" if _is_direct_message(current["interaction_type"])
            else "linkedin_source",
            "external_id": current["external_id"],
        },
    }


def _validate_publication_receipt(
    current: dict[str, Any], published_url: str | None, parent_external_id: str | None
) -> tuple[str | None, str | None]:
    """Validate evidence that a public response is attached to the intended source."""
    if _is_direct_message(current["interaction_type"]):
        if published_url is None:
            return None, None
        return _validate_url(current["platform"], published_url), None

    result_url = _validate_url(current["platform"], published_url)
    parent_id = _clean_text(parent_external_id, "parent_external_id", max_len=500)
    if parent_id != current["external_id"]:
        raise StateError("published parent_external_id does not match the approved target")
    if current["platform"] == "x":
        reply_id = _x_status_id(result_url)
        if reply_id is None:
            raise StateError("published_url must be the direct URL of the X reply")
        if reply_id == current["external_id"]:
            raise StateError("published_url points to the source post, not the new X reply")
    return result_url, parent_id


def mark(db: sqlite3.Connection, ref: str, status: str, *, detail: str = "",
         published_text: str | None = None, published_url: str | None = None,
         parent_external_id: str | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise StateError(f"unknown status {status!r}")
    current = get(db, ref)
    old = current["status"]
    if status == old:
        raise StateError(f"interaction is already {status}")
    if status not in TRANSITIONS[old]:
        raise StateError(f"invalid transition {old} -> {status}")
    now = utcnow()
    fields: dict[str, Any] = {"status": status, "id": current["id"], "old_status": old}
    if status == "notified":
        fields["notified_at"] = now
    if status == "approved":
        fields["approved_at"] = now
        fields["approval_cycle"] = int(current.get("approval_cycle") or 0) + 1
        fields["error"] = None
    if status == "published":
        fields["published_at"] = now
        fields["published_text"] = _clean_text(
            published_text, "published_text", max_len=5_000
        )
        if not current["drafts"] or current["recommended_index"] is None:
            raise StateError("approved interaction has no stored recommended draft")
        expected = current["drafts"][current["recommended_index"]]
        if fields["published_text"] != expected:
            raise StateError("published_text must exactly match the approved stored draft")
        mention = current["required_mention"]
        if mention is not None and not _starts_with_mention(fields["published_text"], mention):
            raise StateError(f"published_text must start with mention {mention!r}")
        result_url, parent_id = _validate_publication_receipt(
            current, published_url, parent_external_id
        )
        fields["published_url"] = result_url
        fields["published_parent_external_id"] = parent_id
    if status == "error":
        fields["error"] = _clean_detail(detail)
    assignments = ", ".join(
        f"{key}=:{key}" for key in fields if key not in {"id", "old_status"}
    )
    changed = db.execute(
        f"UPDATE interactions SET {assignments} WHERE id=:id AND status=:old_status", fields
    )
    if changed.rowcount != 1:
        db.rollback()
        raise StateError("interaction state changed concurrently; reload before acting")
    event_detail = fields.get("error") if status == "error" else detail[:2_000] or None
    db.execute(
        "INSERT INTO events(interaction_id,event_type,detail,created_at) VALUES(?,?,?,?)",
        (current["id"], status, event_detail, now),
    )
    if status == "published":
        db.execute(
            """INSERT INTO publication_attempts(
                 interaction_id,platform,approval_cycle,outcome,error_code,detail,created_at
               ) VALUES(?,?,?, 'success',NULL,?,?)""",
            (current["id"], current["platform"], current["approval_cycle"],
             "visible result and parent target verified", now),
        )
    db.commit()
    return get(db, current["id"])


def record_publication_attempt(
    db: sqlite3.Connection,
    ref: str | int,
    outcome: str,
    *,
    error_code: str = "",
    detail: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Audit a submit attempt that did not produce a verified publication.

    Successful submissions are recorded atomically by ``mark(..., 'published')``.
    Keeping failures separate lets the agent perform a narrowly bounded X retry
    without changing the approval state or risking an untracked send. Only
    error 344 or a conclusively absent generic submission may authorize that
    single retry; ambiguous outcomes never do.
    """
    if outcome not in PUBLISH_ATTEMPT_OUTCOMES:
        raise StateError(
            "outcome must be one of: " + ", ".join(sorted(PUBLISH_ATTEMPT_OUTCOMES))
        )
    current = get(db, ref)
    if current["status"] != "approved":
        raise StateError("publication attempts may only be recorded for an approved interaction")
    code = str(error_code).strip()[:100] or None
    message = _clean_detail(detail) if str(detail).strip() else None
    when = created_at or utcnow()
    _as_utc(when)
    db.execute(
        """INSERT INTO publication_attempts(
             interaction_id,platform,approval_cycle,outcome,error_code,detail,created_at
           ) VALUES(?,?,?,?,?,?,?)""",
        (current["id"], current["platform"], current["approval_cycle"],
         outcome, code, message, when),
    )
    event_detail = json.dumps(
        {"outcome": outcome, "error_code": code, "detail": message}, ensure_ascii=False
    )
    db.execute(
        "INSERT INTO events(interaction_id,event_type,detail,created_at) VALUES(?,?,?,?)",
        (current["id"], "publication_attempt", event_detail, when),
    )
    db.commit()
    return {
        "ok": True,
        "draft_id": current["draft_id"],
        "platform": current["platform"],
        "approval_cycle": current["approval_cycle"],
        "outcome": outcome,
        "error_code": code,
        "created_at": when,
    }


def correct_publication(
    db: sqlite3.Connection, ref: str | int, *, detail: str
) -> dict[str, Any]:
    """Correct a false-positive publication without erasing its audit trail."""
    current = get(db, ref)
    if current["status"] != "published":
        raise StateError("only a published interaction can be corrected")
    message = _clean_detail(detail)
    now = utcnow()
    changed = db.execute(
        """UPDATE interactions SET status='error', error=?
           WHERE id=? AND status='published'""",
        (message, current["id"]),
    )
    if changed.rowcount != 1:
        db.rollback()
        raise StateError("interaction state changed concurrently; reload before acting")
    db.execute(
        "INSERT INTO events(interaction_id,event_type,detail,created_at) VALUES(?,?,?,?)",
        (current["id"], "publication_corrected", message, now),
    )
    db.commit()
    return get(db, current["id"])


def _as_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateError(f"invalid timestamp in publication ledger: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def publishing_policy(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    section = (config or {}).get("publishing", {})
    if not isinstance(section, dict):
        raise StateError("publishing must be a TOML table")
    policy = {name: dict(values) for name, values in DEFAULT_PUBLISHING_POLICY.items()}
    for platform in PLATFORMS:
        prefix = "x" if platform == "x" else "linkedin"
        for key, config_key, lower, upper in (
            ("min_interval_seconds", f"{prefix}_min_interval_seconds", 15, 3600),
            ("max_publications_per_24h", f"{prefix}_max_publications_per_24h", 1, 500),
        ):
            if config_key in section:
                value = section[config_key]
                if (isinstance(value, bool) or not isinstance(value, int)
                        or not lower <= value <= upper):
                    raise StateError(
                        f"publishing.{config_key} must be an integer between {lower} and {upper}"
                    )
                policy[platform][key] = value
    if "x_error_344_backoff_seconds" in section:
        values = section["x_error_344_backoff_seconds"]
        if (not isinstance(values, list) or not 1 <= len(values) <= 3
                or any(isinstance(value, bool) or not isinstance(value, int)
                       or not 1 <= value <= 120 for value in values)):
            raise StateError(
                "publishing.x_error_344_backoff_seconds must contain 1-3 integers from 1 to 120"
            )
        policy["x"]["error_344_backoff_seconds"] = values
    return policy


def load_publishing_policy(path: pathlib.Path | None = None) -> dict[str, dict[str, Any]]:
    config_path = path or default_config_path()
    try:
        config = tomllib.loads(config_path.read_text())
    except FileNotFoundError:
        return publishing_policy()
    except tomllib.TOMLDecodeError as exc:
        raise StateError(f"invalid publication configuration: {exc}") from exc
    return publishing_policy(config)


def publication_gate(
    db: sqlite3.Connection,
    ref: str | int,
    *,
    policy: dict[str, dict[str, Any]] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Return the next safe publication action for one approved draft.

    Normal publications are spaced from the last verified success. X permits
    one automatic retry after a conclusive 344 or conclusively absent generic
    failure. Unknown outcomes never become retryable automatically.
    """
    current = get(db, ref)
    if current["status"] != "approved":
        return {
            "allowed": False,
            "reason": "not_approved",
            "draft_id": current["draft_id"],
            "platform": current["platform"],
            "wait_seconds": 0,
        }
    rules = (policy or publishing_policy())[current["platform"]]
    moment = now or dt.datetime.now(dt.timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    moment = moment.astimezone(dt.timezone.utc)
    window_start = (moment - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    published_count = db.execute(
        """SELECT count(*) FROM publication_attempts
           WHERE platform=? AND outcome='success' AND created_at>=?""",
        (current["platform"], window_start),
    ).fetchone()[0]
    remaining = max(0, int(rules["max_publications_per_24h"]) - published_count)
    if not current["drafts"] or current["recommended_index"] is None:
        raise StateError("approved interaction has no stored recommended draft")
    base = {
        "draft_id": current["draft_id"],
        "platform": current["platform"],
        "approval_cycle": current["approval_cycle"],
        "approved_text": current["drafts"][current["recommended_index"]],
        "target": publication_target(current),
        "published_last_24h": published_count,
        "remaining_last_24h": remaining,
        "wait_seconds": 0,
    }
    if remaining == 0:
        return {**base, "allowed": False, "reason": "daily_limit"}

    last_success = db.execute(
        """SELECT created_at FROM publication_attempts
           WHERE platform=? AND outcome='success'
           ORDER BY created_at DESC LIMIT 1""",
        (current["platform"],),
    ).fetchone()
    interval_wait = 0
    if last_success:
        elapsed = max(0.0, (moment - _as_utc(last_success["created_at"])).total_seconds())
        interval_wait = max(0, math.ceil(int(rules["min_interval_seconds"]) - elapsed))

    attempts = db.execute(
        """SELECT outcome,error_code,created_at FROM publication_attempts
           WHERE interaction_id=? AND approval_cycle=? ORDER BY id""",
        (current["id"], current["approval_cycle"]),
    ).fetchall()
    if attempts:
        last = attempts[-1]
        if len(attempts) >= 2:
            return {**base, "allowed": False, "reason": "retry_exhausted"}
        retryable_x_failure = (
            current["platform"] == "x"
            and (
                (last["outcome"] == "rate_limited"
                 and str(last["error_code"] or "") == "344")
                or
                (last["outcome"] == "failed"
                 and str(last["error_code"] or "") == "X_CONCLUSIVE_ABSENCE")
            )
        )
        if not retryable_x_failure:
            return {**base, "allowed": False, "reason": "manual_review_required"}
        backoffs = list(rules.get("error_344_backoff_seconds", []))
        if not backoffs:
            return {**base, "allowed": False, "reason": "retry_exhausted"}
        # One initial submit plus one safe retry, even when an older config
        # still contains the pre-0.4.2 two-value 344 backoff list.
        backoff = backoffs[0]
        elapsed = max(0.0, (moment - _as_utc(last["created_at"])).total_seconds())
        retry_wait = max(0, math.ceil(backoff - elapsed))
        wait = max(retry_wait, interval_wait)
        return {
            **base,
            "allowed": wait == 0,
            "reason": "retry_ready" if wait == 0 else "retry_backoff",
            "wait_seconds": wait,
            "attempt_number": 2,
            "max_attempts": 2,
        }

    previous_failure = db.execute(
        """SELECT outcome,created_at FROM publication_attempts
           WHERE interaction_id=? AND approval_cycle<? AND outcome!='success'
           ORDER BY id DESC LIMIT 1""",
        (current["id"], current["approval_cycle"]),
    ).fetchone()
    if previous_failure:
        elapsed = max(
            0.0,
            (moment - _as_utc(previous_failure["created_at"])).total_seconds(),
        )
        retry_wait = max(0, math.ceil(int(rules["min_interval_seconds"]) - elapsed))
        if retry_wait:
            return {
                **base,
                "allowed": False,
                "reason": "owner_retry_cooldown",
                "wait_seconds": retry_wait,
                "attempt_number": 1,
            }

    if interval_wait:
        return {
            **base,
            "allowed": False,
            "reason": "minimum_interval",
            "wait_seconds": interval_wait,
            "attempt_number": 1,
        }
    return {**base, "allowed": True, "reason": "ready", "attempt_number": 1}


def pending(db: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        """SELECT * FROM interactions WHERE status NOT IN ('published','ignored')
           ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                    detected_at ASC LIMIT ?""",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [row_dict(row) for row in rows]


def history(db: sqlite3.Connection, ref: str | int) -> dict[str, Any]:
    """Return a secret-free incident timeline for one interaction."""
    current = get(db, ref)
    events = [dict(row) for row in db.execute(
        """SELECT event_type,detail,created_at FROM events
           WHERE interaction_id=? ORDER BY id""",
        (current["id"],),
    ).fetchall()]
    attempts = [dict(row) for row in db.execute(
        """SELECT approval_cycle,outcome,error_code,detail,created_at
           FROM publication_attempts WHERE interaction_id=? ORDER BY id""",
        (current["id"],),
    ).fetchall()]
    return {
        "draft_id": current["draft_id"],
        "platform": current["platform"],
        "external_id": current["external_id"],
        "status": current["status"],
        "approval_cycle": current["approval_cycle"],
        "published_url": current.get("published_url"),
        "published_parent_external_id": current.get("published_parent_external_id"),
        "error": current.get("error"),
        "events": events,
        "publication_attempts": attempts,
    }


def set_cursor(db: sqlite3.Connection, platform: str, external_id: str) -> None:
    if platform not in PLATFORMS:
        raise StateError("platform must be x or linkedin")
    external_id = _clean_text(external_id, "external_id", max_len=500)
    db.execute(
        """INSERT INTO platform_state(platform,last_processed_id,updated_at) VALUES(?,?,?)
           ON CONFLICT(platform) DO UPDATE SET
             last_processed_id=excluded.last_processed_id, updated_at=excluded.updated_at""",
        (platform, external_id, utcnow()),
    )
    db.commit()


def get_cursor(db: sqlite3.Connection, platform: str | None = None) -> dict[str, Any]:
    if platform is not None and platform not in PLATFORMS:
        raise StateError("platform must be x or linkedin")
    if platform is None:
        rows = db.execute(
            "SELECT platform,last_processed_id,updated_at FROM platform_state ORDER BY platform"
        ).fetchall()
        return {row["platform"]: dict(row) for row in rows}
    row = db.execute(
        "SELECT platform,last_processed_id,updated_at FROM platform_state WHERE platform=?",
        (platform,),
    ).fetchone()
    return {
        "platform": platform,
        "last_processed_id": row["last_processed_id"] if row else None,
        "updated_at": row["updated_at"] if row else None,
    }


def _read_json(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError("JSON input must be an object")
    return value


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="social-state")
    parser.add_argument("--db", type=pathlib.Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    item = commands.add_parser("ingest")
    item.add_argument("--json", default="-", metavar="PATH")
    item = commands.add_parser("show")
    item.add_argument("id")
    item = commands.add_parser("history")
    item.add_argument("id")
    item = commands.add_parser("pending")
    item.add_argument("--limit", type=int, default=50)
    item = commands.add_parser("set-draft")
    item.add_argument("id")
    item.add_argument("--json", default="-", metavar="PATH")
    item = commands.add_parser("mark")
    item.add_argument("id")
    item.add_argument("status", choices=sorted(STATUSES))
    item.add_argument("--detail", default="")
    item.add_argument("--published-text")
    item.add_argument("--published-url")
    item.add_argument("--parent-external-id")
    item = commands.add_parser("publication-gate")
    item.add_argument("id")
    item.add_argument("--config", type=pathlib.Path, default=None)
    item = commands.add_parser("record-attempt")
    item.add_argument("id")
    item.add_argument("outcome", choices=sorted(PUBLISH_ATTEMPT_OUTCOMES))
    item.add_argument("--error-code", default="")
    item.add_argument("--detail", default="")
    item = commands.add_parser("correct-publication")
    item.add_argument("id")
    item.add_argument("--detail", required=True)
    item = commands.add_parser("set-cursor")
    item.add_argument("platform", choices=sorted(PLATFORMS))
    item.add_argument("external_id")
    item = commands.add_parser("cursor")
    item.add_argument("platform", nargs="?", choices=sorted(PLATFORMS))
    commands.add_parser("summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        db = connect(args.db)
        if args.command == "init":
            _print({"ok": True, "schema_version": SCHEMA_VERSION, "database": str(args.db or default_db_path())})
        elif args.command == "ingest":
            row, inserted = ingest(db, _read_json(args.json))
            _print({"inserted": inserted, "interaction": row})
        elif args.command == "show":
            _print(get(db, args.id))
        elif args.command == "history":
            _print(history(db, args.id))
        elif args.command == "pending":
            _print(pending(db, args.limit))
        elif args.command == "set-draft":
            _print(set_draft(db, args.id, _read_json(args.json)))
        elif args.command == "mark":
            _print(mark(db, args.id, args.status, detail=args.detail,
                        published_text=args.published_text,
                        published_url=args.published_url,
                        parent_external_id=args.parent_external_id))
        elif args.command == "publication-gate":
            _print(publication_gate(
                db, args.id, policy=load_publishing_policy(args.config)
            ))
        elif args.command == "record-attempt":
            _print(record_publication_attempt(
                db, args.id, args.outcome,
                error_code=args.error_code, detail=args.detail,
            ))
        elif args.command == "correct-publication":
            _print(correct_publication(db, args.id, detail=args.detail))
        elif args.command == "set-cursor":
            set_cursor(db, args.platform, args.external_id)
            _print({"ok": True, "platform": args.platform, "last_processed_id": args.external_id})
        elif args.command == "cursor":
            _print(get_cursor(db, args.platform))
        elif args.command == "summary":
            rows = db.execute("SELECT status,count(*) AS count FROM interactions GROUP BY status").fetchall()
            _print({row["status"]: row["count"] for row in rows})
        return 0
    except (StateError, OSError, sqlite3.Error) as exc:
        print(f"social-state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
