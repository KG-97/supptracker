#!/bin/sh
# wait-for-health.sh - wait until backend /api/health returns 200
# usage: wait-for-health.sh <host> <port> [path] [timeout_seconds]

HOST=${1:-backend}
PORT=${2:-8000}
PATH_CHECK=${3:-/api/health}
TIMEOUT=${4:-30}

URL="http://$HOST:$PORT$PATH_CHECK"
echo "Waiting for $URL (timeout ${TIMEOUT}s)"
start=$(date +%s)
while true; do
  if wget -q -O - "$URL" >/dev/null 2>&1; then
    echo "Service healthy: $URL"
    exit 0
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "$TIMEOUT" ]; then
    echo "Timeout waiting for $URL" >&2
    exit 1
  fi
  sleep 1
done
