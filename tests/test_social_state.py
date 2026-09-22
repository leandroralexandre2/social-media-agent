import json
import datetime as dt

import pytest

from conftest import load_script

state = load_script("social_state.py")


@pytest.fixture
def db(tmp_path):
    return state.connect(tmp_path / "state.sqlite3")


def item(**overrides):
    value = {
        "platform": "x",
        "external_id": "187654321",
        "url": "https://x.com/example/status/187654321",
        "author": "@example",
        "content": "A empresa pode ajudar?",
        "interaction_type": "mention",
        "sentiment": "neutral",
        "priority": "normal",
        "detected_at": "2026-09-17T12:00:00+00:00",
    }
    value.update(overrides)
    return value


def test_ingest_is_idempotent_and_preserves_one_draft_id(db):
    first, inserted = state.ingest(db, item())
    second, inserted_again = state.ingest(db, item(content="Texto atualizado"))
    assert inserted is True
    assert inserted_again is False
    assert first["draft_id"] == second["draft_id"] == "SM-000001"
    assert second["content"] == "Texto atualizado"
    assert db.execute("select count(*) from interactions").fetchone()[0] == 1


@pytest.mark.parametrize("platform,url", [
    ("x", "javascript:alert(1)"),
    ("x", "https://evil.example/post/1"),
    ("linkedin", "https://x.com/example/status/1"),
])
def test_ingest_rejects_non_platform_urls(db, platform, url):
    with pytest.raises(state.StateError, match="HTTPS"):
        state.ingest(db, item(platform=platform, url=url))


def test_draft_approval_and_publish_are_audited(db):
    row, _ = state.ingest(db, item())
    drafted = state.set_draft(db, row["draft_id"], {
        "drafts": ["@example Claro — vamos conversar!", "@example Pode contar mais?"],
        "recommended_index": 0,
        "rationale": "Direct question",
        "risk": "normal",
    })
    assert drafted["status"] == "drafted"
    assert drafted["drafts"][0].startswith("@example")
    assert state.mark(db, row["draft_id"], "notified")["notified_at"]
    assert state.mark(db, row["draft_id"], "approved")["approved_at"]
    published = state.mark(
        db, row["draft_id"], "published",
        published_text="@example Claro — vamos conversar!",
        published_url="https://x.com/brand/status/287654321",
        parent_external_id="187654321",
    )
    assert published["published_text"] == "@example Claro — vamos conversar!"
    assert published["published_at"]
    events = [r[0] for r in db.execute(
        "select event_type from events where interaction_id=? order by id", (row["id"],)
    )]
    assert events == ["ingested", "drafted", "notified", "approved", "published"]
    attempt = db.execute(
        "select outcome,error_code from publication_attempts where interaction_id=?",
        (row["id"],),
    ).fetchone()
    assert tuple(attempt) == ("success", None)


