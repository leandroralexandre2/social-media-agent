#!/usr/bin/env bash
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
failures=0
warnings=0

ok() { printf 'OK   %s\n' "$1"; }
warn() { printf 'WARN %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }

if command -v plow-agents >/dev/null 2>&1; then
  ok "plow-agents is on PATH"
else
  fail "plow-agents is not on PATH; export PATH=\"/path/to/plow-agents/bin:\$PATH\""
fi

if [ -s "$root/plow-credentials" ]; then
  if grep -q '^PLOW_AGENT_TOKEN=.' "$root/plow-credentials"; then
    ok "plow-credentials exists and contains an agent token"
  else
    fail "plow-credentials exists but has no PLOW_AGENT_TOKEN value"
  fi
else
  fail "plow-credentials is missing; run plow-agents mint <free-line-uid> or plow-agents deploy --local --line <line-uid>"
fi

if [ -f "$root/.env" ]; then
  ok ".env exists"
  grep -q '^SOCIAL_MESSAGES_RECIPIENT=.' "$root/.env" \
    && ok "Messages recipient is configured" \
    || warn "SOCIAL_MESSAGES_RECIPIENT is empty; draft notifications will fail"
  grep -Eq '^SOCIAL_APPROVAL_CHAT_UID=cht_.+' "$root/.env" \
    && ok "trusted approval chat is configured" \
    || warn "SOCIAL_APPROVAL_CHAT_UID is missing or is not a cht_... value"
else
  warn ".env is missing; run ./scripts/setup.sh"
fi

if [ -d "$root/runtime/social-media.toml" ]; then
  fail "runtime/social-media.toml is a directory; if empty, run rmdir runtime/social-media.toml && ./scripts/setup.sh"
elif [ -f "$root/runtime/social-media.toml" ]; then
  if python3 "$root/bin/social_monitor.py" \
      --config "$root/runtime/social-media.toml" --check >/dev/null 2>&1; then
    ok "social-media.toml is valid"
  else
    fail "social-media.toml is invalid; run python3 bin/social_monitor.py --config runtime/social-media.toml --check"
  fi
else
  fail "runtime/social-media.toml is missing; run ./scripts/setup.sh and configure company.name"
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon is running"
    if [ -s "$root/plow-credentials" ] && [ -f "$root/runtime/social-media.toml" ]; then
      if (cd "$root" && docker compose config --quiet >/dev/null 2>&1); then
        ok "Docker Compose configuration is valid"
      else
        fail "Docker Compose configuration is invalid; run docker compose config"
      fi
    fi
  else
    fail "Docker is installed but the daemon is not running; run open -a Docker"
  fi
else
  fail "Docker is not installed"
fi

printf '\nDoctor result: %s failure(s), %s warning(s).\n' "$failures" "$warnings"
[ "$failures" -eq 0 ]
