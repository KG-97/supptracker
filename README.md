# supptracker

Supplement interactions

Run the frontend (Vite + React):

```bash
npm install
npm run dev
```

Build frontend:

```bash
npm run build
npm run preview
```

Run the backend (FastAPI):

1. Create a `data/` directory with the CSV/YAML data files the backend expects:
	- `compounds.csv`
	- `interactions.csv`
	- `sources.csv`
	- `risk_rules.yaml`

2. Install Python requirements and run Uvicorn:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.risk_api:app --reload --port 8000
```

During development the Vite dev server proxies API requests to `http://localhost:8000`.

Notes:
- If you run the frontend and backend on different hosts, set `VITE_API_BASE` in an `.env` or in your environment.
- The `data/` folder is intentionally not included; add real data files before starting the backend.

Docker (optional)

Build and run both services with Docker Compose:

```bash
docker compose build
docker compose up
```

The frontend will be available at http://localhost:5173 (served by nginx) and proxies to the backend at http://backend:8000 inside the compose network.
# supptracker
Supplement interactions


# supptracker

This project provides a minimal supplement–drug interaction checker. It consists of a FastAPI backend and a Vite/React frontend.

## Project structure

- `api/` – FastAPI application with endpoints to search compounds and compute interaction risk.
- `api/models.py` – Pydantic models for Compound and Interaction entities.
- `api/risk_api.py` – API entry point (FastAPI) with endpoints (`/api/health`, `/api/search`, `/api/interaction`, `/api/stack/check`).
- `api/rules.yaml` – Risk scoring configuration (mechanism deltas, weights, severity/evidence mappings).
- `data/` – CSV seed data:
  - `compounds.csv` – list of compounds and typical doses.
  - `interactions.csv` – known interactions between pairs of compounds and their severity/action.
  - `sources.csv` – references for interactions.
- `web/` – (to be added) minimal React frontend to search compounds and view interactions.

## Getting started

### Backend

1. Navigate to the `api` directory and create a virtual environment:
   ```bash
   cd api
   python -m venv .venv
   source .venv/bin/activate  # on Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Run the development server:
   ```bash
    uvicorn risk_api:app --reload
   ```
   The API will be available at `http://127.0.0.1:8000/api/`. The interactive docs are at `/docs`.

### Frontend (optional)

The frontend scaffold will live under the `web` directory. To run it:

```bash
cd web
npm install
npm run dev
```

### Data

The CSV files in `data/` provide a starting dataset. You can modify or extend them and reload the API to reflect changes.

### Contributing

This is an MVP scaffold. Feel free to open issues or pull requests to add features such as:

- Parsing the CSVs and serving them via the API.
- Computing risk scores based on the rules in `rules.yaml`.
- A React UI for selecting compounds, viewing interactions, and inspecting sources.
- Tests for the API and risk engine.
