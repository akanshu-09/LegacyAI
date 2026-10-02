# LegacyAI

An evidence-backed AI decision engine for business sales and inventory data, built for BuildFastAI.

**AI reasons about verified data — it does not replace the data.** Authoritative business metrics will come exclusively from deterministic Python calculations.

Phase 0 provides the React/Vite + FastAPI foundation. Phase 1 adds CSV validation, temporary analysis sessions, a synthetic demo and a structural dataset profile at `/data`. Phase 2 adds deterministic backend analytics at `/insights`: business, product and category summaries, daily sales, and supported period comparisons. Phases 4–5 add server-side AI reasoning, independent verification and Ask LegacyAI; Phase 6 adds hypothetical simulation. See [ROADMAP.md](ROADMAP.md).

Phase 3 adds deterministic demand decline/spike, stockout risk, excess inventory and daily sales anomaly detectors. `/insights` now includes issue filters, explicit unsupported evaluations, and an evidence panel with verified values, exact fractions, methods and provenance. No AI or recommendations are generated.

## Repository

Phase 6 adds `/simulator`: choose a product, supply your own hypothetical baseline receipt quantity, adjust receipt −50…+50% and demand −30…+30%, then select 7/14/30 days. Python returns separate baseline/scenario demand, ending inventory, remaining coverage, stockout/excess conditions and exact differences. Results are scenarios, not forecasts or order instructions. Complete recent coverage and fresh stock are required. Zero demand explicitly abstains on coverage/excess. Decisions links into the selected product; no AI key is required for simulation. See [simulation formulas and assumptions](docs/SIMULATION.md) and [Phase 6 validation](docs/PHASE6_VALIDATION.md). Phase 7 deployment remains unstarted.

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

Run upload commands from the repository root. Retrieve/release profiles with GET/DELETE `/api/v1/analysis/{analysis_id}`. GET `/api/v1/analysis/{analysis_id}/analytics` returns deterministic metrics without raw rows or extending expiry. Unknown/expired IDs return 404 with instructions to reload data. See the data contract for error shapes and session capacity limits.

After loading data, follow **View deterministic business analytics** to `/insights`. Revenue uses the supplied values; inventory uses each product's latest snapshot once. Comparisons use the latest seven dataset calendar days versus the preceding seven, requiring complete daily product coverage. Missing observations cause explicit abstention. Money uses Decimal and two-place strings; V1 supplies no currency identifier. See [metric definitions](docs/METRICS.md) for exact formulas and limitations.

GET `/api/v1/analysis/{analysis_id}/issues` returns versioned issues, evidence and per-detector evaluations for the same session. In `/insights`, choose **All**, **Demand**, **Inventory** or **Anomalies**, then **View evidence**. Severity is assigned by backend rules; unsupported is distinct from evaluated-no-issue. Demand uses supported seven-day comparisons; inventory uses a fresh end-date snapshot and recent demand; anomalies use a documented historical IQR baseline. See [detector/evidence contract](docs/DETECTORS.md) and [Phase 3 validation](docs/PHASE3_VALIDATION.md). The unchanged demo yields three inventory conditions; the separate synthetic `backend/tests/fixtures/detectors_business.csv` exercises all five families.

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

Deployment to Vercel and Render is Phase 7, after the complete core product works locally. Groq will remain server-side in Phase 4. See [architecture](docs/ARCHITECTURE.md), [Phase 0 validation](docs/PHASE0_VALIDATION.md), [Phase 1 validation](docs/PHASE1_VALIDATION.md) and [Phase 2 validation](docs/PHASE2_VALIDATION.md).
