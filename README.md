# SuppTracker

SuppTracker is a local compound-search and label-review prototype.  The
shipped corpus is **not a clinically validated interaction database** and does
not make safety, severity, treatment, or "no interaction" claims.

## Shipped data boundary

`data/openfda_candidates/` contains an auditable, label-derived discovery
corpus built from the openFDA drug-label API:

- 1,098 distinct labelled compounds;
- 6,000 unreviewed label-text candidate records;
- 3,362 distinct directed candidate pairs;
- per-record label set ID, openFDA query URL, retrieval time and source text
  excerpt.

A record means only that the generic or substance name of one labelled product
appeared in another label's `DRUG INTERACTIONS` text.  It is **not** an assessed
interaction.  Candidate records cannot enter the risk-scoring path; the API
returns them only through `/api/label-candidates` with an explicit
`unverified_label_candidates` status.

The data are subject to openFDA's stated CC0 1.0 public-domain dedication,
unless otherwise noted.  See [the source licence](https://open.fda.gov/license/)
and [the dataset contract](docs/OPENFDA_CANDIDATE_DATASET.md). Verbatim FDA supplement-label statements are a separate, unreviewed corpus; see [its contract](docs/OPENFDA_SUPPLEMENT_STATEMENTS.md).

## Run locally

```powershell
python -m pip install -r requirements.txt
python scripts/validate_openfda_candidates.py
python scripts/validate_openfda_supplement_statements.py --dir data/openfda_supplement_statements --terms data/openfda_supplement_statements/supplement_terms.json
uvicorn api.risk_api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
npm ci
npm run dev
```

Open the Vite URL printed by the second command.  The API health endpoint is
`http://127.0.0.1:8000/api/health`.

## Useful endpoints

| Endpoint | Purpose |
| --- | --- |
| `/api/health` | Dataset mode and loaded-record counts |
| `/api/search?q=caffeine` | Search the labelled compound index |
| `/api/label-candidates?compound_id=caffeine` | Unreviewed label-text candidates only |
| `/api/interaction?a=caffeine&b=aspirin` | Reports `not_assessed` when no independently assessed record exists |
| `/api/stack/check` | Shows assessed-pair coverage; absence never means safe |

## Validation

```powershell
python scripts/validate_openfda_candidates.py
pytest -q
npm run typecheck
npm run test
npm run build
```

The GitHub Actions workflow runs the isolated candidate-corpus validator and
the Python test suite.  Rebuild the corpus deliberately with
`python scripts/build_openfda_label_candidates.py`; inspect and validate it
before committing the resulting data.

## Clinical and deployment policy

Do not promote a label candidate to an assessed interaction automatically.
Any future assessed dataset must be separately licensed, independently
reviewed, source-cited, and imported through an assessed-data workflow.  This
prototype is informational only and is not medical advice.

## Deployment

The repository root `Dockerfile` builds one container that serves the API and the built page together. It listens on the port given in `PORT` (8000 when unset) and needs no database, API key or paid add-on.

`render.yaml` describes it as one free Render web service that redeploys on every push to `main`, with `/api/health` as the health check. The free plan sleeps after about 15 minutes without visitors, so the first load after a quiet spell takes up to a minute.

The public page shows verbatim FDA label text and unreviewed candidates only. No assessed interaction records are loaded, and the legacy list in `data/interactions.csv` is not served.