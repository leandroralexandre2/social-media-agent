# State commands

All JSON commands accept `--json -` and read one object from standard input.

```sh
python3 "$HERMES_HOME/scripts/social_state.py" ingest --json -
python3 "$HERMES_HOME/scripts/social_state.py" set-draft SM-000001 --json -
python3 "$HERMES_HOME/scripts/social_state.py" show SM-000001
python3 "$HERMES_HOME/scripts/social_state.py" history SM-000001
python3 "$HERMES_HOME/scripts/social_state.py" pending
python3 "$HERMES_HOME/scripts/social_state.py" cursor x
python3 "$HERMES_HOME/scripts/social_state.py" cursor linkedin
python3 "$HERMES_HOME/scripts/social_state.py" mark SM-000001 notified
python3 "$HERMES_HOME/scripts/social_state.py" mark SM-000001 approved
python3 "$HERMES_HOME/scripts/social_state.py" publication-gate SM-000001
python3 "$HERMES_HOME/scripts/social_state.py" record-attempt SM-000001 rate_limited --error-code 344 --detail "CreateTweet returned code 344; reply absent"
python3 "$HERMES_HOME/scripts/social_state.py" correct-publication SM-000001 --detail "later verification found the wrong parent"
python3 "$HERMES_HOME/scripts/social_state.py" mark SM-000001 published \
  --published-text "exact text" \
  --published-url "https://x.com/brand/status/222" \
  --parent-external-id "111"
python3 "$HERMES_HOME/scripts/social_state.py" mark SM-000001 ignored
python3 "$HERMES_HOME/scripts/social_state.py" mark SM-000001 error --detail "what failed"
```

An ingest object requires `platform`, `external_id`, `url`, `author`, `content`
and should include `interaction_type`, `sentiment`, `priority`, `detected_at`.

A draft object requires `drafts` (one to three strings) and may include
`recommended_index`, `rationale`, and `risk`.

Run `publication-gate` after marking a draft approved and before opening its
composer. Use the exact approved text and target locator it returns. It enforces
the per-platform publication interval, rolling 24-hour cap, owner-retry
cooldown, and bounded X error 344 backoff. `record-attempt` is only for a submit
that did not produce a verified publication. A verified public success is
recorded atomically by `mark ... published` and requires the direct result URL
plus the observed parent/source external ID. After an `error`, a trusted owner
`RETRY SM-xxxxxx` is represented by marking the item `approved` again; this
increments its approval cycle without erasing prior attempts.
If later evidence disproves a recorded success, use `correct-publication`
rather than editing SQLite. It changes the current state to `error` while
preserving the published URL, success attempt, and correction event for audit.

To notify, pipe an object with `draft_id`, `platform`, `author`, `category`,
`url`, and `suggested_reply` to:

```sh
python3 "$HERMES_HOME/scripts/messages_notify.py" --json -
```
