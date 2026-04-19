# Supptracker – Supplement Interaction Tracker

Supptracker is a simple full‑stack application for evaluating potential interactions between nutritional supplements.  It consists of a FastAPI backend that exposes REST endpoints for search and scoring, and a lightweight React frontend built with Vite.  The project is intended as a starting point for supplement interaction tools and includes tests and CI configuration.

## Running the Frontend

The frontend uses Vite and React.  During development the dev server proxies API requests to `http://localhost:8000` so you can run the frontend and backend locally without additional configuration.

To get started install dependencies and launch the dev server:

    npm install
    npm run dev

To build a production bundle into `dist/` and preview it locally run:

    npm run build
    npm run preview

If you run the frontend and backend on different hosts, set the `VITE_API_BASE` environment variable (for example in an `.env` file) to point at your backend base URL.

## Running the Backend

The backend is implemented with FastAPI and reads its data from CSV and YAML files.  At startup the API loads four files:

* **`compounds.csv`** – basic metadata for each supplement (id, name and synonyms)
* **`interactions.csv`** – pairwise interaction records including severity and evidence grade
* **`sources.csv`** – metadata about the references used for interactions (id, title, citation, etc.)
* **`risk_rules.yaml`** – configuration controlling scoring weights and risk buckets

You can place these files in a `data/` directory relative to `app.py` (the default) or set an environment variable `SUPPTRACKER_DATA_DIR` to point at another directory.  The backend will fail to start if any of the files are missing.

To run the backend locally using your system Python:

    # install dependencies (FastAPI, Uvicorn, pandas, pyyaml)
    python -m pip install fastapi uvicorn pandas pyyaml

    # start the server on http://localhost:8000
    uvicorn app:app --reload --port 8000

## API Endpoints

The backend exposes three primary endpoints.  All endpoints return JSON and are fully documented via the OpenAPI schema exposed at `/docs`.

| Method | Path | Description |
|-------|------|-------------|
| `GET` | `/api/health` | Health check returning the service name and version. |
| `GET` | `/api/search?q=...` | Search for compounds by id, name or synonym.  Returns up to 20 matches. |
| `GET` | `/api/interaction?a=...&b=...` | Compute the interaction between two compounds, returning severity, evidence grade, score, risk bucket and recommended action along with source metadata. |
| `POST` | `/api/stack/check` | Given a JSON payload like `{ "items": ["caffeine", "aspirin", ...] }`, return an `items` array, a square `matrix` of scores and a flat list of `cells` describing the non‑empty pairs. |

The API uses Pydantic models for strict request and response validation and thus provides accurate OpenAPI documentation.  See `models.py` for the full schema definitions.

## Docker

You can also run both the frontend and backend via Docker Compose.  This is useful for local development or deploying the application in a container environment.

To build the images and start the containers run:

    docker compose build
    docker compose up

The frontend will be served at `http://localhost:5173` (via nginx) and proxies API calls to the backend container.  The backend listens on `http://localhost:8000`.  The `data/` directory will be mounted read‑only into the backend container; ensure your CSV and YAML files exist there before starting the services.

## Running Tests

The repository includes a small test suite for the backend using `pytest`.  To run the tests you need the Python dependencies installed as shown above, and you should ensure the test data is present.  The tests automatically populate a temporary `data/` folder with stub data via `tests/conftest.py`.

To run the tests:

    python -m pip install pytest
    pytest -q

## Contributing

Contributions are welcome!  Please open an issue or pull request on GitHub.  When submitting changes, ensure that the existing tests pass and add new tests as appropriate.  The CI pipeline runs the frontend build and backend tests on every push.