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
  fail 'plow-agents is not on PATH; export PATH="/path/to/plow-agents/bin:$PATH"'
fi

if [ -s "$root/plow-credentials" ]; then
  if grep -q '^PLOW_AGENT_TOKEN=.' "$root/plow-credentials"; then
    ok "plow-credentials contains an agent token"
  else
    fail "plow-credentials has no PLOW_AGENT_TOKEN value"
  fi
else
  fail "plow-credentials is missing; run plow-agents deploy --local --line <free-line>"
fi

if grep -q 'plow-openclaw-agent' "$root/README.md" \
  && grep -q '^ENV AGENT_ID=social-media-agent' "$root/Dockerfile"; then
  ok "OpenClaw variant and Agent Index identity are configured"
else
  fail "Dockerfile or README is missing the OpenClaw variant contract"
fi

if grep -q 'base-771198a9609dcef54d44843e7da5329c17fa51b4@sha256:' "$root/Dockerfile"; then
  ok "Plow OpenClaw base is pinned by tag and digest"
else
  fail "Plow OpenClaw base is not pinned by immutable digest"
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon is running"
    if [ -s "$root/plow-credentials" ] \
      && (cd "$root" && docker compose config --quiet >/dev/null 2>&1); then
      ok "Docker Compose configuration is valid"
    else
      fail "Docker Compose configuration is invalid"
    fi
  else
    fail "Docker is installed but the daemon is not running"
  fi
else
  fail "Docker is not installed"
fi

if python3 -m compileall -q "$root/bin"; then
  ok "Python helpers compile"
else
  fail "Python helpers do not compile"
fi

if [ -e "$root/plow-credentials.401-backup" ]; then
  fail "a credential backup is inside the repository"
else
  ok "no credential backup is tracked in the project root"
fi

printf '\nDoctor result: %s failure(s), %s warning(s).\n' "$failures" "$warnings"
[ "$failures" -eq 0 ]