def test_published_text_must_match_the_approved_stored_draft(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Exact approved text"]})
    state.mark(db, row["draft_id"], "approved")
    with pytest.raises(state.StateError, match="exactly match"):
        state.mark(
            db, row["draft_id"], "published",
            published_text="@example Changed after approval",
        )


def test_invalid_state_transition_fails_closed(db):
    row, _ = state.ingest(db, item())
    with pytest.raises(state.StateError, match="invalid transition"):
        state.mark(db, row["draft_id"], "published", published_text="oops")


def test_public_drafts_require_the_exact_author_mention(db):
    x_row, _ = state.ingest(db, item())
    with pytest.raises(state.StateError, match="must start with mention"):
        state.set_draft(db, x_row["draft_id"], {"drafts": ["Thanks!"]})

    linkedin_row, _ = state.ingest(db, item(
        platform="linkedin",
        external_id="li-1",
        url="https://www.linkedin.com/feed/update/urn:li:activity:1/",
        author="Ingrid Silva",
        interaction_type="comment",
    ))
    drafted = state.set_draft(
        db, linkedin_row["draft_id"], {"drafts": ["@Ingrid Silva Thanks!"]}
    )
    assert drafted["required_mention"] == "@Ingrid Silva"


def test_direct_message_draft_does_not_require_a_mention(db):
    row, _ = state.ingest(db, item(
        external_id="dm-1", author="Example Person", interaction_type="direct_message"
    ))
    assert state.set_draft(db, row["draft_id"], {"drafts": ["Thanks!"]})["drafts"] == ["Thanks!"]


def test_public_x_item_requires_a_handle(db):
    with pytest.raises(state.StateError, match="require an @handle"):
        state.ingest(db, item(author="Example Person"))


def test_public_x_external_id_must_match_canonical_url(db):
    with pytest.raises(state.StateError, match="must match the status ID"):
        state.ingest(db, item(external_id="999"))


def test_public_x_author_must_match_canonical_url(db):
    with pytest.raises(state.StateError, match="author handle must match"):
        state.ingest(db, item(author="@someone_else"))


def test_dedup_does_not_mutate_a_target_after_drafting(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Original reply"]})
    same, inserted = state.ingest(db, item(
        author="@attacker",
        content="Changed content",
        url="https://x.com/attacker/status/187654321",
    ))
    assert inserted is False
    assert same["author"] == "@example"
    assert same["content"] == "A empresa pode ajudar?"
    assert same["url"] == "https://x.com/example/status/187654321"


def test_mention_prefix_requires_a_real_boundary(db):
    row, _ = state.ingest(db, item())
    with pytest.raises(state.StateError, match="must start with mention"):
        state.set_draft(db, row["draft_id"], {"drafts": ["@exampleevil Thanks"]})


def test_repeated_or_concurrent_state_claim_fails_closed(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Thanks!"]})
    state.mark(db, row["draft_id"], "approved")
    with pytest.raises(state.StateError, match="already approved"):
        state.mark(db, row["draft_id"], "approved")
    with pytest.raises(state.StateError, match="cannot draft"):
        state.set_draft(db, row["draft_id"], {"drafts": ["@example Changed"]})


def test_cursor_can_be_read_before_and_after_checkpoint(db):
    assert state.get_cursor(db, "x")["last_processed_id"] is None
    state.set_cursor(db, "x", "post-123")
    assert state.get_cursor(db, "x")["last_processed_id"] == "post-123"
    assert state.get_cursor(db)["x"]["last_processed_id"] == "post-123"


def test_publication_gate_spaces_separate_verified_publications(db):
    first, _ = state.ingest(db, item())
    state.set_draft(db, first["draft_id"], {"drafts": ["@example First"]})
    state.mark(db, first["draft_id"], "approved")
    state.mark(
        db, first["draft_id"], "published", published_text="@example First",
        published_url="https://x.com/brand/status/287654320",
        parent_external_id="187654321",
    )

    second, _ = state.ingest(db, item(
        external_id="187654322", url="https://x.com/example/status/187654322"
    ))
    state.set_draft(db, second["draft_id"], {"drafts": ["@example Second"]})
    state.mark(db, second["draft_id"], "approved")
    gate = state.publication_gate(db, second["draft_id"])
    assert gate["allowed"] is False
    assert gate["reason"] == "minimum_interval"
    assert 1 <= gate["wait_seconds"] <= 60


def test_x_344_retry_is_bounded_and_backed_off(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    base = dt.datetime(2026, 9, 21, 12, 0, tzinfo=dt.timezone.utc)

    state.record_publication_attempt(
        db, row["draft_id"], "rate_limited", error_code="344",
        created_at=base.isoformat(timespec="seconds"),
    )
    waiting = state.publication_gate(db, row["draft_id"], now=base + dt.timedelta(seconds=5))
    assert waiting["reason"] == "retry_backoff"
    assert waiting["wait_seconds"] == 7
    ready = state.publication_gate(db, row["draft_id"], now=base + dt.timedelta(seconds=12))
    assert ready["allowed"] is True
    assert ready["attempt_number"] == 2

    second_at = base + dt.timedelta(seconds=12)
    state.record_publication_attempt(
        db, row["draft_id"], "rate_limited", error_code="344",
        created_at=second_at.isoformat(timespec="seconds"),
    )
    exhausted = state.publication_gate(
        db, row["draft_id"], now=second_at + dt.timedelta(seconds=20)
    )
    assert exhausted["allowed"] is False
    assert exhausted["reason"] == "retry_exhausted"


def test_x_conclusive_absence_allows_exactly_one_safe_retry(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    base = dt.datetime(2026, 9, 21, 12, 0, tzinfo=dt.timezone.utc)

    state.record_publication_attempt(
        db, row["draft_id"], "failed", error_code="X_CONCLUSIVE_ABSENCE",
        detail="reply absent from canonical thread",
        created_at=base.isoformat(timespec="seconds"),
    )
    waiting = state.publication_gate(db, row["draft_id"], now=base + dt.timedelta(seconds=5))
    assert waiting["reason"] == "retry_backoff"
    assert waiting["wait_seconds"] == 7
    ready = state.publication_gate(db, row["draft_id"], now=base + dt.timedelta(seconds=12))
    assert ready["allowed"] is True
    assert ready["attempt_number"] == 2
    assert ready["max_attempts"] == 2

    state.record_publication_attempt(
        db, row["draft_id"], "failed", error_code="X_GENERIC_CLIENT_ERROR",
        created_at=(base + dt.timedelta(seconds=12)).isoformat(timespec="seconds"),
    )
    exhausted = state.publication_gate(
        db, row["draft_id"], now=base + dt.timedelta(seconds=30)
    )
    assert exhausted["allowed"] is False
    assert exhausted["reason"] == "retry_exhausted"


def test_uncertain_submit_never_becomes_automatically_retryable(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    state.record_publication_attempt(db, row["draft_id"], "uncertain", detail="MCP timeout")
    gate = state.publication_gate(db, row["draft_id"])
    assert gate["allowed"] is False
    assert gate["reason"] == "manual_review_required"


def test_explicit_reapproval_starts_a_new_bounded_attempt_cycle(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    first_approval = state.mark(db, row["draft_id"], "approved")
    assert first_approval["approval_cycle"] == 1
    failed_at = dt.datetime(2026, 9, 21, 12, 0, tzinfo=dt.timezone.utc)
    state.record_publication_attempt(
        db, row["draft_id"], "failed", detail="generic X error",
        created_at=failed_at.isoformat(timespec="seconds"),
    )
    state.mark(db, row["draft_id"], "error", detail="generic X error")
    second_approval = state.mark(
        db, row["draft_id"], "approved", detail="owner explicitly requested retry"
    )
    assert second_approval["approval_cycle"] == 2
    cooldown = state.publication_gate(
        db, row["draft_id"], now=failed_at + dt.timedelta(seconds=10)
    )
    assert cooldown["reason"] == "owner_retry_cooldown"
    assert cooldown["wait_seconds"] == 50
    ready = state.publication_gate(
        db, row["draft_id"], now=failed_at + dt.timedelta(seconds=60)
    )
    assert ready["allowed"] is True
    assert ready["approval_cycle"] == 2


def test_publication_receipt_must_prove_the_intended_parent(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    with pytest.raises(state.StateError, match="does not match"):
        state.mark(
            db, row["draft_id"], "published",
            published_text="@example Reply",
            published_url="https://x.com/brand/status/287654321",
            parent_external_id="111111111",
        )
    with pytest.raises(state.StateError, match="source post"):
        state.mark(
            db, row["draft_id"], "published",
            published_text="@example Reply",
            published_url="https://x.com/example/status/187654321",
            parent_external_id="187654321",
        )


def test_history_returns_a_secret_free_incident_timeline(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    state.record_publication_attempt(db, row["draft_id"], "failed", detail="generic UI error")
    state.mark(db, row["draft_id"], "error", detail="generic UI error")
    report = state.history(db, row["draft_id"])
    assert report["status"] == "error"
    assert report["publication_attempts"][0]["outcome"] == "failed"
    assert "drafts" not in report
    assert "content" not in report


def test_false_positive_publication_can_be_corrected_without_erasing_attempt(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    state.mark(
        db, row["draft_id"], "published",
        published_text="@example Reply",
        published_url="https://x.com/brand/status/287654321",
        parent_external_id="187654321",
    )
    corrected = state.correct_publication(
        db, row["draft_id"], detail="later reconciliation found a wrong parent"
    )
    assert corrected["status"] == "error"
    assert corrected["published_url"].endswith("287654321")
    assert db.execute(
        "SELECT count(*) FROM publication_attempts WHERE outcome='success'"
    ).fetchone()[0] == 1
    reapproved = state.mark(
        db, row["draft_id"], "approved", detail="owner explicitly requested retry"
    )
    gate = state.publication_gate(db, reapproved["draft_id"])
    assert gate["published_last_24h"] == 1
    assert gate["reason"] == "minimum_interval"


def test_incident_details_redact_common_secret_shapes(db):
    row, _ = state.ingest(db, item())
    state.set_draft(db, row["draft_id"], {"drafts": ["@example Reply"]})
    state.mark(db, row["draft_id"], "approved")
    state.record_publication_attempt(
        db, row["draft_id"], "failed",
        detail="token=plow_1234567890 password=hunter2",
    )
    report = state.history(db, row["draft_id"])
    detail = report["publication_attempts"][0]["detail"]
    assert "plow_1234567890" not in detail
    assert "hunter2" not in detail


def test_existing_v1_ledger_is_upgraded_without_losing_interactions(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    old = state.connect(path)
    row, _ = state.ingest(old, item())
    old.execute("ALTER TABLE interactions DROP COLUMN approval_cycle")
    old.execute("ALTER TABLE interactions DROP COLUMN published_url")
    old.execute("ALTER TABLE interactions DROP COLUMN published_parent_external_id")
    old.execute("DROP TABLE publication_attempts")
    old.execute(
        """CREATE TABLE publication_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          interaction_id INTEGER NOT NULL REFERENCES interactions(id),
          platform TEXT NOT NULL,
          outcome TEXT NOT NULL,
          error_code TEXT,
          detail TEXT,
          created_at TEXT NOT NULL
        )"""
    )
    old.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
    old.commit()
    old.close()

    upgraded = state.connect(path)
    assert state.get(upgraded, row["draft_id"])["external_id"] == "187654321"
    assert upgraded.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()[0] == "3"
    assert upgraded.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='publication_attempts'"
    ).fetchone()[0] == 1
    interaction_columns = {
        value["name"] for value in upgraded.execute("PRAGMA table_info(interactions)")
    }
    attempt_columns = {
        value["name"] for value in upgraded.execute("PRAGMA table_info(publication_attempts)")
    }
    assert {"approval_cycle", "published_url", "published_parent_external_id"} <= interaction_columns
    assert "approval_cycle" in attempt_columns


def test_cli_round_trip(tmp_path, capsys):
    db_path = tmp_path / "cli.sqlite3"
    payload = tmp_path / "item.json"
    payload.write_text(json.dumps(item()))
    assert state.main(["--db", str(db_path), "ingest", "--json", str(payload)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["inserted"] is True
    assert state.main(["--db", str(db_path), "show", "SM-000001"]) == 0
    assert json.loads(capsys.readouterr().out)["external_id"] == "187654321"
