#!/usr/bin/env bash
# Foreground launcher: no model is called by these preflight checks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ROOT="${TURBO_APP_GM_HOME:-${REPO_ROOT}/build/app-gm}"
PYTHON_BIN="${TURBO_DISPATCH_PYTHON:-python3}"

"${PYTHON_BIN}" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
command -v gh >/dev/null
command -v codex >/dev/null
gh auth status --hostname github.com
gh api repos/michaelsena/turbo --jq '.full_name'
codex login status

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/app_dispatcher.py" run --execute \
  --repo michaelsena/turbo \
  --state-dir "${RUNTIME_ROOT}/state" \
  --workspace-root "${RUNTIME_ROOT}/workspaces" \
  "$@"
