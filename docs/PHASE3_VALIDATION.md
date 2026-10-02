# Phase 3 validation

Validated locally on 2026-10-02 from clean main at `3200fcf3c16615e493912d013bc1f3afb91c4a91`. No commit, push or deployment performed. Phase 4 is not started.

## Scope and design

Read AGENTS.md, ROADMAP.md, ARCHITECTURE.md, DATA_CONTRACT.md, METRICS.md, ingestion/session implementation and analytics code/tests before edits. Created DETECTORS.md before detector logic. No frozen Phase 0–2 contract change/blocker was required. All five families use deterministic backend rules; no LLM, recommendations, confidence scores or unavailable financial claims exist. No dependencies added or lockfiles changed. Demo data is unchanged.

- Demand decline: exact units percentage change over supported latest seven versus preceding seven dataset days. LOW ≤−20%, MEDIUM ≤−35%, HIGH ≤−50%.
- Demand spike: same supported periods, LOW ≥25%, MEDIUM ≥50%, HIGH ≥100%.
- Stockout: coverage=latest inventory×7/current seven-day units. HIGH ≤1 day, MEDIUM >1 and <3, LOW ≥3 and <7.
- Excess: LOW >30 and ≤60 days, MEDIUM >60 and ≤90, HIGH >90. Month-scale review thresholds were chosen before demo evaluation, not tuned to produce demo issues.
- Anomaly: latest seven target days versus preceding 28 calendar days, at least 14 observed baseline days and complete target coverage. Median of lower/upper halves, excluding the odd middle. Strictly outside Q1−1.5IQR or Q3+1.5IQR; quartile-distance/IQR >1.5 LOW, >3 MEDIUM, >4.5 HIGH.

Inventory requires an observation on dataset end E; old snapshots abstain. Zero recent demand abstains for both inventory families; zero prior demand abstains for both percentage demand families. Missing coverage/history, calendar boundaries, too few anomaly samples and zero IQR have explicit unsupported states. Evaluated-no-issue is distinct. No imputation, raw-row export or snapshot summation across dates.

Issue/evidence schemas, exact thresholds, rational/display policy and limitations are in [DETECTORS.md](DETECTORS.md). IDs are full SHA-256 canonical content hashes scoped by normalized dataset, entity, detector version and evidence/issue payload. Identical normalized content produces identical IDs across sessions; IDs confer no access. `detected_at` is the dataset as-of date, not wall-clock execution time. Numeric evidence includes exact numerator/denominator strings, inputs and observed/aggregated/derived provenance. Summary numbers come exclusively from attached evidence. GET `/api/v1/analysis/{analysis_id}/issues` retains existing session expiry, no-store and CORS behavior, including a post-computation availability check.

## Tests, commands and final audit

- From backend/: `.venv/Scripts/python.exe -m pytest tests/test_detectors.py -q` initially passed 60 focused cases.
- Dedicated audit added adversarial threshold-rounding, wide calendar spans, 10,000-row bounds, entity-label identity separation, release-during-computation and hand-verified all-family fixture cases.
- From backend/: `.venv/Scripts/python.exe -m pytest` — **156 passed, 1 existing warning**, 5.66 seconds. All **90 Phase 0–2 tests** pass plus **66 Phase 3 cases**.
- From frontend/: `npm ci` — successful clean locked install; 65 packages added, 66 audited, **0 vulnerabilities**. Stopped the existing Vite process before install to avoid its Windows file lock.
- From frontend/: `npm run build` — passed, Vite 7.3.6, 32 modules, 933 ms. JS 218.43 kB (gzip 67.90 kB); CSS 2.41 kB (gzip 1.01 kB).
- Restarted backend with `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log` and frontend with `npm run dev -- --host localhost` for live validation. Servers remain running for inspection. Backend restart correctly invalidated old IDs.
- `git diff --check` and candidate-file artifact/credential scans passed. `.gitignore` covers actual .env, virtualenv, node_modules, build output and caches; reviewed paths include no IDE/machine-specific artifacts. No source secrets/credential patterns found. Screenshots contain synthetic data and deterministic evidence IDs only, not session capability IDs. Nothing staged.

