#!/bin/sh
set -eu

echo "Starting uvicorn (backend) in background..."
# Start uvicorn on loopback; nginx will proxy to 127.0.0.1:8000
uvicorn api.risk_api:app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

echo "Waiting for backend to become healthy (up to 30s)..."
MAX_TRIES=30
TRY=0
HEALTH_OK=0
while [ $TRY -lt $MAX_TRIES ]; do
    # Use Python's stdlib to avoid depending on curl/wget in the image
    if python - <<'PY'
import sys
from urllib.request import urlopen
try:
        r = urlopen('http://127.0.0.1:8000/api/health', timeout=2)
        code = getattr(r, 'getcode', lambda: r.status)()
        sys.exit(0 if code == 200 else 1)
except Exception:
        sys.exit(1)
PY
    then
        echo "Backend healthy"
        HEALTH_OK=1
        break
    fi
    TRY=$((TRY + 1))
    sleep 1
done

if [ $HEALTH_OK -ne 1 ]; then
    echo "Warning: backend did not report healthy after ${MAX_TRIES}s, continuing to start nginx for debugging and static serving."
fi

echo "Starting nginx in foreground..."
nginx -g 'daemon off;'

