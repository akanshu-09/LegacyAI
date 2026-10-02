# Phase 2 validation

Validated locally on 2026-10-02, starting from Phase 1 commit `5765d64a5f0cf10aea73bfb3720c8b2397328c62` on main. Phase 2 is complete locally. Nothing was staged, committed, pushed or deployed; Phase 3 is not started.

## Implemented semantics

[METRICS.md](METRICS.md) was created before implementation and reviewed against the final code. Python computes authoritative overview, product/category sales and inventory summaries, observed-day averages, daily revenue/units and business/product period comparisons. No unit-price substitution, costs, profit, margins, ROI, forecasting, issue detectors, evidence IDs, AI or recommendations were added.

Reporting covers the inclusive observed dataset date span. Inventory selects each product's latest observation within that span once; aggregate stock includes snapshot date range and mixed-date metadata. Daily series contains observed flow dates only, never inventory totals across time. Average denominators include observed zero-sales days and exclude missing days.

Comparison uses E=max dataset date: current [E−6,E], previous [E−13,E−7], seven non-overlapping calendar days each. Business requires complete daily coverage for every product anywhere in the dataset; products are evaluated independently. Insufficient history, absent products, missing product days and calendar boundary failures abstain. A zero previous sum suppresses percentage change while preserving supported absolute change. Missing observations are never converted into zero.

Money uses Decimal with a local 50-digit context. Supplied revenue sums remain exact; recurring averages and percentages round only at serialization to two places using ROUND_HALF_UP. Money/ratio values are strings. Integers outside JavaScript's safe range serialize as strings. The frontend never recalculates authoritative metrics or converts money to float.

GET `/api/v1/analysis/{analysis_id}/analytics` returns aggregated analytics-v1 metadata and metrics, no raw normalized rows. No retained analytics cache or expiry renewal is introduced. Availability is rechecked after computation, including expiry/release during calculation. Existing 404 behavior, ingestion limits, capacity, isolation and cleanup remain intact. `/insights` reads only the existing ID from sessionStorage, supports loading/error/retry and session expiry, and paginates tables at 20 entries.

## Commands and results

