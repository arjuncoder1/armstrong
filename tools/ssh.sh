#!/usr/bin/env bash
# SSH into a machine from .env.ssh with its password. Password auth only; keys are never used.
#
#   tools/ssh.sh <name>              # interactive shell
#   tools/ssh.sh <name> <command...> # run a command
#   tools/ssh.sh --list              # configured names
#
# Add machines with tools/ssh-configure.sh. No sshpass: the password goes to ssh through
# SSH_ASKPASS (this same script), so it never appears in argv or the process list.
set -euo pipefail

# Called back by ssh as its askpass program: print the password and nothing else.
if [[ "${ARMSTRONG_SSH_ASKPASS:-}" == 1 ]]; then
  printf '%s\n' "$ARMSTRONG_SSH_PASSWORD"
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
file="$root/.env.ssh"
self="$root/tools/ssh.sh"

get() { [[ -f "$file" ]] && grep -m1 "^$1=" "$file" | cut -d= -f2- || true; }

if [[ $# -eq 0 ]]; then
  echo "usage: tools/ssh.sh <name> [command...] | --list" >&2
  exit 2
fi

if [[ "$1" == "--list" ]]; then
  [[ -f "$file" ]] && grep -oE '^SSH_[A-Z0-9_]+_HOST=' "$file" | sed -E 's/^SSH_(.*)_HOST=$/\1/' | tr 'A-Z_' 'a-z-'
  exit 0
fi

key="SSH_$(printf '%s' "$1" | tr 'a-z-' 'A-Z_' | tr -c 'A-Z0-9_' '_')"
shift
host="$(get "${key}_HOST")"
port="$(get "${key}_PORT")"
password="$(get "${key}_PASSWORD")"
if [[ -z "$host" ]]; then
  echo "tools/ssh.sh: no ${key}_HOST in .env.ssh; run tools/ssh-configure.sh" >&2
  exit 1
fi

export ARMSTRONG_SSH_ASKPASS=1 ARMSTRONG_SSH_PASSWORD="$password"
export SSH_ASKPASS="$self" SSH_ASKPASS_REQUIRE=force

exec ssh \
  -p "${port:-22}" \
  -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o NumberOfPasswordPrompts=1 \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 \
  "$host" "$@"
