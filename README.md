# supptracker

Supptracker is a minimal supplement–drug interaction checker. It consists of a FastAPI backend that serves CSV-driven interaction data and a Vite/React frontend for exploring compounds, checking pair-wise risks, and evaluating custom stacks.

## Frontend

The React frontend lives at the repository root inside `src/`. Development and build tooling are managed by the top-level `package.json`.

```bash
npm install
npm run dev      # start Vite on http://localhost:5173
npm run build    # generate the production bundle in dist/
npm run preview  # preview the production build
```

During development the Vite dev server proxies API calls to `http://localhost:8000`. When the backend runs elsewhere, set `VITE_API_BASE` in your environment (or an `.env` file) to the backend's base URL, e.g. `https://example.com/api`.

## Backend

1. Create a virtual environment and install dependencies:
   ```bash
   cd api
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
2. Ensure the `data/` directory contains the CSV and YAML inputs expected by the API:
   - `compounds.csv`
   - `interactions.csv`
   - `sources.csv`
   - `risk_rules.yaml`
3. Launch the FastAPI app with Uvicorn:
   ```bash
   uvicorn risk_api:app --reload --port 8000
   ```

The API is served from `http://127.0.0.1:8000/api/` with interactive docs available at `/docs`.

## Docker Compose

A Compose stack is available to run both services together:

```bash
docker compose build
docker compose up
```

The frontend is served by nginx on <http://localhost:5173> and proxies to the backend container at `http://backend:8000`.

## Contributing

This repo is an MVP scaffold. Feel free to open issues or pull requests to improve the dataset, enrich the risk model, refine the UI, or add automated tests.
