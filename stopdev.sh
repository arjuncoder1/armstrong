#!/usr/bin/env bash
# Stop everything ./dev.sh started (also handy if a dev.sh terminal was closed without Ctrl-C):
# the frontend dev server, main.py stack / dream, the Manifest robot bridge, the token endpoint, and the local
# LiveKit dev server. Asks politely first (SIGINT, so the bridge releases any arm lease), then forces after 6 s.
#
#   ./stopdev.sh           stop all of it
#   ./stopdev.sh --dry-run list what would be stopped
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
ROOT="$(pwd)"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

# Our processes only: matched on this repo's commands, never other users' or other projects' servers.
PATTERNS=(
  "main.py stack"
  "main.py dream"
  "manifest_bridge"
  "policies/dream_1_tasks"
  "$ROOT/frontend/node_modules/.bin/nuxt"
  "nuxt dev"
  "livekit-server --dev"
  "livekit-server --config .*/livekit\\.yaml"
)

pids=()
for pattern in "${PATTERNS[@]}"; do
  while read -r pid; do
    [[ -n "$pid" && "$pid" != "$$" ]] && pids+=("$pid")
  done < <(pgrep -f -- "$pattern" 2>/dev/null)
done
# Frontend dev servers started from this repo's frontend/ folder (bun/node with cwd there).
while read -r pid; do
  [[ "$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')" == "$ROOT/frontend"* ]] && pids+=("$pid")
done < <(pgrep -x bun 2>/dev/null; pgrep -x node 2>/dev/null)

if [[ ${#pids[@]} -eq 0 ]]; then
  echo "nothing running"
  exit 0
fi
pids=($(printf '%s\n' "${pids[@]}" | sort -un))

echo "stopping:"
for pid in "${pids[@]}"; do
  printf '  %-7s %s\n' "$pid" "$(ps -o command= -p "$pid" 2>/dev/null | cut -c1-110)"
done
[[ $DRY == 1 ]] && exit 0

kill -INT "${pids[@]}" 2>/dev/null
for _ in $(seq 12); do
  alive=()
  for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive+=("$pid"); done
  [[ ${#alive[@]} -eq 0 ]] && { echo "all stopped"; exit 0; }
  sleep 0.5
done
echo "forcing: ${alive[*]}"
kill -TERM "${alive[@]}" 2>/dev/null
sleep 1
for pid in "${alive[@]}"; do kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null; done
echo "all stopped"
