# Social Media Agent

Human-approved monitoring and engagement agent for **X (Twitter)** and
**LinkedIn**, derived from the `str-hermes-agent-main` architecture and executed
through the `plow-agents` lifecycle.

The agent navigates social networks using the browser capabilities provided by
Plow/Latch, reuses login and TOTP from the Browser Vault, records each
interaction in SQLite, creates responses in the brand persona, and sends the
suggestion through the macOS Messages app. No social action is published without
human approval.

## What V1 does

- Visits X and LinkedIn notifications on a configurable interval.
- Searches for the configured name, aliases, and terms to find untagged mentions.
- Includes comments, mentions, replies, and relevant direct messages.
- Classifies context, sentiment, priority, and risk.
- Deduplicates by `(platform, external_id)` in SQLite.
- Generates up to three replies and selects one recommended option.
- Notifies the owner through the Messages app via AppleScript on the Mac.
- Accepts `APPROVE`, `EDIT`, `IGNORE`, `RETRY`, or `LOGS` with an `SM-xxxxxx` ID in the agent’s
  trusted conversation.
- After approval, opens the canonical URL, rereads the context, publishes once,
  verifies the result, and writes an audit record.

There is no paid X or LinkedIn API. V1 does not use direct HTTP scraping,
exported cookies, or passwords stored in files; all interaction happens through
the web interface and the Latch Browser Vault.

## Architecture

| Component | Responsibility |
|---|---|
| Plow/Hermes base | Gateway, scheduler, session, and `plow` MCP injection |
| `social_monitor.py` | Validates configuration and defines a safe monitoring tick |
| Plow/Latch browser | Navigates X/LinkedIn using the Browser Vault session |
| `social_state.py` | SQLite, deduplication, IDs, drafts, and audit trail |
| Persona/skill | Triage, style, limits, and approval flow |
| `messages_notify.py` | Runs AppleScript on the Mac through the relay and sends the alert |
| `plow-agents` | Creates/rotates the credential and manages the agent line |

SQLite lives in the `agent-home` volume at
`/var/lib/hermes/state/social-media.sqlite3`. Credentials remain outside the
image and outside the database.

## Prerequisites

- macOS with Docker and Docker Compose.
- `plow-agents` available in `PATH`.
- One free Plow line for the agent.
- X and LinkedIn registered in the Latch Browser Vault, including TOTP when 2FA
  is enabled.
- Latch **Browser use** plugin enabled. For the Safari fallback, keep the
  **Enable in Safari** requirement ready in the Plugins tab.
- Messages app configured on macOS.
- Permission in **System Settings → Privacy & Security → Automation → Messages**
  for the process used by Latch to run `osascript`.

## Installation

From the project root:

```sh
./scripts/setup.sh
```

Before starting Docker, run the preflight check. It reports missing credentials,
invalid configuration, Docker availability, and incomplete notification setup
without printing secrets:

```sh
./scripts/doctor.sh
```

Edit `.env`:

```dotenv
SOCIAL_MESSAGES_RECIPIENT=+5511999999999
SOCIAL_APPROVAL_CHAT_UID=cht_xxx
TZ=America/Sao_Paulo
SOCIAL_POLL_SCHEDULE=every 1h
```

The recipient can be an E.164 phone number or Apple ID accepted by the Messages
app. The `cht_...` value must be the trusted private conversation or group where
the owner will approve drafts.

Edit `runtime/social-media.toml`:

```toml
[company]
name = "My Company"
aliases = ["@mycompany", "Product X"]

[monitor]
max_items_per_platform = 10
max_browser_actions_per_platform = 20

[browser]
reuse_authenticated_session = true
keep_session_open_minutes = 120

[publishing]
x_min_interval_seconds = 60
linkedin_min_interval_seconds = 45
x_max_publications_per_24h = 25
linkedin_max_publications_per_24h = 25
x_error_344_backoff_seconds = [12, 20]
post_fill_settle_seconds = 2

[platforms.x]
enabled = true
notifications_url = "https://x.com/notifications"
search_terms = ["My Company", "Product X"]

[platforms.linkedin]
enabled = true
notifications_url = "https://www.linkedin.com/notifications/"
search_terms = ["My Company"]

[persona]
description = "Professional, human, concise, and lightly humorous when appropriate."
languages = ["en"]
```

Complete the persona and forbidden topics in the same file. V1 rejects the
configuration if `auto_publish` is enabled.

Create the credential with the wrapper:

```sh
plow-agents login
plow-agents lines
plow-agents mint <line-uid>
```

The last command should produce `./plow-credentials`. This file and `.env` are
ignored by Git and by the image build.

## Startup

```sh
docker compose build
docker compose up -d
docker compose logs -f social-media-agent
```

Wait for the log to indicate that Plow has configured the line and MCP. Validate
the state:

```sh
docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_monitor.py --check

docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_state.py init
```

Register the recurring monitor:

```sh
./scripts/enable-social-monitor.sh
docker compose exec -T social-media-agent hermes cron list
```

Run one manual tick before leaving the job on its own:

```sh
docker compose exec -T social-media-agent \
  hermes cron run social-media-monitor
```

Confirm four things: the browser opened both networks, no credential appeared in
the log, a new item received an ID in SQLite, and the suggestion arrived in the
Messages app.

## Approval and publishing

Each alert contains an ID. In the agent’s trusted conversation, use:

