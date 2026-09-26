# OpenClaw 2.0 Hackathon Checklist

## Qualification

- [x] Real startup role: Social Engagement Lead
- [x] OpenClaw 2.0 base pinned by immutable tag and digest
- [x] Multiplayer groups and isolated direct sessions
- [x] Public MIT repository
- [x] Existing Agent Index ID: `social-media-agent`
- [x] Agent Index client inherited from the maintained Plow base
- [x] Local Compose workflow
- [ ] Public `linux/amd64` image pushed by digest
- [ ] Independent one-click cloud deployment validated
- [ ] New OpenClaw multiplayer demo recorded
- [ ] Repository, commit, digest, Index link, demo, and validation sent to Dane

## Release validation

```sh
python3 -m pytest -q
python3 -m compileall -q bin
./scripts/doctor.sh
docker compose build agent
```

Local smoke test:

```sh
plow-agents deploy --local --line <free-line>
docker compose ps
docker compose logs --tail=100 agent
```

Do not use `docker compose down -v`; it erases the persistent ledger, sessions,
configuration, and Agent Index install identity.

## Demo flow

1. Owner completes brand onboarding in their direct chat.
2. Owner starts a review room with two participants.
3. A teammate submits a public social URL or asks for a monitoring check.
4. The agent creates an `SM-xxxxxx` draft in the source language.
5. A teammate proposes an edit; the agent treats it as advisory.
6. The owner sends the final `APPROVE SM-xxxxxx`.
7. The agent publishes, verifies the direct URL and parent, and returns one
   concise success message.
8. Show `LOGS SM-xxxxxx` and the Agent Index usage page.

## Cloud release

```sh
plow-agents image build ghcr.io/leandroralexandre2/social-media-agent:v1.0.0
plow-agents image push ghcr.io/leandroralexandre2/social-media-agent:v1.0.0
plow-agents deploy ghcr.io/leandroralexandre2/social-media-agent@sha256:DIGEST \
  --line <free-line>
```