Tests assert actual numbers and severities at −20/−35/−50%, +25/+50/+100%, 1/3/7 coverage days, 30/60/90 excess days, anomaly fences and severity equalities. Near-threshold values that display as −20%, +25%, 1.00 or 30.00 still use exact values. For example coverage 1.00001→display 1.00 is MEDIUM, and 30.00001→display 30.00 is LOW excess. Fractions ±0.125 serialize to ±0.13; tiny negative rounded zero becomes 0.00.

Audit also covers observed zeros, absent products/windows, missing days, stale inventory, latest snapshot selection, zero denominators, constant/zero-IQR baselines, insufficient samples, even/odd quartiles, multiple anomalies, disjoint baseline/target windows, immutability and caller Decimal-context independence. IDs/order are stable on reversed records and equal normalized Decimal representations; changed dataset content changes all IDs. Entity IDs containing delimiters cannot collide through concatenation. Every issue reference resolves to matching entity/detector evidence; every evidence object is used. Summaries are checked against attached values. JSON serialization rejects non-finite values. Unknown/expired/deleted sessions preserve 404 semantics; release/expiry during computation does not return results. No retained detector cache or session lifetime extension exists.

No functional defect remained after the dedicated audit. No Phase 0–2 implementation was refactored. SHA-256 collision resistance remains an assumption; tests check identity construction and accidental collisions, not cryptographic proof. Bound tests are not a production load benchmark.

## Hand-verifiable scenarios and demo outcome

The separate `backend/tests/fixtures/detectors_business.csv` contains 175 synthetic rows over 35 days, five products, all five families. Expected by hand:

| Product | Inputs | Result |
| --- | --- | --- |
| Decline | previous 7×10=70, current 7×6=42; −28/70×100=−40% | MEDIUM decline |
| Spike | previous 70, current 7×16=112; 42/70×100=60% | MEDIUM spike |
| Stockout | inventory 0, current 70, daily demand 10 | 0 days, HIGH stockout |
| Excess | inventory 1000, daily demand 10 | 100 days, HIGH excess |
| Anomaly | baseline fourteen 10s and fourteen 14s; Q1=10, Q3=14, IQR=4, upper fence=20; observed 40 | distance (40−14)/4=6.5, HIGH anomaly |

Other fixture products have constant anomaly baselines and explicitly abstain with zero_iqr. These are test conditions, not adjustments to the repository demo.

Unchanged `data/demo_business.csv`, C=2026-03-25…31, produces **3 issues, 12 evidence objects, 30 evaluations**, all evaluations supported:

| Product | Calculation | Issue |
| --- | --- | --- |
| Harbor Pen Set (P-002) | U=73, D=73/7≈10.43; I=0; coverage=0 | HIGH stockout |
| Summit Mug (P-003) | U=101, D=101/7≈14.43; I=828; coverage=5796/101≈57.39 | LOW excess |
| Orbit Desk Lamp (P-005) | U=185, D=185/7≈26.43; I=90; coverage=630/185≈3.41 | LOW stockout |

Latest inventory dates are 2026-03-31. No latest-window demand decline/spike or IQR anomaly is detected in the demo. Historical patterns outside the target window are intentionally not classified. Regression tests pin these demo outcomes.

## Browser validation

In-app browser at localhost:5173 with live API:

1. Reloaded an old session after server restart: existing unknown/expired recovery message appeared.
2. Data → Load Demo Business → Insights: three correct inventory issues and explicit evaluated-no-issue entries; existing analytics remained visible with revenue 157094.00, units 6556 and inventory 1439.
3. Opened Summit Mug evidence: snapshot 828 dated Mar 31, seven-day units 101, daily demand 101/7, coverage 5796/101, source classifications and method visible. Expanded calculation inputs/ID. [Demo evidence screenshot](phase3-demo-evidence.png).
4. Uploaded the 175-row all-family fixture through the file picker. All five expected issues appeared with correct severities and summaries.
5. Demand filter showed decline/spike; decline evidence showed 70→42, −28/−40%, Jan 22–28 versus Jan 29–Feb 4.
6. Anomalies filter showed the Feb 4 observation 40, Q1=10, Q3=14, IQR=4, fence=20, baseline Jan 1–28 with 28 samples, exact distance 13/2. Other products explicitly showed unsupported zero-IQR status. [Anomaly evidence screenshot](phase3-anomaly-evidence.png).
7. Inventory filter showed only excess/stockout; changing filters cleared the prior evidence selection. Analytics remained accessible below the issue/evaluation sections. Both saved screenshots were visually inspected.

