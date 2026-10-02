# LegacyAI

An evidence-backed AI decision engine for business sales and inventory data, built for BuildFastAI.

**AI reasons about verified data — it does not replace the data.** Authoritative business metrics will come exclusively from deterministic Python calculations.

Phase 0 provides the React/Vite + FastAPI foundation. Phase 1 adds supported CSV validation, normalized backend data, temporary analysis sessions, a synthetic demo and a structural dataset profile at `/data`. Business analytics and AI features are not implemented yet. See [ROADMAP.md](ROADMAP.md).

## Repository

- `frontend/`: React + Vite browser application
- `backend/app/`: FastAPI modular monolith
- `backend/tests/`: backend tests
- `data/`: synthetic demo CSV
- `docs/`: architecture and validation records
- `AGENTS.md`: engineering constraints

## Local setup

Prerequisites: Git, Node.js 22.12+ (Node 24 supported), npm, and Python 3.12+. Clone this repository and use two terminals from its root.

### Backend (PowerShell)

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux use `python3 -m venv backend/.venv`, `backend/.venv/bin/python` instead of the Windows interpreter path, and `cp` instead of `Copy-Item`. Inside backend/, use `.venv/bin/python`.

The backend loads backend/.env regardless of launch directory; existing environment variables take precedence. `CORS_ORIGINS` is a comma-separated list of exact origins, defaulting to `http://localhost:5173`. GET [http://localhost:8000/health](http://localhost:8000/health) returns `{"status":"ok","service":"legacyai-backend"}`. This indicates process health only.

### Frontend (second terminal)

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

On macOS/Linux use `cp .env.example .env`. Open [http://localhost:5173](http://localhost:5173) and confirm **Backend connected**. Stop the backend and click **Check again** to see **Backend disconnected**. Restart the backend and retry to reconnect.

Open [the data workspace](http://localhost:5173/data), choose **Load Demo Business**, or upload a UTF-8 CSV matching [the V1 contract](docs/DATA_CONTRACT.md). Files may be at most 2 MiB/10,000 rows. Required missing values, duplicates, conflicting product/day observations and invalid fields are rejected with corrective errors. Optional blanks remain null. The profile displays structural counts, date coverage, schema recognition and quality information.

Sessions expire after 30 minutes, clear on restart, and can be released using the page button. Use one backend process. The browser keeps only the analysis ID in tab-scoped sessionStorage; the backend keeps normalized data in bounded temporary memory. Reopening/reloading the same tab fetches its profile without extending expiry. No API keys, database or real business dataset are needed.

The API accepts raw CSV, avoiding multipart buffering and additional dependencies:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/analysis/upload -H "Content-Type: text/csv" --data-binary "@data/demo_business.csv"
curl.exe -X POST http://localhost:8000/api/v1/analysis/demo
```

Run upload commands from the repository root. Retrieve/release profiles with GET/DELETE `/api/v1/analysis/{analysis_id}`. Unknown/expired IDs return 404 with instructions to reload data. See the data contract for error shapes and session capacity limits.

`VITE_API_BASE_URL` defaults to `http://localhost:8000`. Vite embeds it in the browser bundle at build time: never put secrets in `VITE_*` variables. Restart Vite after configuration changes. No API keys are needed in Phase 0.

If connectivity fails, check both servers, the API URL, and the exact browser origin in `CORS_ORIGINS`. Opening the frontend on 127.0.0.1 requires adding that origin. Vite uses strict ports to avoid silently changing the origin.

## Validation

```powershell
# From backend/
.venv/Scripts/python.exe -m pytest
# From frontend/
npm run build
npm run preview
```

For preview connectivity add `http://localhost:4173` to backend `CORS_ORIGINS` and restart the backend. Build output frontend/dist/ is ignored. Production backend installations use requirements.txt; development adds pytest and HTTPX via requirements-dev.txt.

React/React DOM render the UI; Vite and its React plugin provide build tooling. FastAPI/Uvicorn provide the API/server; python-dotenv loads local configuration. Pytest/HTTPX test API behavior. No analytics or AI dependencies are included.

Phase 1 adds CSV ingestion, validation and temporary analysis sessions. Deployment to Vercel and Render is Phase 7, after the complete core product works locally. Groq will remain server-side in Phase 4. See [architecture](docs/ARCHITECTURE.md), [Phase 0 validation](docs/PHASE0_VALIDATION.md) and [Phase 1 validation](docs/PHASE1_VALIDATION.md).
