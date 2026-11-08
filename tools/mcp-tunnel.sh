#!/usr/bin/env bash
# Forward the robot machine's Manifest MCP server (port 8765 there, localhost only) to http://127.0.0.1:8765/mcp here,
# for a voice agent worker on this machine. Keep it running.
#
#   on the robot:  uv run main.py mcp                 # MANIFEST_URL=http://127.0.0.1:8100/v1 there
#   here:          tools/mcp-tunnel.sh                # machine "robot", local port 8765
#                  uv run main.py manifest-voice dev
#   tools/mcp-tunnel.sh <machine> [local_port]
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$root/tools/ssh.sh" --tunnel "8765:${2:-8765}" "${1:-robot}"
