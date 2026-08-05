#!/usr/bin/env bash
# Runs once when the Codespace/dev container is first created.
set -euo pipefail

echo "==> Upgrading pip and installing Python backend deps (requirements.txt)"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "==> Installing frontend deps (package.json)"
npm install

echo "==> Checking data files (backend returns HTTP 503 on every route if any are missing)"
if ls data/compounds.csv data/interactions.csv data/sources.csv data/risk_rules.yaml >/dev/null 2>&1; then
  echo "    data/ OK"
else
  echo "    WARNING: one or more data files missing under data/ — backend will 503 until present"
fi

cat <<'EOF'

============================================================
 supptracker Codespace ready.
   Backend :  uvicorn app:app --reload --port 8000
   Frontend:  npm run dev            # http://localhost:5174
   Tests   :  pytest -q
============================================================
EOF
