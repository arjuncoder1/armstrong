#!/usr/bin/env bash
# One-time (and re-runnable) setup for Armstrong. Safe to run again: it never overwrites existing files.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# 1. portal-makermods is vendored in thirdparty/ (see thirdparty/VENDORED.md); edit it in place.
[[ -f thirdparty/portal-makermods/pyproject.toml ]] || { echo "thirdparty/portal-makermods is missing" >&2; exit 1; }

# 2. Python deps (root pyproject installs portal-makermods editable).
command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv sync

# 3. macOS: candleLight USB-CAN adapters need libusb.
if [[ "$(uname)" == Darwin ]] && command -v brew >/dev/null && ! brew list libusb >/dev/null 2>&1; then
  echo "note: candleLight adapters on macOS need libusb: brew install libusb"
fi

# 4. Env files (all git-ignored). Created only if missing; fill them in afterwards.
if [[ ! -f .env ]]; then
  cat > .env <<'EOF'
# Armstrong credentials only. Never commit (git-ignored).
# Non-secret settings live in .env.config.

# LiveKit Cloud project: `lk cloud auth`, then copy URL/key/secret from `lk project list`.
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Dream-1 (platform.dreamlabs.ai, API Keys).
# DREAM_API_KEY=
EOF
  echo "created .env: fill in the LiveKit credentials"
fi

if [[ ! -f .env.config ]]; then
  cat > .env.config <<'EOF'
# Armstrong configuration: non-secret settings. Credentials go in .env.
# Option docs: thirdparty/portal-makermods/.env.example and tutorial/09-reference.md.

LIVEKIT_ROOM=portal-makermods
MAKERMODS_MODEL=makers
METAL_MAX_STEP_RAD=0.02
PORTAL_HOTKEYS_GLOBAL=0

# One CAN adapter per arm. macOS candleLight: gs_usb:<serial> from `uv run main.py robot --list-adapters`.
# METAL_FOLLOWER_LEFT_CAN=
# METAL_FOLLOWER_RIGHT_CAN=

# Robot cameras: macOS indices (0, 1, 2) or Linux /dev/videoN.
# METAL_CAM_OVERHEAD=
# METAL_CAM_LEFT_WRIST=
# METAL_CAM_RIGHT_WRIST=

# LOG_LEVEL=INFO
EOF
  echo "created .env.config"
fi

# Secrets: readable by this user only.
for f in .env .env.local .env.config .env.ssh; do
  [[ -f "$f" ]] && chmod 600 "$f"
done

# 5. Helper scripts.
[[ -d tools ]] && chmod +x tools/*.sh

echo
echo "done. next:"
echo "  - fill in .env (LiveKit credentials) and .env.config (arms, cameras)"
echo "  - tools/ssh-configure.sh robot     # add the robot machine (password auth)"
echo "  - uv run main.py                   # voice agent, console mode"