## Exact files

Created:

- backend/app/detectors/__init__.py
- backend/app/detectors/config.py
- backend/app/detectors/engine.py
- backend/app/evidence/__init__.py
- backend/app/evidence/contract.py
- backend/tests/test_detectors.py
- backend/tests/test_phase3_audit.py
- backend/tests/fixtures/detectors_business.csv
- frontend/src/pages/IssuePanel.jsx
- docs/DETECTORS.md
- docs/PHASE3_VALIDATION.md
- docs/phase3-demo-evidence.png
- docs/phase3-anomaly-evidence.png

Modified:

- backend/app/analysis.py
- frontend/src/pages/Insights.jsx
- frontend/src/style.css
- README.md
- ROADMAP.md
- docs/ARCHITECTURE.md
- docs/README.md

Deleted: none. Dependencies: none added. Original demo, Phase 1 parser/store/data contract, Phase 2 analytics/metric contract and their existing tests are unchanged.

## Warnings and limitations

One existing Starlette TestClient/HTTPX deprecation warning recommends httpx2; no dependency migration performed. Python is absent from PATH here; the working backend virtual environment is used. Git emits normal LF→CRLF notices. Local unauthenticated, single-process sessions remain temporary and bounded; detection does not add authentication or durable persistence.

Thresholds are explicit V1 heuristics, not business-specific stocking targets or statistical significance. Coverage assumes the recent rate solely for a descriptive ratio; no forecast, lead-time adjustment, costs or recommendations. Anomalies require adequate observed baseline data, ignore missing baseline days, and abstain on zero IQR even if a later value differs. Target windows are fixed at the latest dataset dates; no historical issue timeline or arbitrary filters. Detected-at means dataset as-of date. IDs are content-stable across identical sessions, not authorization handles. UI is a minimal inspection interface; no full UX redesign, accessibility audit or deployment was performed.

All Phase 3 completion gates passed locally. Phase 4 must consume versioned evidence, respect unsupported evaluations and treat dataset text as untrusted. No AI provider, prompts, recommendations, Ask or simulation were added. Await an explicit Phase 4 request.

## Final adversarial audit

Performed the requested falsification audit on 2026-10-02 against all repository rules, metric/detector contracts and Phase 2 primitives. Added 63 cases in test_phase3_audit.py; all existing 156 cases remain unchanged and passing. No Phase 0–2 implementation/contract changes or dependencies were needed.

**Finding and correction:** original SHA-256 inputs included rounded evidence values, method wording, issue summary/title/name text and the order of evidence references. A regression test first failed when display precision changed while exact evidence remained identical. Evidence identity now excludes `value` and `method`; issue identity excludes presentation title/summary/name and sorts its evidence references before hashing. Exact fractions, dataset content, entity, detector version, metric, units, periods, source, inputs and observation dates still determine evidence identity; issue classification and linked semantic evidence determine issue identity. DETECTORS.md now enumerates precisely what is hashed. This corrects pre-commit Phase 3 IDs without changing detector classifications. Refreshed screenshots contain the corrected IDs. No data migration is needed because detection is request-local and Phase 3 is uncommitted.

**Boundary results:** all requested hundredth-percentage demand cases passed: decline −19.99/−20/−34.99/−35/−49.99/−50 → none/LOW/LOW/MEDIUM/MEDIUM/HIGH; spike +24.99/+25/+49.99/+50/+99.99/+100 → none/LOW/LOW/MEDIUM/MEDIUM/HIGH. Inventory coverage uses exact I×7/U: zero and exactly one day HIGH; immediately above one and below three MEDIUM; exactly three and below seven LOW; seven or greater no stockout issue. Excess exactly30/just-over30/exactly60/just-over60/exactly90/just-over90 → none/LOW/LOW/MEDIUM/MEDIUM/HIGH. The duplicated 30/60/90 lines in the audit request were tested as equality and immediately above, consistently with the explicit existing contract. Zero demand remains unsupported, never infinity. An end-date-minus-one snapshot yields stale_inventory_snapshot with its actual observation date and required period visible.

