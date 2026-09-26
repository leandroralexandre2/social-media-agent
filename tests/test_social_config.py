import json
import os
from pathlib import Path

import pytest

from conftest import load_script

monitor = load_script("social_monitor.py")
config_cli = load_script("social_config.py")


def payload(**overrides):
    value = {
        "company_name": "Acme",
        "aliases": ["@acme", "Acme Inc"],
        "x_enabled": True,
        "linkedin_enabled": True,
        "x_search_terms": ["Acme"],
        "linkedin_search_terms": ["Acme platform"],
        "persona_description": "Helpful, concise, and warm.",
        "languages": ["en", "pt-BR"],
    }
    value.update(overrides)
    return value


def test_rendered_onboarding_config_is_valid():
    rendered = config_cli.render(payload())
    assert 'name = "Acme"' in rendered
    assert 'languages = ["en", "pt-BR"]' in rendered


def test_init_writes_private_valid_config(tmp_path, capsys):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload()))
    target = tmp_path / "state" / "social-media.toml"
    assert config_cli.main(["--config", str(target), "init", "--json", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["configured"] is True
    assert monitor.load_config(target)["company"]["name"] == "Acme"
    assert os.stat(target).st_mode & 0o777 == 0o600


def test_existing_config_is_not_overwritten_without_force(tmp_path, capsys):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload()))
    target = tmp_path / "social-media.toml"
    assert config_cli.main(["--config", str(target), "init", "--json", str(source)]) == 0
    source.write_text(json.dumps(payload(company_name="Changed")))
    assert config_cli.main(["--config", str(target), "init", "--json", str(source)]) == 2
    assert "--force" in capsys.readouterr().err
    assert monitor.load_config(target)["company"]["name"] == "Acme"


def test_force_replaces_config_after_owner_confirmation(tmp_path):
    source = tmp_path / "input.json"
    target = tmp_path / "social-media.toml"
    source.write_text(json.dumps(payload()))
    assert config_cli.main(["--config", str(target), "init", "--json", str(source)]) == 0
    source.write_text(json.dumps(payload(company_name="Changed")))
    assert config_cli.main([
        "--config", str(target), "init", "--json", str(source), "--force"
    ]) == 0
    assert monitor.load_config(target)["company"]["name"] == "Changed"


def test_status_is_machine_readable_when_not_configured(tmp_path, capsys):
    target = tmp_path / "missing.toml"
    assert config_cli.main(["--config", str(target), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["configured"] is False


def test_at_least_one_platform_is_required():
    with pytest.raises(config_cli.ConfigInputError, match="at least one platform"):
        config_cli.render(payload(x_enabled=False, linkedin_enabled=False))
