# Phase 1 validation and handoff

Validated on 2026-10-02 (Asia/Calcutta), Windows, Python 3.12.14, Node 24.16.0, npm 11.13.0. Starting state: clean main at `0425a9ea4dfb096db87acee41a0654f385af513a`, synchronized with origin/main. This work is intentionally uncommitted and unstaged.

## Scope and roadmap

Reviewed AGENTS.md, ROADMAP.md and docs/ARCHITECTURE.md before implementation. Reordered the roadmap while preserving objectives, constraints, tests and acceptance criteria: Foundation; Ingestion/Validation/Sessions; Deterministic Analytics; Detection/Evidence; AI/Verification; Ask; Simulator; Deployment; UX Polish; Reliability; Packaging. Deployment remains Vercel + Render in Phase 7, after the local core vertical slice. Corrected references in README, architecture, engineering rules and the historical Phase 0 handoff.

Implemented Phase 1 only: deterministic ingestion/normalization/quality profiles, bounded in-memory sessions, synthetic demo loading and the /data experience. No business insights, detectors, AI, recommendations, simulation, deployment configuration or infrastructure were added. Phase 0 /health remains intact.

## Completion gates and actual results

| Gate | Actual evidence |
| --- | --- |
| Backend tests | Initial implementation: 52 passed. Final code review regression suite: 66 passed, one existing upstream Starlette/HTTPX deprecation warning. |
| Frontend production build | Vite 7.3.6; 30 modules transformed; successful build in 625 ms. Output: index.html 0.39 kB, CSS 2.04 kB, JS 202.66 kB (JS gzip 63.99 kB). |
| Live valid upload | Browser selected data/demo_business.csv through the file chooser, clicked Upload CSV, and displayed Validated · Uploaded CSV, 540 rows, 6 products, 3 categories, 2026-01-01 to 2026-03-31. Actual backend returned 201; browser preflight succeeded. |
| Live demo | Load Demo Business returned 201 and displayed the same deterministic structural profile with zero missing values, duplicates and validation errors. |
| Live invalid input | Browser uploaded backend/tests/fixtures/missing_columns.csv; API returned 422 and the UI listed missing category, inventory, product_name, revenue, unit_price and units_sold. The previous valid session remained visible. |
| Session behavior | Browser reload restored the uploaded session profile; Release analysis session returned 204 and cleared it; backend restart followed by page reload displayed the unknown/expired recovery message; loading the demo again recovered successfully. |
| Isolation and expiry | Backend tests verify separate random IDs/data, unchanged independent profiles, release of one session without affecting another, unknown IDs, rejection at the exact TTL boundary, cleanup, count/memory capacity, no active-session eviction and shutdown clearing. Clock injection avoids a 30-minute sleep. |
| Health regression | All three original health/CORS tests pass; live root page showed Backend connected. |
| Artifact review | git diff --cached --name-only returned no paths; tracked/new candidate path scan found no local artifacts; common credential/private-key pattern scan found no matches; git check-ignore confirmed local environment, virtualenv, node_modules, dist, pytest cache and IDE files remain ignored. |
| Formatting | git diff --check passed; only Windows LF/CRLF conversion notices. |

Saved browser evidence: [valid demo profile](phase1-data-profile.png), [schema rejection preserving the prior session](phase1-validation-error.png). These screenshots contain synthetic/profile information, no uploaded private data or session IDs.

## Test coverage

Tests exercise valid CSV/normalization, UTF-8 BOM, reordered columns, quoted commas, exact Decimal values, leading-zero identifiers, empty/header-only data, malformed quotes, null bytes, invalid encoding, row-width/blank-row errors, exact schema recognition, invalid dates, nonnumeric/fractional/negative quantities, invalid/negative/NaN/infinite/exponent/overprecision currency fields, numeric bounds, text length/control characters, required blanks, optional null preservation, invalid optional lead time, normalized duplicates, conflicting labels/daily observations, byte and row limits, streamed oversize without Content-Length, bad Content-Length, unsupported content type, capped error detail, independent/immutable sessions, expiry/cleanup/release, count/memory capacity, deterministic demo/missing-demo errors, POST/DELETE CORS preflights and error-response CORS/no-store headers.

## Dependencies and API

