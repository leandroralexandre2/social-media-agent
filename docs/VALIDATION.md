# Validation

## Latest automated result

Validated on 2026-09-26: **55 tests passed**. Python compilation, shell syntax,
Compose YAML, and GitHub Actions YAML also passed. A container build and live
Plow/Latch smoke test still require Docker and an active Plow line; those are
intentionally listed as pending evidence below rather than claimed as complete.

## Automated contracts

Run from the repository root:

```sh
python3 -m pytest -q
python3 -m compileall -q bin
```

The suite checks:

- OpenClaw base pinning and cloud-visible Agent Index identity;
- persistent `/var/lib/plow` state and local dashboard isolation;
- MIT licensing and removal of local credential backups;
- one-click configuration validation and atomic persistence;
- social URL/author/parent binding and public mention requirements;
- state transitions, deduplication, approval cycles, caps and bounded retry;
- multiplayer owner authority and session-isolation instructions;
- concise English control messages and source-language social drafts.

## Container contracts

With Docker running:

```sh
./scripts/doctor.sh
docker compose build agent
docker compose config --quiet
```

## Local end-to-end evidence

Record the date, line, commit and result after testing:

| Check | Evidence |
|---|---|
| Owner first contact receives one response | Pending |
| Latch Browser use reads X notifications | Pending |
| Latch Browser use reads LinkedIn notifications | Pending |
| Team review room receives isolated replies | Pending |
| Non-owner approval is rejected | Pending |
| Owner approval publishes exact stored text | Pending |
| Direct URL and intended parent are recorded | Pending |
| Native recurring monitor runs once | Pending |
| Agent Index reports OpenClaw usage | Pending |

## Cloud evidence

The release is ready for one-click admission only after all of these are saved:

- public repository commit SHA;
- public GHCR image digest built for `linux/amd64`;
- successful `plow-agents deploy IMAGE@sha256:DIGEST --line ...`;
- `plow-agents agents` status showing ready;
- first text and multiplayer room smoke test;
- Agent Index page showing the install and usage.
