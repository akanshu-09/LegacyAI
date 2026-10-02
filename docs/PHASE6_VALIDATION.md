# Phase 6 validation and handoff

Phase: 6 — What-If Simulator. Status: complete locally, 2026-10-02. Started from main at `61a57d0` (Phase 5). Read the user handoff `instructions.md.txt` and all ten required repository instruction/contract/validation files before implementation. The handoff's old Phase 3 first-action section was superseded by the current committed Phase 5 state and the user's request to begin Phase 6. Phase 7 remains not started; no deployment or push performed.

## Implemented and audited

Deterministic Python product simulation, `/simulator`, navigation and a Decisions → selected-product simulation link. Explicit user baseline reorder quantity is necessary because the V1 data has no planned-order field. No quantity is inferred from AI, selling price or historical revenue. Reorder adjustment −50…50%, demand −30…30%, horizon 7/14/30 days. Strict integer types and bounds reject coerced strings, floats, booleans, extra fields and unsupported horizons.

[SIMULATION.md](SIMULATION.md) defines formulas, units, support states, precision, thresholds and assumptions. It was created before code. Source demand is a complete latest seven-calendar-day sum anchored to dataset end, with one fresh latest inventory snapshot. Partial/stale/date-boundary data abstains without imputation. Seven days suffice; the Phase 2 previous comparison window is unnecessary. Baseline and scenario use the same selected horizon and explicit receipt quantity; baseline uses zero adjustments. Source records and prior analytics/detectors/AI/Ask implementations remain unchanged.

All arithmetic is exact Fraction, including receipt/demand adjustments and scenario-minus-baseline differences. Only display rounds HALF_UP using integer quotient/remainder, with exact fractions exposed. No monetary calculations occur. Ending inventory clamps at zero; unmet demand is separate. Exactly depleted at horizon means no unmet demand, not a potential stockout. Hypothetical ending coverage >30 days flags potential excess; equality is false. Zero demand supports flows/inventory but explicitly abstains for coverage and excess, never infinity or a false healthy result.

Architecture remains React/Vite + FastAPI modular monolith; no dependencies, infrastructure, database, forecast model or AI simulation call. New API:

- GET `/api/v1/analysis/{analysis_id}/simulation`: sorted product eligibility and aggregate source inputs/assumptions.
- POST `/api/v1/analysis/{analysis_id}/simulate`: strict scenario request → hypothetical baseline/scenario/exact differences.

Both routes share no-store, configured CORS, existing opaque IDs and absolute session expiry. Availability is checked before and after work. No result cache, session extension, retained upload or raw-row response. UI retains only analysis_id in sessionStorage, clears transient results on control changes/expiry, aborts on unmount, and displays backend values without numerical business calculations.

## Tests and commands

- Baseline before new tests: **236 passed, 1 skipped**, one upstream warning. The optional pre-existing live Groq smoke test skips when the backend key is absent; historical roadmap count 237 included that test.
- Backend `.venv/Scripts/python.exe -m pytest tests/test_simulation.py -q`: initial 58 focused cases passed. Final audit adds four cases (62 Phase 6 cases total).
- Backend `.venv/Scripts/python.exe -m pytest -q`: **298 passed, 1 skipped, 1 warning**, 4.85 seconds. All 236 prior passing regressions still pass.
- Frontend `npm.cmd ci`: locked clean install passed, 65 packages added, 66 audited, **0 vulnerabilities**. Initial sandboxed cache access failed EPERM; approved execution with cache access succeeded.
- Frontend `npm.cmd run build`: **passed**, Vite 7.3.6, 35 modules, 1.42 seconds. JS 241.36 kB (gzip 73.35); CSS 2.62 kB (gzip 1.06). Initial sandboxed build after the failed install could not find Vite; successful install/build resolved it.
- `git diff --check`: passed. Candidate/tracked path and common credential/private-key scans: no matches. `git check-ignore` confirmed real .env, venv, node_modules, dist, caches and IDE files are excluded. No dependency/lockfile changes. User handoff file is preserved untracked and excluded from the project commit.

Tests cover control endpoints/cross-combinations and all horizons, unchanged baseline, fractional receipts, exact depletion and excess boundaries, actual simulation HALF_UP ties (1/8→0.13), excess 30.000000001 displaying 30.00 but correctly flagged, zero demand/stock/receipt, missing/stale/early dates, date.max, maximum quantities, 10,000 rows, JSON safety, no mutation, row-order/context independence, concurrent identical requests, malformed JSON/types/extra fields, unknown products, independent sessions, unchanged expiry, release and exact TTL expiry before/during computation, CORS/preflight and no-store. No new regression defect remained after audit.

