# Same Plow/Hermes base contract used by str-hermes-agent-main. The digest keeps
# the runtime reproducible; update tag and index digest together.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-80ef5024eb4b770e727a618a9b55421c73da6228@sha256:864771e8165db16c11a55635df85696f39d91020f258576dd62b7cab0515514f

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