No dependencies added or changed. Uses existing FastAPI/Starlette infrastructure and Python csv, Decimal, date, secrets, threading and asyncio. Raw CSV bodies avoid a multipart dependency and let application buffering stop at the upload limit. Existing pytest/HTTPX provide tests. The frontend adds no router dependency: standard links and Vite SPA fallback support the two current routes.

- POST /api/v1/analysis/upload: raw UTF-8 CSV, 201 session/profile, structured validation/size/media errors.
- POST /api/v1/analysis/demo: same pipeline for the fixed repository demo, 201 session/profile.
- GET /api/v1/analysis/{analysis_id}: metadata/profile, never raw records; 404 unknown/expired/released.
- DELETE /api/v1/analysis/{analysis_id}: 204 immediate release; 404 unavailable.
- GET /health: unchanged.

POST and DELETE were added to the local CORS allowlist alongside GET. Origin restrictions and credential behavior are unchanged. Analysis responses set Cache-Control: no-store.

## Decisions and limits

The exact V1 field meanings, units and policies are in docs/DATA_CONTRACT.md. Required blanks, invalid values, exact normalized duplicates, conflicting product labels and multiple conflicting rows for one product/day reject the entire dataset. Optional blanks/absent columns remain null, with missing counts and warnings. Headers are never guessed/renamed. Value whitespace is trimmed and counted. No partial dataset is admitted; no duplicate is silently dropped or aggregated. Currency is Decimal, quantities are integers, IDs are strings and dates are explicit ISO dates.

Uploads: at most 2 MiB and 10,000 rows. Error details: at most 100 with total/truncation metadata. Sessions: absolute 30-minute lifetime, maximum 20 sessions and 64 MiB conservative retained-data reservations (2 MiB + 4 KiB per row per session). Full capacity returns 503. Cleanup occurs on access/create/release and every 60 seconds in the lifespan task. Restart/shutdown clears memory. Each session has independent profile copies and immutable records. The browser persists only the analysis ID in tab-scoped sessionStorage; display metadata stays transient. Original file bytes/names are not stored on the backend or written to disk.

The demo contains 540 entirely synthetic daily observations, six products, three categories, three supplier labels, all ten V1 fields and 90 days from 2026-01-01 through 2026-03-31. Fixed demand/inventory variation can support later analytics tests; Phase 1 computes no detectors or business insights.

## Commands executed

Read-only inspection included Get-Content, Git status/diff/ls-files, rg reference searches, and a listener check. Source and documentation edits used apply_patch. The static demo was deterministically assembled and written via apply_patch. Browser interactions used the local app and file chooser; screenshots were saved from the browser API.

```powershell
# Repository root
git status --short --branch
git diff --check
git diff --stat
git diff --cached --name-only
git ls-files --others --exclude-standard
git check-ignore backend/.env frontend/.env.local backend/.venv/pyvenv.cfg frontend/node_modules/react/package.json frontend/dist/index.html backend/.pytest_cache/README.md .vscode/settings.json .idea/workspace.xml .vs/config/applicationhost.config
# backend/
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# frontend/
npm.cmd run build
npm.cmd run dev
```

Intermediate test runs passed 47 and 48 tests as coverage grew; the final run passed 52. The initial sandboxed build was blocked by esbuild filesystem access restrictions; the approved build outside the sandbox succeeded. Starting both dev servers initially reported ports 8000/5173 already in use by the earlier Phase 0 servers. The prior backend was stopped using its known session's Ctrl+C and restarted with Phase 1; the running Vite server served the changes. The backend was restarted once more to verify lost-session recovery. A scripted Git candidate-file review scanned artifact paths and common Groq/OpenAI/AWS/GitHub/Google/Slack credential/private-key patterns, printing only filenames/line numbers if found; no matches occurred.

## Exact files created/modified/deleted

Modified:
- AGENTS.md
- README.md
- ROADMAP.md
- backend/app/main.py
- data/README.md
- docs/ARCHITECTURE.md
- docs/PHASE0_VALIDATION.md
- docs/README.md
- frontend/src/main.jsx
- frontend/src/style.css

Created:
- backend/app/analysis.py
- backend/app/ingestion/__init__.py
- backend/app/ingestion/validation.py
- backend/app/sessions/__init__.py
- backend/app/sessions/store.py
- backend/tests/fixtures/missing_columns.csv
- backend/tests/test_analysis.py
- data/demo_business.csv
- docs/DATA_CONTRACT.md
- docs/PHASE1_VALIDATION.md
- docs/phase1-data-profile.png
- docs/phase1-validation-error.png
- frontend/src/api.js
- frontend/src/pages/Data.jsx

