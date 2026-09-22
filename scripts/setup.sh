#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)

if [ ! -f "$root/.env" ]; then
  cp "$root/.env.example" "$root/.env"
  chmod 0600 "$root/.env"
  echo "created .env; set SOCIAL_MESSAGES_RECIPIENT and SOCIAL_APPROVAL_CHAT_UID"
fi

if [ -d "$root/runtime/social-media.toml" ]; then
  echo "ERROR: runtime/social-media.toml is a directory, but it must be a file." >&2
  echo "If it is empty, run: rmdir runtime/social-media.toml && ./scripts/setup.sh" >&2
  exit 2
elif [ ! -f "$root/runtime/social-media.toml" ]; then
  cp "$root/runtime/social-media.toml.example" "$root/runtime/social-media.toml"
  chmod 0600 "$root/runtime/social-media.toml"
  echo "created runtime/social-media.toml; set company.name, aliases and search terms"
fi

if [ ! -f "$root/plow-credentials" ]; then
  echo "NEXT: plow-credentials is missing." >&2
  echo "Run 'plow-agents lines', then 'plow-agents mint <free-line-uid>' in this directory." >&2
fi

echo "Run ./scripts/doctor.sh before starting Docker."
