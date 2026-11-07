#!/usr/bin/env bash
# Forward the robot machine's Manifest API (port 8100 there) to http://127.0.0.1:8100/v1 here.
# Then: MANIFEST_URL=http://127.0.0.1:8100/v1 (shell or .env.config). Keep it running while you test.
#
#   tools/manifest-tunnel.sh                      # machine "robot", local port 8100
#   tools/manifest-tunnel.sh <machine> [local_port]
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$root/tools/ssh.sh" --tunnel "8100:${2:-8100}" "${1:-robot}"
