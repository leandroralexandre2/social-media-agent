import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text()


def test_image_inherits_current_pinned_plow_openclaw_base():
    dockerfile = text("Dockerfile")
    assert "base-771198a9609dcef54d44843e7da5329c17fa51b4@sha256:" in dockerfile
    assert "f1e7c421b97a80f1bd17015f96daceb965f350a241f7edc7e4d856a0e3a6f8f5" in dockerfile
    assert "AGENT_RUNTIME=OpenClaw" in dockerfile
    assert "HERMES" not in dockerfile


def test_agent_index_identity_is_inside_cloud_image():
    dockerfile = text("Dockerfile")
    assert "ENV AGENT_ID=social-media-agent" in dockerfile
    assert 'AGENT_NAME="Social Media Agent"' in dockerfile
    assert "AGENT_BLURB=" in dockerfile
    assert "agent_index_client.py" not in dockerfile
    assert not (ROOT / "agent_index_client.py").exists()


def test_image_contains_only_variant_payload():
    dockerfile = text("Dockerfile")
    assert "COPY prompt/AGENTS.md /opt/plow/prompt/AGENTS.md" in dockerfile
    assert "COPY skills/ /opt/plow/skills/" in dockerfile
    assert "/opt/social-media/bin/" in dockerfile
    assert (ROOT / "prompt/AGENTS.md").is_file()
    assert (ROOT / "skills/social-media-engagement/SKILL.md").is_file()
    assert (ROOT / "bin/social_config.py").is_file()


def test_compose_matches_openclaw_state_and_dashboard_contract():
    compose = text("compose.yml")
    assert "agent:" in compose
    assert "./plow-credentials" in compose
    assert "state:/var/lib/plow" in compose
    assert '"127.0.0.1:3001:3001"' in compose
    assert "dev-dashboard:" in compose
    assert "network_mode: service:agent" in compose
    assert "stop_grace_period: 35s" in compose
    assert "/var/lib/hermes" not in compose.lower()
    assert ".env" not in compose


def test_prompt_defines_real_job_and_multiplayer_authority():
    prompt = text("prompt/AGENTS.md")
    assert "Social Engagement Lead" in prompt
    assert "OpenClaw" in prompt
    assert "plow_start_thread" in prompt
    assert "actual owner identity" in prompt
    assert "teammates" in prompt.lower()
    assert "separate OpenClaw history" in prompt
    assert "PROPOSE SM-000001" in prompt
    assert "Only the actual owner" in prompt


def test_prompt_preserves_compact_english_control_and_source_language():
    prompt = text("prompt/AGENTS.md")
    assert "Write every Plow conversation message in English" in prompt
    assert "source interaction" in prompt
    assert "Never narrate" in prompt
    assert "✅ SM-000001 published." in prompt
    assert "❌ SM-000001 was not published." in prompt
    assert "Do not expose technical error codes" in prompt


def test_skill_requires_owner_approval_and_bounded_exact_publication():
    skill = text("skills/social-media-engagement/SKILL.md")
    assert "actual owner" in skill
    assert "Never recompose after approval" in skill
    assert "two total X submissions per approval cycle" in skill
    assert "TARGET_NOT_UNIQUE" in skill
    assert "MISROUTED_PUBLICATION" in skill
    assert "X_CONCLUSIVE_ABSENCE" in skill
    assert "Explicitly forbidden output pattern" in skill
    assert "plow_start_thread" in skill


def test_native_openclaw_automation_is_the_only_scheduler_contract():
    prompt = text("prompt/AGENTS.md")
    skill = text("skills/social-media-engagement/SKILL.md")
    assert "native OpenClaw automation" in prompt
    assert "social-media-monitor" in prompt
    assert "OpenClaw's native automation" in skill
    assert not (ROOT / "scripts/enable-social-monitor.sh").exists()


def test_no_out_of_band_messages_or_hermes_boot_payload_remain():
    assert not (ROOT / "bin/messages_notify.py").exists()
    assert not (ROOT / "bin/plow_relay.py").exists()
    assert not (ROOT / "runtime/persona.md").exists()
    assert not (ROOT / "docker/cont-init.d/05-install-agent-payload.sh").exists()


def test_secrets_and_generated_state_are_ignored():
    gitignore = text(".gitignore").splitlines()
    dockerignore = text(".dockerignore").splitlines()
    assert "plow-credentials*" in gitignore
    assert "plow-credentials*" in dockerignore
    assert "*.sqlite3" in gitignore
    assert not list(ROOT.glob("plow-credentials.*backup"))


def test_project_is_mit_with_prior_attribution_preserved():
    assert text("LICENSE").startswith("MIT License")
    assert "Apache-2.0.txt" in text("NOTICE")
    assert (ROOT / "LICENSES/Apache-2.0.txt").is_file()


def test_scripts_parse():
    for path in ROOT.glob("scripts/*.sh"):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{path}: {result.stderr}"
