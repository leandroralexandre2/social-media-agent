#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

if ! command -v plow-agents >/dev/null 2>&1; then
  echo 'plow-agents is not on PATH.' >&2
  echo 'Example: export PATH="/path/to/plow-agents/bin:$PATH"' >&2
  exit 2
fi

if [ ! -s plow-credentials ]; then
  echo 'No local agent credential yet.'
  echo 'Run: plow-agents login'
  echo 'Then: plow-agents lines'
  echo 'Then deploy on a free line: plow-agents deploy --local --line <line-uid>'
  exit 0
fi

chmod 0600 plow-credentials
echo 'Local credential is present. Run ./scripts/doctor.sh, then docker compose up -d --build.'
