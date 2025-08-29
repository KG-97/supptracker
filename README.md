# supptracker
Supplement interactions


# supptracker

This project provides a minimal supplement–drug interaction checker. It consists of a FastAPI backend and a Vite/React frontend.

## Project structure

- `api/` – FastAPI application with endpoints to search compounds and compute interaction risk.
- `api/models.py` – Pydantic models for Compound and Interaction entities.
- `api/main.py` – API entry point (FastAPI) with sample endpoints (`/api/health`, `/api/search`, `/api/interaction`, `/api/stack/check`).
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
   uvicorn main:app --reload
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