Deleted: none. Dependency manifests/lockfiles are unchanged. Generated dist/caches remain ignored.

## Warnings, limitations and manual actions

The existing StarletteDeprecationWarning recommends httpx2 for future TestClient updates; tests pass, and no dependency was added just to silence it. Python is still absent from PATH on this machine; the existing project virtual environment was used. Sandbox filesystem restrictions required an approved frontend build/dev command.

Sessions require a single process; independent workers do not share memory. IDs are opaque capability handles, not authentication; anyone possessing an ID can access its profile/release it. Closing the tab or replacing a dataset leaves the previous backend session until expiry unless explicitly released. Retained-data reservations do not bound total interpreter/RSS or simultaneous transport buffers. Money supports a single owner-defined currency and at most two decimal places; fractional quantities/returns and mixed currencies are intentionally unsupported. Phase 2 must define business formulas and supported analyses rather than infer them.

No unresolved completion blockers. No manual action is required for Phase 1 completion. Open localhost:5173/data to inspect. Local servers remain running for review; stop them when finished. Nothing was staged, committed, pushed or deployed. Phase 0 and Phase 1 are complete; Phase 2 and all subsequent phases remain not started. Proceed to deterministic analytics only on a new request.

## Final Phase 1 code review · 2026-10-02

Reviewed all Phase 1 implementation and supporting changes against AGENTS.md, ROADMAP.md, ARCHITECTURE.md and DATA_CONTRACT.md. Three defects were corrected without changing phase scope or dependencies:

1. Python csv.reader(strict=True) accepted bare quotes inside unquoted fields. Added a bounded linear quote-syntax check before parsing. Malformed bare/misplaced quotes and junk after closing quotes now return structured 422 errors; properly doubled quotes and quoted commas remain supported.
2. Session lifetimes previously depended on time.time(), so wall-clock corrections could extend or truncate the stated lifetime. Expiry/cleanup now use a monotonic deadline; the UTC display timestamp remains fixed separately. Regression coverage changes the wall clock in both directions and verifies availability through second 1799 and rejection at second 1800.
3. Filesystem failures checking/reading the demo could produce an unstructured 500. They now return a structured 503 demo_unavailable response without leaking exception text or filesystem paths. Missing-file, stat failure and open failure are covered.

Added boundary/concurrency regression tests for a valid CSV of exactly 2 MiB and 10,000 rows, one byte over the limit, understated Content-Length, concurrent attempts to create 40 sessions under the default 20-session cap, the independent default 64 MiB reservation limit, DELETE freeing both session/count and reservation capacity, actual DELETE CORS headers, denied PUT preflight, and validation of octet-stream bodies rather than trusting media type. All new session IDs in concurrent/replacement tests are distinct and contain the expected 32 bytes of cryptographic randomness.

Confirmed required/optional field policies, explicit ISO dates, integer bounds, exact backend Decimal normalization, duplicate/conflicting-row rejection and unsupported-column rejection remain enforced. Raw Decimal/date records are never returned by Phase 1 APIs: response profiles contain JSON-compatible integers, strings, lists and dictionaries, avoiding accidental float serialization. Session create/cleanup/get/delete operations are protected by the same RLock; metadata responses are copied and records are immutable. Periodic cleanup is cancelled on shutdown and the store is cleared.

Frontend source review confirmed that only analysis_id is persisted. File data is used solely as the active upload body and the file input is cleared immediately after sending; no FileReader, dataset state, localStorage, IndexedDB or raw-row response exists. Transient profile metadata is necessary for display. The fixed demo remains synthetic and deterministic, with no analytics/detectors/AI/recommendations implemented.

Final commands: backend `.venv/Scripts/python.exe -m pytest` (66 passed); frontend `npm.cmd run build` (successful Vite 7.3.6 production build, 30 modules). Git candidate-path and common credential/private-key scans found no secrets, local artifacts or machine-specific absolute paths; git diff --cached --name-only was empty and git diff --check passed. No staging/commit/push/deployment occurred.

Remaining warning: the pre-existing upstream Starlette/HTTPX TestClient deprecation. Documented local limits remain: single backend process, unauthenticated capability IDs, and conservative retained-data reservations rather than a total RSS/concurrent-request memory limit. Within those explicit Phase 1 boundaries, the working tree is safe to commit.
