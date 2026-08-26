#!/usr/bin/env sh
set -eu

cleanup() {
  if [ -n "${server_pid:-}" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "Starting SwiftAgent API on http://127.0.0.1:8000"
(
  cd server
  SWIFTAGENT_DEV=1 SWIFTAGENT_NO_BROWSER=1 .venv/bin/python -m swiftagent.main
) &
server_pid=$!

echo "Starting SwiftAgent web app on http://127.0.0.1:5173"
cd client
npm run dev
