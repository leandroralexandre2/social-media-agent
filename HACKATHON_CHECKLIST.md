# Hackathon Demo Checklist

## Before the demo

```sh
./scripts/doctor.sh
docker compose up --build -d --force-recreate social-media-agent
docker compose exec -T social-media-agent \
  hermes skills reset social-media-engagement
docker compose up -d --force-recreate social-media-agent
docker compose ps
docker compose logs --tail=100 social-media-agent
```

Run the test suite:

```sh
uv run --no-project --with pytest==8.4.2 pytest -q
```

Do not use `docker compose down -v`; it deletes the persistent ledger and agent
memory.

## Recommended demo flow

1. Send one English or Portuguese mention from a test account.
2. Run one manual monitoring tick instead of waiting for the hourly schedule.
3. Show the exact-language draft and its `SM-xxxxxx` audit ID in Messages.
4. Send `APPROVE SM-xxxxxx`.
5. Show the concise final response, the direct social URL, and the matching
   parent/source ID in `LOGS SM-xxxxxx`.
6. Demonstrate `EDIT`, `IGNORE`, or a simulated failed attempt only if time
   permits.

## Expected safe failures

- `TARGET_NOT_UNIQUE`: the source post could not be uniquely bound; nothing was
  submitted.
- `MENTION_UNRESOLVED`: the intended public mention could not be created.
- `AUTH_CHALLENGE_LINKEDIN_MANUAL`: approve the device challenge and continue
  in the same browser session.
- `SESSION_NOT_PERSISTED`: stop the login chain and inspect Latch profile
  persistence.
- `BROWSER_USE_UNAVAILABLE`: enable the Latch Browser use plugin.
- `owner_retry_cooldown`: wait for the returned duration, then continue the
  same approved cycle; do not issue another submit click early.

## Residual platform risks

X and LinkedIn can change their UI, challenge an account, rate-limit actions,
or delay reply visibility. Those conditions cannot be eliminated by agent
code. This release handles them by failing closed, preserving the browser
session, bounding retries, and retaining an auditable ledger rather than
claiming success without evidence.
