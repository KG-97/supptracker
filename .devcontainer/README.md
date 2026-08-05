# supptracker in the cloud — Codespaces + JetBrains Gateway

This dev container lets you develop supptracker with the **full JetBrains
toolchain** (PyCharm Professional / IntelliJ Ultimate — free via the JetBrains
Student Pack) while your **N100 laptop only runs the lightweight Gateway
client**. All indexing, the FastAPI backend, and the Vite dev server run on
GitHub's cloud VM, not locally.

## Prerequisites
- This repo pushed to GitHub (Codespaces builds from the remote).
- **JetBrains Gateway** installed locally (the only JetBrains piece you install
  on the laptop). Get it from the Toolbox App or jetbrains.com/remote-development/gateway.
- JetBrains Student Pack active (unlocks PyCharm Pro etc.): https://www.jetbrains.com/academy/student-pack/
- GitHub Student Pack linked (gives Codespaces hours): https://education.github.com/pack

## Fastest path — browser
1. On GitHub: **Code ▸ Codespaces ▸ Create codespace on `release/0.2.0`**.
2. It builds from `.devcontainer/` and runs `post-create.sh` automatically.
3. Run the servers (see below). Ports 8000/5174 auto-forward.

## JetBrains Gateway path (thin client on the N100)
1. Open **JetBrains Gateway ▸ Connect to Codespaces** (install the GitHub
   Codespaces plugin in Gateway if prompted), sign in to GitHub.
2. Pick this Codespace, choose **PyCharm** (or IntelliJ) as the backend IDE.
   Gateway installs the backend into the Codespace and opens a thin client.
3. Code as if local. The backend/indexing stay in the cloud.

> Machine size: `devcontainer.json` requests **4 cpus / 8 GB** via
> `hostRequirements` so the JetBrains backend has room. The 2-core/4 GB default
> will thrash under PyCharm indexing.

## Running the app (in the Codespace terminal)
```bash
uvicorn app:app --reload --port 8000    # backend  -> :8000
npm run dev                             # frontend -> :5174 (proxies /api to :8000)
pytest -q                               # tests
```

## Notes
- Python 3.11, Node 20 — matches `requirements.txt` (pandas 2.2.2) and Vite 5.
- The edu license is **non-commercial** (personal/coursework/OSS). supptracker as
  a personal project is fine.
- Stop the Codespace when idle so you don't burn free hours.
