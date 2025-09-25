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
npm run preview
```

Set `VITE_API_BASE` in an `.env` file or your shell when the backend runs on a different host than the dev server.

## Backend (FastAPI)

1. Create a Python virtual environment inside the `api/` directory.
2. Install requirements and start the API.

```bash
cd api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn risk_api:app --reload --port 8000
```

The API exposes `/api/health`, `/api/search`, `/api/interaction`, and `/api/stack/check`. During development the Vite dev server proxies requests to `http://localhost:8000`.

## Data

Sample CSV/YAML data files live under `data/`:

- `compounds.csv`
- `interactions.csv`
- `sources.csv`
- `risk_rules.yaml`

Provide real data before starting the backend.

## Project structure

- `App.tsx`, `main.tsx`, `api.ts` – React application entry points.
- `api/` – FastAPI app, Pydantic models, and risk scoring logic.
- `backend/` – Docker assets for the backend service.
- `frontend/` – Docker assets for building and serving the frontend (includes the nginx health check script).
- `scripts/run-vite.js` – Wrapper used by the npm scripts to invoke Vite with the current environment.
- `tests/` – Backend test suite.

## Docker

An optional Docker Compose setup is provided:

```bash
docker compose build
docker compose up
```

The frontend is served by nginx on port `5173` and proxies to the backend service on port `8000` inside the Compose network.
