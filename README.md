# supptracker

A minimal supplement interaction tracker consisting of a FastAPI backend and a Vite/React frontend.

## Frontend (Vite + React)

The frontend lives at the repository root and is built with Vite.

### Development

```bash
npm install
npm run dev
```

### Production build

```bash
npm run build
```

## Backend (FastAPI)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.risk_api:app --reload --host 0.0.0.0 --port 8000
```

Key environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `SUPPTRACKER_DATA_DIR` | Override the folder that contains `compounds.csv`, `interactions.csv`, `sources.csv`, and `risk_rules.yaml`. | `<repo>/data` |
| `RISK_RULES_PATH` | Alternative path to the YAML rule set used for risk scoring. | `api/rules.yaml` |

The backend now loads data safely even if the files are missing, logging a warning instead of crashing. This makes container starts resilient while still allowing you to provide real data before launch.

Run tests with:

```bash
pytest
```