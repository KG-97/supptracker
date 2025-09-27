#!/bin/sh
set -euo pipefail

echo "Starting backend (uvicorn) in background and redirecting logs to /var/log/uvicorn.log"
uvicorn api.risk_api:app --host 127.0.0.1 --port 8000 > /var/log/uvicorn.log 2>&1 &
UVICORN_PID=$!

# Give the backend a few seconds to start, then try a single health probe.
sleep 3
echo "Probing backend health once (non-fatal)..."
python - <<'PY' || true
import sys
try:
    from urllib.request import urlopen
    r = urlopen('http://127.0.0.1:8000/api/health', timeout=2)
    code = getattr(r, 'getcode', lambda: r.status)()
    print('health status', code)
except Exception as e:
    print('health probe failed:', e)
    sys.exit(1)
PY

echo "Starting nginx in foreground"
nginx -g 'daemon off;'

#!/bin/sh
set -e

# Start backend
uvicorn api.risk_api:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!

# Start nginx in foreground
nginx -g 'daemon off;' &
NGINX_PID=$!

# wait on processes
wait $UVICORN_PID $NGINX_PID
