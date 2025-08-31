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
uvicorn app:app --reload --port 8000
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
