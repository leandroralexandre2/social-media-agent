# Same Plow/Hermes base contract used by str-hermes-agent-main. The digest keeps
# the runtime reproducible; update tag and index digest together.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-67021a7029e33e80bcb27899be6515a5a0e9b37b@sha256:0c3892e93c1a001c61fb7106396e0a4b7e0219008184fd90719caa84a3390ff0

# A cloud install runs this image without compose.yml, so the AGENT_ID set
# there never reaches it and the base's reporter stands down. Kept here too,
# which is the only place both paths read.
ENV AGENT_ID=social-media-agent

COPY runtime/persona.md /opt/hermes/plow-seed/persona.md
RUN chmod 0644 /opt/hermes/plow-seed/persona.md

COPY runtime/config.yaml /opt/plow/social/home/config.yaml
COPY runtime/social-media.toml.example /opt/plow/social/home/social-media.toml.example
RUN install -m 0644 -t /var/lib/hermes/ /opt/plow/social/home/config.yaml

COPY agent-skills/productivity/social-media-engagement/ /opt/hermes/skills/productivity/social-media-engagement/
RUN chmod -R a=rX,u+w /opt/hermes/skills/productivity/social-media-engagement

COPY bin/ /opt/plow/social/bin/
RUN chown -R root:root /opt/plow/social \
 && find /opt/plow/social -type d -exec chmod 0755 {} + \
 && find /opt/plow/social -type f -exec chmod 0644 {} + \
 && find /opt/plow/social/bin -type f -exec chmod 0755 {} +

COPY docker/cont-init.d/05-install-agent-payload.sh /etc/cont-init.d/05-install-agent-payload.sh
RUN chmod 0755 /etc/cont-init.d/05-install-agent-payload.sh

ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2

