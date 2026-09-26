# Discord Verification Message

Replace the placeholders only after the cloud validation table in
`docs/VALIDATION.md` is complete.

```text
Social Media Agent — OpenClaw 2.0 hackathon update

The agent now runs on the current digest-pinned Plow OpenClaw base and keeps the
same Agent Index ID. It acts as a startup Social Engagement Lead: monitors X and
LinkedIn through Latch, deduplicates activity, drafts in the source language,
coordinates team review, and publishes only an exact owner-approved response.

Multiplayer is implemented with isolated OpenClaw direct/group sessions. The
owner can start a social review room; teammates, customers, and vendors can
submit public links, review drafts, propose wording, and flag risk. Only the
actual owner identity can approve a public publication.

Local and cloud workflows are validated: owner first contact, Latch browser
monitoring, non-owner approval rejection, owner publication with direct parent
verification, native recurring monitoring, and Agent Index usage reporting.

OpenClaw multiplayer demo:
DEMO_URL

Agent Index:
https://aiworthusing.com/agent-index/social-media-agent

MIT repository:
https://github.com/leandroralexandre2/social-media-agent

Validation:
https://github.com/leandroralexandre2/social-media-agent/blob/main/docs/VALIDATION.md

Commit:
COMMIT_SHA

Public linux/amd64 image:
ghcr.io/leandroralexandre2/social-media-agent@sha256:IMAGE_DIGEST

Could you verify the image for one-click deployment and let me know if any
additional admission evidence is needed?
```
