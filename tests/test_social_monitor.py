from pathlib import Path

import pytest

from conftest import load_script

monitor = load_script("social_monitor.py")


def config(tmp_path: Path, company="Acme") -> Path:
    path = tmp_path / "social-media.toml"
    path.write_text(f'''\
[company]
name = "{company}"
aliases = ["@acme"]
[monitor]
max_items_per_platform = 15
max_browser_actions_per_platform = 18
[browser]
reuse_authenticated_session = true
keep_session_open_minutes = 120
[publishing]
x_min_interval_seconds = 60
linkedin_min_interval_seconds = 45
x_max_publications_per_24h = 25
linkedin_max_publications_per_24h = 25
x_error_344_backoff_seconds = [12, 20]
post_fill_settle_seconds = 2
[platforms.x]
enabled = true
notifications_url = "https://x.com/notifications"
search_terms = ["Acme"]
[platforms.linkedin]
enabled = true
notifications_url = "https://www.linkedin.com/notifications/"
search_terms = []
[persona]
description = "Friendly and concise"
languages = ["en"]
forbidden_topics = ["legal promises"]
[safety]
auto_publish = false
''')
    return path


def test_prompt_carries_surfaces_dedup_and_human_gate(tmp_path):
    prompt = monitor.render_prompt(monitor.load_config(config(tmp_path)))
    assert "https://x.com/notifications" in prompt
    assert "https://www.linkedin.com/notifications/" in prompt
    assert "inserted=false" in prompt
    assert "Browser Vault" in prompt
    assert "Never like, repost, follow, connect" in prompt
    assert "trusted owner conversation" in prompt
    assert "auto_publish is false" in prompt
    assert "Browser use" in prompt
    assert "camoufox-browsing" in prompt
    assert "social_state.py cursor <platform>" in prompt
    assert "at most 18 browser actions" in prompt
    assert "Every public draft must start" in prompt
    assert "APPROVE <draft_id>" in prompt
    assert "Reuse an existing healthy authenticated Browser use session" in prompt
    assert "Keep a healthy authenticated session open for up to 120 minutes" in prompt
    assert "SESSION_NOT_PERSISTED" in prompt
    assert "repetitive engagement bait" in prompt
    assert "detect and match the source interaction language" in prompt
    assert "language of the direct question or request" in prompt
    assert "Never translate a social reply to English" in prompt
    assert "Fallback languages when the source language is genuinely indeterminate: en" in prompt
    assert "numeric `/status/<id>` value as `external_id`" in prompt
    assert "Every draft must be real text" in prompt
    assert "Never send progress messages" in prompt
    assert "Do not expose technical error codes" in prompt


def test_placeholder_company_refuses_to_run(tmp_path):
    with pytest.raises(monitor.ConfigError, match="company.name"):
        monitor.load_config(config(tmp_path, "CHANGE_ME"))


def test_v1_refuses_auto_publish(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace("auto_publish = false", "auto_publish = true"))
    with pytest.raises(monitor.ConfigError, match="auto_publish=false"):
        monitor.load_config(path)


def test_browser_action_budget_is_bounded(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace(
        "max_browser_actions_per_platform = 18",
        "max_browser_actions_per_platform = 0",
    ))
    with pytest.raises(monitor.ConfigError, match="max_browser_actions_per_platform"):
        monitor.load_config(path)


def test_notification_url_must_stay_on_platform_domain(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace(
        "https://x.com/notifications", "https://evil.example/notifications"
    ))
    with pytest.raises(monitor.ConfigError, match="HTTPS x URL"):
        monitor.load_config(path)


def test_session_reuse_cannot_be_disabled(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace(
        "reuse_authenticated_session = true", "reuse_authenticated_session = false"
    ))
    with pytest.raises(monitor.ConfigError, match="reuse_authenticated_session"):
        monitor.load_config(path)


def test_x_344_backoff_is_bounded(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace(
        "x_error_344_backoff_seconds = [12, 20]",
        "x_error_344_backoff_seconds = [12, 20, 30, 40]",
    ))
    with pytest.raises(monitor.ConfigError, match="x_error_344_backoff_seconds"):
        monitor.load_config(path)


def test_empty_aliases_and_languages_are_rejected_cleanly(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text().replace('aliases = ["@acme"]', 'aliases = [""]'))
    with pytest.raises(monitor.ConfigError, match="non-empty strings"):
        monitor.load_config(path)

    path = config(tmp_path)
    path.write_text(path.read_text().replace('languages = ["en"]', 'languages = []'))
    with pytest.raises(monitor.ConfigError, match="at least one language"):
        monitor.load_config(path)


def test_existing_v030_config_remains_valid_with_safe_defaults(tmp_path):
    path = config(tmp_path)
    text = path.read_text()
    text = text.replace('''[browser]
reuse_authenticated_session = true
keep_session_open_minutes = 120
[publishing]
x_min_interval_seconds = 60
linkedin_min_interval_seconds = 45
x_max_publications_per_24h = 25
linkedin_max_publications_per_24h = 25
x_error_344_backoff_seconds = [12, 20]
post_fill_settle_seconds = 2
''', "")
    path.write_text(text)
    loaded = monitor.load_config(path)
    prompt = monitor.render_prompt(loaded)
    assert "Keep a healthy authenticated session open for up to 120 minutes" in prompt


def test_check_mode_reports_valid_config(tmp_path, capsys):
    assert monitor.main(["--config", str(config(tmp_path)), "--check"]) == 0
    assert capsys.readouterr().out.strip() == "configuration ok"
