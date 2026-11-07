#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# portal-makermods is a plain clone (git-ignored), not a submodule.
PORTAL_DIR=thirdparty/portal-makermods
PORTAL_URL=https://github.com/livekit-examples/portal-makermods.git
PORTAL_BRANCH=dc/maker_arm
if [[ ! -d "$PORTAL_DIR/.git" ]]; then
  git clone --branch "$PORTAL_BRANCH" "$PORTAL_URL" "$PORTAL_DIR"
fi

uv sync

# Secrets live in .env (git-ignored); keep it readable by this user only.
[[ -f .env ]] && chmod 600 .env