- From backend/: `.venv/Scripts/python.exe -m pytest` — final review **90 passed, 1 warning** in 3.28 seconds. Includes all 66 prior tests plus 24 analytics cases.
- From frontend/: `npm ci` — clean install, 65 packages added, 66 audited, **0 vulnerabilities**. Initial attempt failed with EPERM because the live Vite process held esbuild.exe; stopped that process, reran successfully, then restarted it.
- From frontend/: `npm run build` — **passed**, Vite 7.3.6, 31 modules, 859 ms. JS 212.16 kB (gzip 66.19 kB), CSS 2.17 kB (gzip 0.92 kB). Earlier sandbox-only build access failure was resolved by approved execution outside the Windows sandbox restriction.
- Backend restarted with `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; frontend restarted with `npm run dev -- --host localhost`. Both remain available locally for inspection.
- `git diff --check` — passed. Git emits normal LF→CRLF working-copy notices.
- Reviewed `git ls-files --cached --others --exclude-standard` candidates against forbidden local artifact paths and credential patterns — no violations or credential matches. No files staged. `git check-ignore` confirms real backend/.env, virtual environment, node_modules, frontend/dist, pytest cache and Python bytecode are ignored. Existing .gitignore needs no change. Intended PNGs contain synthetic validation UI only, with no opaque session IDs or credentials.

## Numerical and regression coverage

Hand fixture `analytics_known.csv` has 28 rows, two products/categories, Jan 1–14. Independently expected revenue = 7×0.10 + 7×0.25 + 7×1 + 7×2 = **23.45**; units = **70**; latest stock = 87+37 = **124**. Revenue comparison 7.70→15.75 gives 8.05 and 104.55%; units 21→49 gives 28 and 133.33%. Product A average revenue 2.45/14=0.175 displays 0.18. Selling price 99 is deliberately unrelated to supplied revenue.

Assertions cover exact totals and reconciliation across categories/products/daily series; mixed latest inventory dates; observed zero averages; sparse date spans without calendar expansion; one-day/2/7/13-day history; exact period boundaries; incomplete daily coverage; products missing either window; historical products in the fixed cohort; zero previous values; negative changes; half-up rounding; maximum V1 10,000-row amounts/units above JavaScript safe range; row-order invariance; immutability; Decimal context isolation; unknown/expired/deleted IDs and expiry during computation; deterministic repeated API results; unchanged profile/lifetime; no-store and CORS. Existing Phase 1 tests preserve rejection of returns/negative input: Phase 2 does not reinterpret that frozen V1 policy.

## Live browser checks

Using the in-app browser on localhost:5173, exercised real UI file selection, upload, profile and navigation to insights:

- **Load Demo Business → insights:** 540 rows, 90 observed days, six products, three categories; revenue **157094.00**, units **6556**, last-known inventory **1439**. Current Mar 25–31 versus previous Mar 18–24; revenue 14607.00→14813.00, +206.00/+1.41%; units 524→526, +2/+0.38%. Product/category/daily tables rendered, daily table paginated 90 entries.
- **Upload hand fixture → insights:** 28-row profile; overview **23.45/70/124**, two products/categories; comparison **7.70→15.75**, **104.55%**, units **21→49**, **133.33%**; product A **0.18** average revenue. Product/category and daily values matched the fixture. [Screenshot](phase2-upload-analytics.png), visually inspected.
- **Upload one-day fixture → insights:** observed revenue **0.00**, units **0**, inventory **5**, averages **0.00**; explicit “Fewer than 14 calendar days of history” message, previous totals and both changes shown as unsupported. No crash or fabricated percentage. [Screenshot](phase2-insufficient-history.png).

## Exact file changes

Created:

- backend/app/analytics/__init__.py
- backend/app/analytics/metrics.py
- backend/tests/fixtures/analytics_known.csv
- backend/tests/fixtures/analytics_tiny.csv
- backend/tests/test_analytics.py
- frontend/src/pages/Insights.jsx
- docs/METRICS.md
- docs/PHASE2_VALIDATION.md
- docs/phase2-upload-analytics.png
- docs/phase2-insufficient-history.png

Modified:

- backend/app/analysis.py
- frontend/src/main.jsx
- frontend/src/pages/Data.jsx
- frontend/src/style.css
- README.md
- ROADMAP.md
- docs/ARCHITECTURE.md
- docs/README.md

Deleted: none. Dependencies/lockfiles changed: none. Phase 1 parser, session store, data contract and existing tests remain unchanged.

## Warnings, limitations and handoff

One existing upstream StarletteDeprecationWarning recommends httpx2 instead of HTTPX for TestClient. It is non-blocking; dependency migration is not part of Phase 2. Python remains absent from PATH on this machine; the existing virtual environment interpreter works. The recovered npm file-lock error and sandbox build restriction are recorded above, not outstanding failures.

V1 has no currency identifier, costs or returns support. Analytics has a full-dataset reporting period and fixed seven-day comparisons only, with conservative cohort coverage; retired/new products can cause business abstention. Stock can be stale or mixed-date and is labeled last-known. No category changes, inventory trends, date filters or imputation exist. Arrays and per-request work are bounded by the existing row limit; no performance/load benchmark or broad UX polish was performed. Single-process temporary sessions still expire absolutely and clear on restart. Browser validation was local, not deployed.

All Phase 2 gates passed. Future Phase 3 work must consume documented analytics-v1 values/bases and explicit support states; it must not recalculate monetary claims in the frontend or treat abstained comparisons as zeros. Wait for an explicit Phase 3 request.

## Final Phase 2 review

Reviewed all Phase 2 code against AGENTS.md, ROADMAP.md, ARCHITECTURE.md, DATA_CONTRACT.md and METRICS.md. No implementation defects were found; no implementation changes or style refactors were made. Strengthened test coverage for exact positive/negative percentage rounding ties: seven daily observations per window with totals 8.00→8.01 or 8.00→7.99 produce ±0.125%, which ROUND_HALF_UP must serialize to ±0.13%. Existing average tests already exercise 0.175→0.18 and 0.005→0.01 boundaries. Added independently audited demo expectations to its existing API regression test.

`/insights` is a frontend route, not a separate backend analytics endpoint. It presents GET `/api/v1/analysis/{analysis_id}/analytics`. Both were inspected: no demand decline/spike, stockout risk, excess inventory, anomaly, severity, evidence issue or recommendation classifier exists. Supported/unsupported labels describe mathematical/coverage eligibility only. JavaScript formats supplied values and paginates tables; it performs no business arithmetic. Category period comparisons are explicitly unimplemented, so absent categories cannot produce category growth claims; absent products cause documented business/product abstention.

Independently checked raw CSV using Python csv plus integer-cent parsing, without importing ingestion or analytics helpers. Demo category revenue: Accessories 48120.00 + Home 86850.00 + Stationery 22124.00 = 157094.00; units 1712+2686+2158=6556. Latest per-product inventory 131+0+828+180+90+210=1439. Mar 18–24 revenue 14607.00, Mar 25–31 revenue 14813.00; difference 206.00 and 206/14607×100=1.410282…%, displayed 1.41%. Units 524→526 give 2/524×100=0.381679…%, displayed 0.38%. Fixture arithmetic independently remains 0.70+1.75+7+14=23.45 revenue, 14+28+7+21=70 units, and 87+37=124 stock; 8.05/7.70×100=104.545454…%, displayed 104.55%.

Reran full backend suite: 90 passed/one existing warning. Reran frontend production build: passed, 31 modules, 867 ms; output sizes unchanged. Browser review repeated demo load→insights, daily pagination to page 2, file-picker upload of the 28-row fixture→insights, and refreshed the one-day session to confirm observed zeros/insufficient-history abstention. Values matched the independent checks. Existing screenshots remain representative; the uploaded-fixture screenshot was refreshed for this review.

Final candidate-file credential/local-artifact checks and git diff --check passed. No dependency or Phase 1 contract changes. Phase 2 is safe to commit within its documented local scope; nothing was staged, committed, pushed or deployed. Phase 3 remains not started.
