# Walkthrough: Comprehensive Supplement/Medication App Upgrade

This document captures the implementation plan and verification notes for upgrading the Supplement Tracker from a CSV-based MVP to a database-driven application with mechanism-based interaction detection.

## Environment warning

The prior execution environment used a Python 3.14 pre-release toolchain, which can break key dependencies (for example `pydantic-core` and `fastapi`). `npm` was also unavailable in that environment.

**Recommended local setup:**
- Python 3.11 or 3.12
- Node.js (current LTS)
- `npm`

## Features implemented in the upgrade plan

### 1) Mechanism-based inference engine

Interaction detection was redesigned to deduce interactions by mechanism, instead of only relying on hardcoded compound pairs:

- **Pharmacokinetic (PK):** detect when one compound inhibits an enzyme (e.g., CYP3A4) that metabolizes another compound.
- **Pharmacodynamic (PD):** detect when two compounds share a mechanism (for example both increasing serotonin).

### 2) Database migration (SQLite)

Planned schema additions:
- `compounds`
- `mechanisms`
- `interaction_overrides`

A database seed script was planned to migrate existing CSV data and add mechanism records for test scenarios.

### 3) Dashboard-first frontend

Planned UI improvements:
- Stack Builder for adding/removing compounds dynamically.
- Real-time interaction reporting cards showing severity, evidence grade, and mechanism details.

## Verification steps (on a compatible environment)

### Backend

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Install any additional backend dependencies required by your implementation
# Example: sqlalchemy alembic pydantic-settings
# Run seed/migration script if present
# Start API server
uvicorn main:app --reload
```

Health check example:

```bash
curl http://127.0.0.1:8000/api/health
```

### Frontend

```bash
npm install
npm run dev
```

Then open the local dev URL printed by Vite (commonly `http://127.0.0.1:5173`).

## Suggested interaction smoke test

1. Add a CYP3A4 inhibitor compound to the stack.
2. Add a CYP3A4 substrate compound to the stack.
3. Confirm a severe/major interaction appears with mechanism details.

## Notes

If startup fails, first confirm interpreter and package manager versions (`python --version`, `node --version`, `npm --version`) and then reinstall dependencies in a fresh virtual environment.
