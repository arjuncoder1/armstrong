#!/usr/bin/env bash
# Add or update a machine in .env.ssh for tools/ssh.sh. Password auth only.
#
#   tools/ssh-configure.sh            # prompts for everything
#   tools/ssh-configure.sh arm        # prompts for arm's details
#
# .env.ssh is git-ignored and kept at mode 600: it holds passwords.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
file="$root/.env.ssh"

name="${1:-}"
[[ -z "$name" ]] && read -rp "Machine name (e.g. arm, deploy): " name
[[ -z "$name" ]] && { echo "a name is required" >&2; exit 1; }
key="SSH_$(printf '%s' "$name" | tr 'a-z-' 'A-Z_' | tr -c 'A-Z0-9_' '_')"

read -rp "user@host: " host
[[ "$host" == *@* ]] || { echo "expected user@host" >&2; exit 1; }
read -rp "Port [22]: " port
read -rsp "Password: " password
echo

# Rewrite .env.ssh without this machine's old lines, then append the new ones.
touch "$file"
chmod 600 "$file"
tmp="$(mktemp "$file.XXXXXX")"
grep -vE "^${key}_(HOST|PORT|PASSWORD)=" "$file" > "$tmp" || true
{
  printf '%s_HOST=%s\n' "$key" "$host"
  printf '%s_PORT=%s\n' "$key" "${port:-22}"
  printf '%s_PASSWORD=%s\n' "$key" "$password"
} >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$file"
echo "saved $name to .env.ssh"

echo "testing connection..."
if "$root/tools/ssh.sh" "$name" true; then
  echo "ok: tools/ssh.sh $name works"
else
  echo "connection failed: check host, port, and password (rerun tools/ssh-configure.sh $name)" >&2
  exit 1
fi
