# supptracker

Supplement interaction tracking for launch night. The project pairs a FastAPI backend (risk scoring + search) with a polished React/Vite frontend that lets you:

- search for compounds by name or synonym
- inspect the risk profile for a specific pair
- paste a stack of supplements and review all risky combinations at once

The repository includes a small reference dataset under `data/` so the app can boot out of the box. Swap in your own CSV/YAML files before going live.

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

## Frontend (React + Vite)

From the repository root:

```bash
npm install
npm run dev     # Vite dev server with API proxying
npm run build   # Production build in dist/
npm run preview # Preview the production bundle locally
```

Configuration:

- `VITE_API_BASE` – optional. When unset the frontend automatically talks to `/api` on the same origin in production builds and `http://localhost:8000/api` when running on `localhost:5173`.

The refreshed UI (see `App.tsx`/`App.css`) includes accessible forms, clear loading/error states, severity badges, and a modern responsive layout suitable for a same-day launch.

## Docker / deployment

Two Dockerfiles (`backend/` and `frontend/`) are provided plus a `docker-compose.yml` for local orchestration:

```bash
docker compose build
docker compose up
```

Notable updates:

- The backend image now copies the `data/` directory so the API boots with seed content even without a bind mount.
- The frontend nginx image waits for the backend health endpoint before serving traffic.

Access the UI at http://localhost:5173 (nginx) and the API at http://localhost:8000.

## Project structure

```
api/              FastAPI application, risk engine, rule loader
backend/          Backend Dockerfile
frontend/         Frontend Dockerfile and helper scripts
scripts/          Vite wrapper used by npm scripts
data/             Seed CSV/YAML files (replace with production data)
App.tsx, App.css  React entrypoint with launch-ready UI
api.ts, types.ts  Typed frontend API client + shared types
```

## Launch checklist

The quick list for confirming you are production-ready is below. For the detailed launch-night runbook (with commands, manual QA
flows, and deployment steps) see [`LAUNCH_PLAN.md`](./LAUNCH_PLAN.md).

- [x] Backend boots successfully with bundled data (`uvicorn api.risk_api:app`).
- [x] Frontend renders search, pair, and stack flows with helpful error states.
- [x] Docker images include the required dataset.
- [x] `pytest` passes locally.

## Contributing / next steps

- Expand the dataset before launch night and verify citations.
- Expose authentication/roles if you need editing controls.
- Tighten TypeScript strictness and extract more reusable components as the UI grows.