**IQR results:** independent repeated/zero/even/odd examples agree with median-of-halves, odd middle excluded. Separate lower/upper tests pin strict 1.5 fences, equality at 3 staying LOW and at 4.5 staying MEDIUM, and immediately outside each band. A sparse 14-observation Jan 1–28 baseline with 13 older outliers correctly excludes those older records and uses 14 samples, not 28 records or 28 imputed days. Removing one in-window sample yields insufficient_anomaly_samples despite the older history. Target observations never enter the baseline. Constant valid history explicitly remains unsupported/zero_iqr; this deliberate conservative policy does not claim health.

**Evidence and identity:** traced every fixture family from normalized records to exact evidence and issue. Hand values remain decline70→42/−40%, spike70→112/+60%, stockout0 days, excess100 days, anomaly40 versus fence20 with Q1=10/Q3=14/IQR=4 and distance13/2. All evidence references resolve to matching entity/version, no duplicate IDs with different semantic content or orphan evidence were found, and summaries agree with attached values. Source kind/name distinguishes observed, aggregated and derived facts. Identity tests cover changed entity, period, metric, version, observation date, exact values that share the same rounded display, units, classification, reordered dictionaries and evidence references. Reversed records and repeat execution produce identical output. Display/method/summary changes leave semantic IDs unchanged. SHA-256 collision resistance is assumed; no mathematical collision guarantee is claimed.

**Independent demo oracle:** raw CSV was read using stdlib csv; sums and exact Fraction arithmetic were calculated without detector helpers. Quartiles used statistics.median_low/median_high on independently selected halves. Current C=Mar25–31, previous Mar18–24, anomaly baseline Feb25–Mar24 (28 observations/product):

| Product | Previous/current units | Exact demand change % | Q1/Q3 | IQR fences | Current daily units |
| --- | --- | --- | --- | --- | --- |
| P-001 | 46/37 | −450/23 ≈ −19.57 | 7/10 | 2.5…14.5 | 6,6,5,5,5,5,5 |
| P-002 | 72/73 | 25/18 ≈ 1.39 | 9.5/11.5 | 6.5…14.5 | 12,9,10,11,12,9,10 |
| P-003 | 97/101 | 400/97 ≈ 4.12 | 13/15 | 10…18 | 15,16,12,13,14,15,16 |
| P-004 | 42/43 | 50/21 ≈ 2.38 | 5/7 | 2…10 | 7,5,6,7,5,6,7 |
| P-005 | 181/185 | 400/181 ≈ 2.21 | 24/27 | 19.5…31.5 | 27,28,24,25,26,27,28 |
| P-006 | 86/87 | 50/43 ≈ 1.16 | 12/14 | 9…17 | 14,11,12,13,14,11,12 |

All demand percentages lie strictly between −20 and +25; every target lies inside its fences, with nonzero IQR. Thus absence of demand/anomaly issues is legitimate, not failed evaluation. Raw latest inventory and demand reproduce Harbor0×7/73=0 (HIGH stockout), Summit828×7/101=5796/101≈57.39 (LOW excess), Orbit90×7/185=126/37≈3.41 (LOW stockout).

**API/UI:** full suite includes unknown/expired/released sessions, unchanged expiry and release/expiry during computation. An additional API case returns all five unsupported evaluations for a fresh seven-day zero-demand dataset with empty issues/evidence, not a healthy claim. Response keys exclude raw normalized rows. Browser rerun after backend restart displayed the correct expired-session recovery. Reloaded demo and all-family upload; classifications and analytics remained unchanged. Opened regenerated Summit and anomaly evidence, expanded calculation inputs, verified exact fractions/IDs and filter behavior. Constant-baseline unsupported states remained visibly distinct from evaluated-no-issue. Frontend was inspected: it only filters/paginates/displays returned classifications and resolves selected evidence; it contains no detector arithmetic, severity assignment, recommendations or generated AI prose.

**Final commands/results:** backend `.venv/Scripts/python.exe -m pytest` → **219 passed, 1 existing warning**, 3.87s. Frontend `npm run build` → **passed**, 32 modules, 757ms, unchanged asset sizes. `npm audit` → **0 vulnerabilities**. `git diff --check`, candidate secret/artifact review and frozen-file diff check passed. All real .env, dependencies, venv, build output and caches remain ignored. No secrets, credentials, IDE or machine-specific files are candidates. Nothing staged/committed/pushed/deployed. Existing upstream Starlette/HTTPX warning and documented V1 heuristic/session limitations remain. Phase 3 is safe to commit; Phase 4 is not started.