## Independent arithmetic

Separately read raw demo CSV with stdlib csv and integer/Fraction arithmetic, without importing ingestion/analytics/simulation helpers. Mar25–31 demand and last Mar31 inventory reproduce:

| Product | Inputs | Baseline result |
| --- | --- | --- |
| Harbor | U73, I0, user Q100, H7 | demand73, ending27, remaining189/73≈2.59, unmet0 |
| Summit | U101, I828, Q0, H14 | demand202, ending626, remaining4382/101≈43.39, potential excess true |
| Orbit | U185, I90, Q0, H7 | demand185, ending0, unmet95, potential stockout true |

Harbor scenario +50% receipt/+30% demand: receipt150, rate949/70, demand94.90, ending55.10, remaining3857/949≈4.06. Exact remaining-days delta is 1400/949≈1.48; subtracting rounded 4.06−2.59 would incorrectly give 1.47, so the browser correctly uses the backend's exact-before-rounding delta.

Independent simple fixture arithmetic: U70, I100, Q100, H14 → baseline demand140, ending60, remaining6. Scenario +50/+30 → receipt150, demand182, ending68, remaining68/13≈5.23, exact coverage delta −10/13. Test expected values are hand-derived, not generated by the engine.

## Browser validation

Local frontend/API, real UI and file picker:

1. Load Demo Business → Simulator: sources/period/as-of date and explicit assumptions visible.
2. Harbor Q100/H7/no adjustment: baseline equals scenario, demand73/ending27/coverage2.59, all differences zero.
3. Slider End keys set +50/+30; changing inputs clears previous output; run shows receipt150/demand94.90/ending55.10/coverage4.06/delta1.48. Opened exact inputs/fractions. [Screenshot](phase6-simulator.png) saved and visually reviewed; synthetic data only, no session capability ID.
4. Summit Q0/H14 and slider Home keys −50/−30: receipt stays0, demand141.40, ending686.60, coverage67.98, excess true; baseline202/626/43.39.
5. Decisions → Simulate this product: navigates to the actual issue product (Harbor); no AI-derived quantity is prefilled. Works with AI key missing.
6. Upload new seven-day synthetic zero-demand fixture → Simulator: demand0, ending10, stockout false, coverage/excess visibly unsupported.
7. Upload existing one-day tiny fixture → Simulator: incomplete daily coverage visible, run disabled.
8. Stop backend → run: error visible, stale result cleared. Restart backend → retry: unknown/expired recovery clears transient inputs/results and stored ID. New demo recovers. Backend TTL tests independently verify absolute expiry without waiting 30 minutes.

Backend and Vite servers remain local for inspection. No live provider call was required for Phase 6. No deployment workflow or Phase 7 configuration was added.

## Exact files and handoff

Created: backend/app/simulation/__init__.py; backend/app/simulation/engine.py; backend/tests/test_simulation.py; backend/tests/fixtures/simulation_zero.csv; frontend/src/pages/Simulator.jsx; docs/SIMULATION.md; docs/PHASE6_VALIDATION.md; docs/phase6-simulator.png.

Modified: backend/app/analysis.py; frontend/src/main.jsx; frontend/src/pages/Decisions.jsx; frontend/src/style.css; README.md; ROADMAP.md; docs/ARCHITECTURE.md; docs/README.md.

Deleted: none. Dependencies added: none. Commit status: final audit passed; legitimate Phase 6 files are ready for the handoff's separate Phase 6 commit. Commit SHA is reported in the completion message because it cannot be included in its own commit.

Known limitations: scenarios assume immediate receipts, constant uniform recent demand, no lead-time/supplier capacity/seasonality/returns/reservations, continuous fractional units and no financial effects. They are not forecasts, probabilities or purchasing instructions. Existing sessions remain temporary, single-process and unauthenticated. Optional live Groq test skipped for missing key; existing Starlette/HTTPX deprecation warning remains. Browser also exposed a pre-existing Decisions abort message alongside functional missing-key degradation; no frozen-phase refactor was undertaken. Phase 6 is safe to commit within these documented boundaries.

Next phase: 7 — Deployment. Next recommended action: review the Phase 6 commit and authorize Phase 7 separately. Stop after Phase 6.
