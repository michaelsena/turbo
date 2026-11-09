#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TURBO_PYTHON="${TURBO_PYTHON:-${ROOT_DIR}/.venv/bin/python}"
TURBO_PORT="${TURBO_PORT:-8017}"

if [[ ! "$TURBO_PORT" =~ ^[0-9]+$ ]] || (( 10#$TURBO_PORT < 1024 || 10#$TURBO_PORT > 65535 )); then
  echo "TURBO_PORT must be an integer from 1024 through 65535." >&2
  exit 2
fi
if [[ ! -x "$TURBO_PYTHON" ]]; then
  echo "Install the documented Python environment or set TURBO_PYTHON to its interpreter." >&2
  exit 2
fi
if [[ ! -f "$ROOT_DIR/frontend/dist/index.html" ]]; then
  echo "Build the dashboard first: cd frontend && npm ci && npm run build" >&2
  exit 2
fi
cd "$ROOT_DIR"
echo "Turbo local dashboard: http://127.0.0.1:$TURBO_PORT (Ctrl-C to stop)"
exec env PYTHONPATH=src "$TURBO_PYTHON" -m uvicorn turbo.web.app:app --host 127.0.0.1 --port "$TURBO_PORT"
