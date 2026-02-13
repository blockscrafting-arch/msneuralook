#!/bin/sh
# Check that all parser services are running. Exit 0 if ok, 1 otherwise.
# Run from project root. Use in cron for simple monitoring.

cd "$(dirname "$0")/.."
out=$(docker compose ps -a 2>/dev/null) || { echo "docker compose failed" >&2; exit 1; }
if echo "$out" | grep -qE 'Exited|Restarting'; then
  echo "One or more parser containers are not running." >&2
  echo "$out" >&2
  exit 1
fi
exit 0
