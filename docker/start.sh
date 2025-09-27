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
