#!/usr/bin/env bash
set -euo pipefail
echo "[bootstrap] installing deps (best effort)"
pip install -r requirements.txt || true
pip install pandas pyyaml pytest pre-commit || true

echo "[bootstrap] migrating schema (optional)"
python tools/migrate_compounds_schema.py || true

echo "[bootstrap] compiling datasets"
python tools/compile_compounds.py
python tools/compile_interactions.py || true

echo "[bootstrap] validating datasets"
python tools/validate_compounds.py
python tools/validate_interactions.py || true

echo "[bootstrap] running tests"
pytest -q

echo "[bootstrap] done — ready to commit & push"
