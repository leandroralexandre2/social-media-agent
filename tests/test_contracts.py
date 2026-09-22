import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_plow_credentials_persistent_home_and_read_only_config():
    compose = (ROOT / "compose.yml").read_text()
    assert "./plow-credentials" in compose
    assert "agent-home:/var/lib/hermes" in compose
    assert "social-media.toml:/opt/plow/social/config/social-media.toml:ro" in compose
    assert "stop_grace_period: 35s" in compose
    assert "ports:" not in compose
    assert "SOCIAL_POLL_SCHEDULE:-every 1h" in compose


def test_secrets_and_local_configuration_are_not_in_the_image_context():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert "plow-credentials" in ignored
    assert ".env" in ignored
    assert "runtime/social-media.toml" in ignored


def test_credential_example_cannot_accidentally_point_at_an_old_api():
    example = (ROOT / "plow-credentials.example").read_text()
    assert "<api-root-without-v1>" in example
    assert "api.plow.ai" not in example


def test_runtime_persona_and_skill_both_require_explicit_approval():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "never publishes" in persona
    assert "explicit owner command" in persona
    assert "trusted owner command" in skill
    assert "Never recompose after approval" in skill


def test_runtime_persona_and_skill_define_fast_bounded_publication():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "do not narrate browser clicks" in persona
    assert "one primary interaction strategy and one safe fallback" in persona
    assert "Do not narrate individual browser" in skill
    assert "submit once" in skill
    assert "TARGET_NOT_UNIQUE" in persona
    assert "[data-testid=\"reply\"]" in skill
    assert "--parent-external-id" in persona
    assert "MISROUTED_PUBLICATION" in skill
    assert "correct-publication" in skill
    assert "Never delete" in persona


def test_runtime_contract_reuses_sessions_and_bounds_x_344_retries():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "publication-gate" in persona
    assert "SESSION_NOT_PERSISTED" in persona
    assert "record-attempt <id> rate_limited" in persona
    assert "Never mix X" in persona
    assert "two retries after the initial attempt" in skill
    assert "never re-authenticate" in skill


def test_runtime_persona_and_skill_follow_browser_use_without_loops():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "Browser use" in persona
    assert "camoufox-browsing" in persona
    assert "Enable in Safari" in persona
    assert "Never repeat the same failed action" in skill


def test_runtime_contract_is_english_and_requires_mentions():
    persona = (ROOT / "runtime/persona.md").read_text()
    notify = (ROOT / "bin/messages_notify.py").read_text()
    assert "APPROVE SM-000001" in persona
    assert "EDIT SM-000001" in persona
    assert "IGNORE SM-000001" in persona
    assert "Every public reply must begin" in persona
    assert "APPROVE {draft_id}" in notify


def test_owner_conversation_is_compact_and_hides_tool_narration():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "The owner conversation is a concise control interface" in persona
    assert "All messages to the owner are in English" in persona
    assert "First publish attempt failed. I’ll try once more." in persona
    assert "✅ SM-000008 published." in persona
    assert "❌ SM-000008 was not published." in persona
    assert "Do not expose technical error codes" in persona
    assert "Never send messages\nbeginning with “let me”" in skill
    assert "RESPONSE <id>" in skill


def test_release_refreshes_only_agent_owned_live_behavior_files():
    init = (ROOT / "docker/cont-init.d/05-install-agent-payload.sh").read_text()
    assert '"$home/SOUL.md"' in init
    assert '"$skill/SKILL.md"' in init
    assert '"$skill/references/commands.md"' in init
    assert "rm -rf" not in init


def test_social_replies_match_source_language_while_owner_status_stays_english():
    persona = (ROOT / "runtime/persona.md").read_text()
    skill = (ROOT / "agent-skills/productivity/social-media-engagement/SKILL.md").read_text()
    assert "owner-facing conversation, status messages, errors, and approval commands" in persona
    assert "Suggested social replies are written in the language of the" in persona
    assert "For mixed-language content" in persona
    assert "Owner-facing status" in skill


def test_image_payload_paths_have_matching_sources():
    dockerfile = (ROOT / "Dockerfile").read_text()
    for source in re.findall(r"^COPY\s+([^ ]+)\s+", dockerfile, re.M):
        assert (ROOT / source.rstrip("/")).exists(), source


def test_shell_scripts_parse():
    for path in [*ROOT.glob("scripts/*"), *ROOT.glob("docker/cont-init.d/*")]:
        if path.is_file():
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            assert result.returncode == 0, f"{path}: {result.stderr}"
