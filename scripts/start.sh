#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
    printf 'Run bash scripts/setup.sh first.\n' >&2
    exit 1
fi
# One backend worker owns the solver queue. No reload while runs are active.
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
(cd frontend && exec node_modules/.bin/vite --host 127.0.0.1 --strictPort) &
frontend_pid=$!
cleanup() {
    kill -TERM "$backend_pid" "$frontend_pid" 2>/dev/null || true
    wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
printf '\nOpen http://localhost:5173 in your Windows browser. Ctrl+C stops both services.\n'
wait -n "$backend_pid" "$frontend_pid"
