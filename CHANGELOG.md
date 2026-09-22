# Changelog

## 0.4.1

- Make the owner conversation English-only and suppress browser, DOM, tool,
  selector, coordinate, ledger, and internal-plan narration.
- Add compact `✅`, `⚠️`, and `❌` result templates, with technical details
  available only through `LOGS <id>`.
- Accept clear `RESPONSE/REPLY <id>` requests without lecturing the owner about
  command syntax; canonical `APPROVE <id>` remains required for publication.
- Prevent ignore recommendations and diagnostic placeholders from being stored
  as publishable drafts.
- Refresh this agent's `SOUL.md` and social-media skill on every container boot
  so persistent Hermes volumes cannot keep stale behavior rules.
- Diagnose the common `runtime/social-media.toml` directory/file mistake with a
  direct recovery command.

## 0.4.0

- Bind X replies to the exact article containing the stored `/status/<id>`;
  page-global first-match reply selectors are forbidden.
- Require a direct result URL and verified parent/source ID before the ledger
  accepts a public reply as published.
- Add audited approval cycles, bounded owner retries, and retry cooldowns so a
  generic failure can be retried without erasing earlier attempts or looping.
- Add `correct-publication` for false-positive or misrouted publication records
  while preserving their original audit trail.
- Freeze URL, author, and source content after drafting so later duplicate
  scans cannot redirect an approved response.
- Keep notification text exact; oversized drafts now fail validation instead
  of showing a truncated preview and publishing hidden text.
- Add secret redaction to incident details and the `LOGS <id>` workflow.
- Add `scripts/doctor.sh` for deployment preflight checks.
- Make monitor installation idempotent and change the fresh-install polling
  default from five minutes to one hour to reduce overlap and platform pressure.
- Publish the repository README in English.

## 0.3.2

- Match each suggested social reply to the source interaction language while
  keeping owner-facing commands and status messages in English.

## 0.3.1

- Reuse authenticated Browser use sessions.
- Add bounded X error 344 retries, publication spacing, and rolling limits.
- Use safe contenteditable insertion and require public mentions.
