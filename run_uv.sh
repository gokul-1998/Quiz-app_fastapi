#!/usr/bin/env bash
set -euo pipefail

# Configurable via env vars
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"
WORKERS="${WORKERS:-1}"

# Ensure uvx (from uv) is available
command -v uvx >/dev/null 2>&1 || {
  echo "Error: 'uvx' (from 'uv') is not installed or not in PATH. Install from https://docs.astral.sh/uv/" >&2
  exit 1
}

# Run the app using uvx to fetch/run uvicorn on-the-fly
CMD=(uvx uvicorn main:app --host "${HOST}" --port "${PORT}")

if [[ "${RELOAD}" == "true" ]]; then
  CMD+=(--reload)
else
  CMD+=(--workers "${WORKERS}")
fi

exec "${CMD[@]}"
