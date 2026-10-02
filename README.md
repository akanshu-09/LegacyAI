# LegacyAI

An evidence-backed AI decision engine for business sales and inventory data, built for BuildFastAI.

**AI reasons about verified data — it does not replace the data.** Authoritative business metrics will come exclusively from deterministic Python calculations.

Phase 0 provides a React page that checks a FastAPI health endpoint. Business analytics and AI features are not implemented yet. See [ROADMAP.md](ROADMAP.md).

## Repository

- `frontend/`: React + Vite browser application
- `backend/app/`: FastAPI modular monolith
- `backend/tests/`: backend tests
- `data/`: reserved for synthetic/demo data
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

Phase 1 will deploy to Vercel and Render. Groq will remain server-side in its later phase. Nothing is deployed in Phase 0. See [architecture](docs/ARCHITECTURE.md) and [validation](docs/PHASE0_VALIDATION.md).
