# Launch runbook

This guide walks through the final prep needed to ship the Supplement Interaction Tracker tonight. It assumes you are working from the repository root.

## 1. Finalize the dataset
- [ ] Review `data/` and swap in the real CSV/YAML files you plan to launch with (`compounds.csv`, `interactions.csv`, `sources.csv`, `risk_rules.yaml`).
- [ ] Run `python scripts/validate_data.py` (if you add one) **or** spot check the new files to ensure column headers line up with the examples in `data/`.
- [ ] Confirm citations (`sources.csv`) have working URLs and human readable titles; these surface directly in the UI.

## 2. Verify backend scoring
- [ ] Activate the virtual environment and install dependencies:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- [ ] Run the automated suite:
  ```bash
  pytest
  ```
- [ ] Boot the API locally and confirm it ingests the production dataset without warnings:
  ```bash
  uvicorn api.risk_api:app --reload --host 0.0.0.0 --port 8000
  ```
- [ ] Hit the health endpoint and a couple of real interactions:
  ```bash
  curl http://localhost:8000/api/health
  curl "http://localhost:8000/api/pair?compound_a=...&compound_b=..."
  curl -X POST http://localhost:8000/api/stack -H 'Content-Type: application/json' \
       -d '{"compounds": ["...", "..."]}'
  ```

## 3. QA the frontend
- [ ] Install dependencies and run the Vite dev server:
  ```bash
  npm install
  npm run dev
  ```
- [ ] Visit http://localhost:5173, verify search/pair/stack flows, and confirm severity badges and citations render correctly with the real dataset.
- [ ] Trigger empty-state and error scenarios (empty form submits, invalid compounds) to ensure the launch copy looks good.
- [ ] Build the production bundle and preview it:
  ```bash
  npm run build
  npm run preview
  ```

## 4. Container rehearsal
- [ ] Build the Docker images and start the stack:
  ```bash
  docker compose build
  docker compose up
  ```
- [ ] Confirm nginx waits for the backend health check and serves the React bundle at http://localhost:5173.
- [ ] Tail logs for any warnings about missing data or failed requests.

## 5. Deployment
- [ ] Push the built images to your registry (example commands shown, adjust registry/project names):
  ```bash
  docker build -t registry.example.com/supptracker-backend:$(date +%Y%m%d) -f backend/Dockerfile .
  docker build -t registry.example.com/supptracker-frontend:$(date +%Y%m%d) -f frontend/Dockerfile .
  docker push registry.example.com/supptracker-backend:$(date +%Y%m%d)
  docker push registry.example.com/supptracker-frontend:$(date +%Y%m%d)
  ```
- [ ] Provision the target environment (.env values, reverse proxy, TLS) per `railway.toml` or your chosen platform.
- [ ] Update environment variables (`SUPPTRACKER_DATA_DIR`, `RISK_RULES_PATH`, `VITE_API_BASE`) as needed.
- [ ] Run database/file backups for the source CSVs before switching traffic.

## 6. Launch night checklist
- [ ] Re-run `pytest` and `npm run build` immediately before deployment to catch regressions.
- [ ] Confirm the health endpoint is green after deploying.
- [ ] Walk through each UI flow in production with the launch dataset.
- [ ] Keep one terminal tailing backend logs for the first hour after going live.
- [ ] Have a rollback plan (previous image tags) ready in case issues arise.

## 7. Post-launch
- [ ] Capture user feedback in an issue tracker.
- [ ] Schedule a data refresh cadence and assign ownership.
- [ ] Document any manual steps you performed so the next launch is smoother.
