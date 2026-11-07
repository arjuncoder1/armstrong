#!/usr/bin/env bash
# Drive Manifest's arms with Portal's webcam hand teleop over LiveKit, from this laptop.
# The Halo runs the bridge (systemd user unit manifest-hands, room manifest-hands), which writes
# through Manifest's station lease, so Manifest stays up for everyone else.
# Keys, typed in this terminal: c takes or releases control, h then y homes (opens both grippers),
# x quits. Grip: curl middle, ring, pinky. Needs thirdparty/portal-makermods/.env (git-ignored) with
# LIVEKIT_URL=ws://localhost:7880, LIVEKIT_ROOM=manifest-hands and the Halo dev server's key and secret.
set -euo pipefail
cd "$(dirname "$0")/../thirdparty/portal-makermods"
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -L 7880:127.0.0.1:7880 pablo@10.103.1.11 &
tunnel=$!
trap 'kill $tunnel 2>/dev/null' EXIT
sleep 1
kill -0 $tunnel 2>/dev/null || { echo "LiveKit tunnel to the Halo failed (port 7880 busy here?)"; exit 1; }
PORTAL_HOTKEYS_GLOBAL=0 uv run --group hands hand-teleop --dashboard "$@"  # open the printed dashboard URL
