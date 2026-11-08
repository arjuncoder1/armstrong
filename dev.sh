#!/usr/bin/env bash
# Start everything for local development, all on this Mac:
#   - main.py stack: local LiveKit dev server (ws://127.0.0.1:7880), the Manifest robot bridge (room armstrong-local),
#     the token endpoint (http://127.0.0.1:8787/token) and, with --dream, the Dream-1 node
#   - frontend: Nuxt dev server at http://localhost:3000
# Ctrl-C stops all of it.
#
#   ./dev.sh             everything
#   ./dev.sh --no-dream  without the Dream-1 node
#   ./dev.sh --no-ui     without the frontend
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

DREAM=--dream
UI=1
for arg in "$@"; do
  case "$arg" in
    --no-dream) DREAM= ;;
    --no-ui) UI=0 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
command -v livekit-server >/dev/null || { echo "livekit-server is required: brew install livekit" >&2; exit 1; }
[[ $UI == 0 ]] || command -v bun >/dev/null || { echo "bun is required for the frontend (or use --no-ui)" >&2; exit 1; }

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "stopping..."
  for pid in "${pids[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
  sleep 2
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "== stack: LiveKit (local), Manifest bridge, token endpoint${DREAM:+, Dream-1 node}"
uv run main.py stack $DREAM &
pids+=($!)

if [[ $UI == 1 ]]; then
  [[ -d frontend/node_modules ]] || (cd frontend && bun install)
  echo "== frontend: http://localhost:3000"
  (cd frontend && exec bun --bun run dev) &
  pids+=($!)
fi

echo "== running. Open http://localhost:3000  (Ctrl-C to stop everything)"
# Portable "wait for the first to exit" (macOS /bin/bash 3.2 has no wait -n).
while :; do
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || { echo "a process exited; shutting the rest down"; exit 0; }
  done
  sleep 1
done