```text
APPROVE SM-000001
EDIT SM-000001: @Person Thanks for sharing. We will review it and follow up here.
IGNORE SM-000001
RETRY SM-000001
LOGS SM-000001
```

`EDIT` does not publish: it replaces the text and asks for a new approval.
`APPROVE` publishes exactly the stored text. If the live context has changed,
the agent interrupts publishing and requests a new review. If it cannot visually
confirm the send, it records an error and does not click again. `RETRY` starts a
new audited attempt cycle after an error and still obeys the cooldown. `LOGS`
returns the secret-free incident timeline for that ID.

Every public reply starts with the person’s mention: `@handle` on X and a
mention selected by full name on LinkedIn. Direct messages are the only
exception. If the exact person cannot be identified or selected, the agent exits
with `MENTION_UNRESOLVED` without publishing.

To reduce latency, an approval uses a limited path: it loads the item once,
opens the canonical URL directly in an authenticated session, locates the
context through DOM/accessibility, fills the text with native events, sends once,
and verifies the result. The agent does not report every click; it responds only
with the final result or with a single blocker that requires human action. There
is at most one primary strategy and one safe fallback.

Version 0.4.0 keeps a healthy Camoufox session open and reuses it between
monitoring and approvals, avoiding chained logins. It also applies an interval
between publications and a rolling 24-hour limit. The only automatic resend
allowed is for X `CreateTweet` error 344: the failure must be confirmed, the
reply must be absent from the page, and the ledger allows at most two new
attempts, with waits of 12 and 20 seconds by default.

In the X composer, text is inserted once with `insertText` after a real click
and after confirming that the field is empty; `fill`, `type`, and `insertText`
are not mixed. On LinkedIn, native typing remains the primary strategy and
`insertText` is only the safe fallback. In both cases, the full content is
compared with the stored draft before sending.

X thread pages can contain several tweets and several reply buttons. The agent
therefore binds the action to exactly one article containing the stored
`/status/<id>` link and only uses the reply control inside that article. It
never uses the first page-global reply button. A publication is only recorded
as successful after the agent captures the direct response URL and verifies
that its observed parent ID equals the stored source ID. A reply visible on the
profile but attached to another tweet is treated as a misrouted publication,
not as success, and is never deleted without separate owner approval. If later
evidence disproves a recorded success, the audited `correct-publication`
command moves it to `error` without erasing the original attempt or URL.

## Browser use, verification, and blocks

The agent uses Latch’s **Browser use** plugin: Camoufox on the Mac, the owner’s
local network, and a copy of the authenticated profile. Username, password, and
TOTP remain in the Browser Vault and are filled by `fill_secret` without
revealing the values.

CAPTCHA, human confirmation, and visible code fields follow the
`camoufox-browsing` skill. A hard block with no interactive target is not
reloaded: the agent tries the Safari fallback once. If Safari is not ready yet,
the owner opens **Latch → Plugins → Browser use** and clicks **Enable in
Safari**. Approvals that exist only on another device remain a human step,
preserving the session when possible.

Each operation has an action budget, one primary strategy, and only one safe
fallback. `429` (except the strictly confirmed X 344 error), persistent hard
block, unresolved mention, browser/MCP timeout, or unverifiable send ends the
attempt without another send click.

If a new Camoufox session appears logged out shortly after confirmed
authentication, the agent returns `SESSION_NOT_PERSISTED` and stops instead of
starting new logins. Cookie/profile synchronization is Latch’s responsibility;
the agent never exports cookies or tokens to try to work around the problem.

Check the ledger:

```sh
docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_state.py pending

docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_state.py show SM-000001

docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_state.py history SM-000001

docker compose exec -T social-media-agent \
  python3 /var/lib/hermes/scripts/social_state.py summary
```

## Security and limits

- Passwords, TOTP, cookies, and tokens do not enter the repository, SQLite, or
  notifications.
- Social media content is always treated as untrusted data and cannot authorize
  tools.
- Navigation is restricted to the configured X and LinkedIn domains.
- Complaints, crises, threats, privacy, account security, and regulated topics
  are classified as high risk.
- UI automation may need adjustments when X or LinkedIn change their web
  experience. The agent uses the browser’s accessible surface, not fixed CSS
  selectors, to reduce this fragility.
- Sending through Messages depends on local macOS permissions and on the
  configured handle being reachable by the Mac’s iMessage/SMS service.
- Respect platform terms, frequency limits, and privacy laws applicable to the
  operated account.

## Tests

Tests are local and do not access real accounts:

```sh
uv run --no-project --with pytest==8.4.2 pytest -q
```

They cover deduplication, approval transitions, URL validation, auditing,
auto-publish protection, safe AppleScript construction, Compose/Dockerfile
contracts, and shell script syntax.

## Operation

To stop only the monitor:

```sh
docker compose exec -T social-media-agent \
  hermes cron remove social-media-monitor
```

To update the image while preserving memory, sessions, and SQLite:

```sh
docker compose build
docker compose up -d --force-recreate
```

The image refreshes its agent-owned `SOUL.md` and `social-media-engagement`
skill on every boot. Persistent sessions, memory, SQLite state, local
configuration, and credentials are preserved; no manual skill reset is needed.

Do not use `docker compose down -v` in production: `-v` removes the ledger and
the agent’s memory. To retire the credential, use `plow-agents revoke`.
