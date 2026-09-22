import json

from conftest import load_script

notify = load_script("messages_notify.py")


def payload(**overrides):
    value = {
        "draft_id": "SM-000001",
        "platform": "x",
        "author": "@person",
        "category": "question",
        "url": "https://x.com/person/status/1",
        "suggested_reply": "@person Thanks for the question!",
    }
    value.update(overrides)
    return value


def test_render_contains_review_commands_and_no_recipient():
    body = notify.render(payload())
    assert "APPROVE SM-000001" in body
    assert "EDIT SM-000001" in body
    assert "IGNORE SM-000001" in body
    assert "Suggested reply:" in body
    assert "@person Thanks for the question!" in body
    assert len(body) <= 1_800


def test_payload_cannot_cross_to_an_unrelated_domain():
    try:
        notify.render(payload(url="https://example.com/phishing"))
    except notify.NotificationError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("unrelated URL accepted")


def test_suggested_reply_is_never_silently_truncated():
    too_long = "x" * 701
    try:
        notify.render(payload(suggested_reply=too_long))
    except notify.NotificationError as exc:
        assert "exceeds 700" in str(exc)
    else:
        raise AssertionError("oversized reply was silently truncated")


def test_url_cannot_embed_credentials():
    try:
        notify.render(payload(url="https://user:pass@x.com/person/status/1"))
    except notify.NotificationError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("credential-bearing URL accepted")


def test_main_uses_argv_not_applescript_interpolation(tmp_path, monkeypatch, capsys):
    dangerous = 'quote " and \\ and $(touch nope)'
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload(suggested_reply=dangerous)))
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return 0, ""

    monkeypatch.setenv("SOCIAL_MESSAGES_RECIPIENT", "+5511999999999")
    monkeypatch.setattr(notify.plow_relay, "run", fake_run)
    assert notify.main(["--json", str(path)]) == 0
    argv = calls[0][0]
    assert argv[:2] == ["osascript", "-e"]
    assert dangerous in argv[-1]
    assert dangerous not in argv[2]
    assert "+5511999999999" not in capsys.readouterr().out
