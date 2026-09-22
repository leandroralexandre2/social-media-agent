#!/usr/bin/env bash
set -euo pipefail

home="${HERMES_HOME:-/var/lib/hermes}"
owner="$(id -u hermes)"
group="$(id -g hermes)"

link_payload() {
  local target="$1" link="$home/$2"
  if [ -d "$link" ] && [ ! -L "$link" ] && [ -z "$(ls -A "$link")" ]; then
    rmdir "$link"
  fi
  ln -sfnT "$target" "$link"
}

# Hermes cron resolves scripts only inside $HERMES_HOME/scripts. Linking the
# whole directory lets both the scripts root and candidate resolve to the same
# root-owned image path.
link_payload /opt/plow/social/bin scripts

# A named volume retains old files, so reinstall the image-owned runtime config
# on every boot. plow-init then safely applies its own injected keys.
install -o "$owner" -g "$group" -m 0640 -t "$home" \
  /opt/plow/social/home/config.yaml

# The Hermes home is persistent. Generic skill synchronization preserves
# user-modified files, which can leave an old SOUL or skill active after an
# image upgrade. Refresh only the behavior files owned by this agent release.
install -o "$owner" -g "$group" -m 0640 \
  /opt/hermes/plow-seed/persona.md "$home/SOUL.md"

skill="$home/skills/social-media-engagement"
install -d -o "$owner" -g "$group" -m 0750 "$skill/references"
install -o "$owner" -g "$group" -m 0640 \
  /opt/hermes/skills/productivity/social-media-engagement/SKILL.md \
  "$skill/SKILL.md"
install -o "$owner" -g "$group" -m 0640 \
  /opt/hermes/skills/productivity/social-media-engagement/references/commands.md \
  "$skill/references/commands.md"

mkdir -p "$home/state"
chown "$owner:$group" "$home/state"
chmod 0700 "$home/state"
