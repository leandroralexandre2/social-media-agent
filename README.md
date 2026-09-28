# Social Media Agent

![Social Media Agent](assets/logo.png)

An OpenClaw 2.0 **Social Engagement Lead** for startups. It monitors X and
LinkedIn through the owner's real browser, triages meaningful activity, drafts
context-aware replies, coordinates review with a team, and publishes only after
the owner explicitly approves a stored draft.

[Agent Index](https://aiworthusing.com/agent-index/social-media-agent) ·
[Repository](https://github.com/leandroralexandre2/social-media-agent) ·
[Original workflow demo](https://youtu.be/amh9g_OlNVs)

## Why this is a real first hire

The agent owns a complete operating loop instead of showing a mock workflow:

1. Monitor notifications, mentions, replies, comments, and relevant searches.
2. Deduplicate every interaction in a durable SQLite ledger.
3. Detect the source language and produce 1–3 publishable drafts in that language.
4. Bring useful drafts to the owner or a multiplayer review room.
5. Accept team proposals while reserving publication authority for the owner.
6. Publish the exact approved text and verify its direct URL and parent post.
7. Keep a secret-free audit trail and stop safely on uncertain results.

## OpenClaw 2.0 multiplayer

This image inherits the maintained
[`plow-openclaw-agent`](https://github.com/plow-pbc/plow-openclaw-agent) base.
The owner's direct chat, collaborator DMs, customer/vendor conversations, and
group review rooms each receive separate OpenClaw sessions.

- The owner can monitor, edit, approve, retry, schedule, and start review rooms.
- Teammates can submit public links, review drafts, propose wording, and flag risk.
- Customers and vendors can raise a social issue in their own conversation.
- Only the actual owner identity can authorize a public response.
- Cross-conversation history is not exposed; shared ledger state is not treated
  as permission to disclose private messages.

See [docs/MULTIPLAYER.md](docs/MULTIPLAYER.md) for the authority model and demo
script.

## Safety and reliability

- Human approval is mandatory; auto-publish is disabled.
- Browser credentials and TOTP stay in Latch Browser Vault.
- Social content is untrusted data and can never approve an action.
- Public replies must mention the source author; DMs are exempt.
- X targets are bound to the exact `/status/<id>` article, not the first reply
  button on a thread page.
- A publish succeeds only after the direct reply URL and intended parent are
  verified.
- X retries are bounded to one safe retry after conclusive absence. Ambiguous
  results are never resent.
- Browser work is silent; the user receives a concise result, not click-by-click
  narration.

## Requirements

- macOS with [Plow Latch](https://plow.co/) connected for Browser use
- Docker Desktop for local deployment
- [`plow-agents`](https://github.com/plow-pbc/plow-agents) on `PATH`
- X and/or LinkedIn credentials saved in Latch Browser Vault

No paid social API keys are required.

## Local deployment

Clone the repository and enter it:

```sh
git clone https://github.com/leandroralexandre2/social-media-agent.git
cd social-media-agent
```

Install or expose the current `plow-agents` CLI, then authenticate:

```sh
export PATH="/path/to/plow-agents/bin:$PATH"
plow-agents login
plow-agents lines
```

Choose a `free` line and let the CLI mint the project credential and start
Compose:

```sh
plow-agents deploy --local --line ln_p2
```

Verify the runtime:

```sh
docker compose ps
docker compose logs --tail=100 agent
```

### Apple Silicon Macs (M1/M2/M3/M4)

The Plow base image is `linux/amd64` only. Docker Desktop runs it under
Rosetta by default, and Rosetta lacks the `openat2` syscall that OpenClaw's
state migration needs. The container then restart-loops with:

```text
Failed migrating legacy shared auth store: the Gateway or another SQLite
maintenance command owns this state directory.
plow-boot: gateway exited code=78
```

Fix: Docker Desktop → Settings → General → turn **off** "Use Rosetta for
x86_64/amd64 emulation on Apple Silicon", restart Docker Desktop, then run
`docker compose up --build -d`. The gateway then boots in about 30 seconds.
A `qemu: uncaught target signal 11` line from the Agent Index usage reporter
is expected under QEMU and does not affect the agent.

Before the first deploy, `docker compose config` and `scripts/doctor.sh`
report `env file ./plow-credentials not found`. That is expected; deploy
creates the file.

### Latch Gatekeeper

Latch reviews every browser request against the agent purpose saved in its
settings. If that text does not mention X or LinkedIn, the request is denied
and the agent reports "your Mac's Gatekeeper denied the request". Add a line
such as "allow the social media agent to browse x.com and linkedin.com to read
notifications and mentions; it may draft replies but must not post without my
APPROVE" to the Latch agent purpose before running `CHECK X`.

Open the local owner dashboard at <http://localhost:3001>. Do not expose this
port beyond loopback.

Text the selected line:

```text
Set up social monitoring for my startup.
```

The agent asks once for non-secret brand settings. It never asks for passwords
or verification codes in chat. Configuration, the ledger, OpenClaw sessions,
and Agent Index install identity persist in the named `state` volume.

Do not run `docker compose down -v` unless you intentionally want to erase that
local state.

## Useful commands

```text
CHECK SOCIAL
CHECK X
CHECK LINKEDIN
RESPONSE SM-000001
EDIT SM-000001: <new text>
APPROVE SM-000001
IGNORE SM-000001
RETRY SM-000001
LOGS SM-000001
START SOCIAL TEAM +14155550100 +5511999999999
MONITOR EVERY 2 HOURS
```

Owner-facing conversation is always English. A suggested social response
matches the source interaction language.

## Build and deploy to Plow Cloud

Builds made by `plow-agents image build` target the cloud's `linux/amd64`
platform, including when run from Apple Silicon:

```sh
plow-agents image build ghcr.io/leandroralexandre2/social-media-agent:v1.0.0
plow-agents image push ghcr.io/leandroralexandre2/social-media-agent:v1.0.0
```

Make the GHCR package public. Copy the immutable digest printed by the push,
choose a free line, and deploy the digest rather than the mutable tag:

```sh
plow-agents deploy \
  ghcr.io/leandroralexandre2/social-media-agent@sha256:REPLACE_WITH_DIGEST \
  --line ln_p3
```

Check provisioning:

```sh
plow-agents agents
plow-agents lines
```

The image contains `AGENT_ID=social-media-agent`, so the inherited Agent Index
client registers the existing listing and reports OpenClaw usage every five
minutes. There is no second reporter in this repository.

## Development

The application-specific code uses only Python's standard library. Run:

```sh
python3 -m pip install pytest
python3 -m pytest -q
python3 -m compileall -q bin
```

With Docker available:

```sh
./scripts/doctor.sh
docker compose build agent
```

CI runs the Python contracts and builds the image. See
[docs/VALIDATION.md](docs/VALIDATION.md) for the release evidence checklist.

## Architecture

| Layer | Responsibility |
|---|---|
| Plow OpenClaw base | Phone/email/group transport, session isolation, Latch bridge, native automations, Agent Index reporting |
| `prompt/AGENTS.md` | Social Engagement Lead persona, authority, onboarding, multiplayer behavior |
| `skills/social-media-engagement` | Browser workflow, approval protocol, bounded publication and error handling |
| `social_config.py` | Safe one-click onboarding into persistent non-secret configuration |
| `social_monitor.py` | Validated, deterministic monitoring instructions |
| `social_state.py` | SQLite deduplication, drafts, approvals, receipts, retries, audit history |

## Limitations

X and LinkedIn can change their interfaces, challenge an account, rate-limit
actions, or delay reply visibility. This project cannot remove those platform
controls. It handles them by reusing an authenticated Latch session, bounding
retries, requiring positive verification, and failing closed.

## License

MIT. Earlier Apache-2.0-derived helper attribution is retained in
[`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt) and [`NOTICE`](NOTICE).
