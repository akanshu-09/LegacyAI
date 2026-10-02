# LegacyAI implementation roadmap

Work in phase order. Deployment follows the complete core product vertical slice locally, in Phase 7, before UX polish/reliability/submission. Later modules below are plans, not implemented functionality. Global exclusions unless this roadmap is explicitly changed: authentication, any database, vector database, RAG, LangChain, multi-agent runtime, Kafka/streaming, microservices, Kubernetes, neural-network forecasting, reinforcement learning, ERP integrations, autonomous purchasing.

## Phase 0 — Foundation
- Objective: establish a reproducible React/Vite + FastAPI monorepo.
- Functionality: GET /health, browser connection state/retry, local environment configuration and CORS.
- Expected files/modules: frontend/src/, backend/app/main.py, backend/tests/, environment examples, AGENTS.md, README.md, docs/ARCHITECTURE.md.
- Acceptance criteria: dependencies install; both dev servers start; health succeeds; browser connects; frontend builds; backend tests pass; tracked files contain no secrets.
- Required tests: health payload/status, allowed/disallowed CORS origins, frontend build, live browser connection/failure/retry, secret/ignore checks.
- Out of scope: deployment and all business/AI features.
- Completion status: complete; locally validated on 2026-10-02. See docs/PHASE0_VALIDATION.md.
- Handoff notes: all Phase 0 gates passed; see docs/PHASE0_VALIDATION.md for commands, evidence and the upstream test warning. The revised Phase 1 is ingestion, validation and analysis sessions.

## Phase 1 — Data Ingestion, Validation & Analysis Sessions
- Objective: establish trusted input data and bounded temporary sessions.
- Functionality: V1 sales/inventory CSV upload and Load Demo Business, explicit schemas/units, normalization/quality profiles, structured validation errors, size limits, temporary session isolation/expiry and synthetic examples.
- Expected files/modules: backend/app/ingestion/, backend/app/sessions/, frontend/src/pages/Data.jsx, data/, docs/DATA_CONTRACT.md.
- Acceptance criteria: valid files normalize reproducibly; malformed/unsupported inputs fail clearly; sessions are isolated and expire; frontend upload/demo work end-to-end; frontend production build and backend tests pass; /health still works; no secrets/local artifacts are tracked.
- Required tests: missing columns, types, empty files, duplicate rows, dates, invalid quantities, size limits, cleanup and session isolation.
- Out of scope: authoritative analytics, issue detection, AI, persistent database.
- Completion status: complete; locally validated on 2026-10-02. All completion gates passed; see docs/PHASE1_VALIDATION.md.
- Handoff notes: V1 contract and missing/duplicate policies are documented in docs/DATA_CONTRACT.md. Phase 2 must use immutable normalized backend records and Decimal money, distinguish inventory snapshots from sales flows, and attach results to the existing isolated sessions with their absolute expiry. Retain the documented 2 MiB/10,000-row and session-capacity bounds. No analytics/AI/deployment is implemented. Stop until Phase 2 is requested.

## Phase 2 — Deterministic Business Analytics
- Objective: compute trusted business metrics in Python.
- Functionality: defined sales/inventory aggregations with units, windows, assumptions and supported-data checks.
- Expected files/modules: backend/app/analytics/, backend/tests/test_analytics.py, docs/METRICS.md, frontend/src/pages/Insights.jsx.
- Acceptance criteria: metrics match hand-verified fixtures; unsupported calculations abstain; frontend displays backend results.
- Required tests: known totals, boundary dates, zero denominators, missing data, returns, rounding and aggregation invariants.
- Out of scope: issue recommendations, LLM calculations, forecasting.
- Completion status: complete; locally validated and reviewed on 2026-10-02. Metric semantics preceded implementation; independent fixture/demo checks, 90 passing backend tests, frontend production build, upload/demo workflows and Phase 1 regressions passed. See docs/PHASE2_VALIDATION.md.
- Handoff notes: docs/METRICS.md defines analytics-v1 formulas, exact Decimal serialization, latest-per-product inventory and fixed seven-day comparison/abstention policy. Phase 3 must consume these verified values and support states for evidence generation. No detection, AI or deployment is implemented. Stop until Phase 3 is requested.

## Phase 3 — Issue Detection & Evidence
- Objective: turn trusted metrics into traceable issues.
- Functionality: deterministic rule detectors, explicit thresholds, evidence IDs and source/metric references.
- Expected files/modules: backend/app/detectors/, backend/app/evidence/, frontend/src/pages/IssuePanel.jsx within /insights, docs/DETECTORS.md. The requested minimal evidence panel provides inspection; separate decision pages are deferred.
- Acceptance criteria: every issue links to reproducible evidence; thresholds and severity are explainable; no unsupported issue appears.
- Required tests: threshold boundaries, evidence integrity, stable references, no-issue cases and missing evidence.
- Out of scope: LLM reasoning and simulation.
- Completion status: complete; locally validated and adversarially audited on 2026-10-02. All five detector families, exact thresholds, semantic deterministic IDs, provenance and abstention are implemented. Final boundary/evidence audit passed after correcting presentation-dependent IDs; 219 backend tests, frontend production build, npm audit and demo/upload evidence workflows passed. See docs/PHASE3_VALIDATION.md.
- Handoff notes: docs/DETECTORS.md defines detectors-v1, issues-v1 and evidence-v1, exact rational values, severity rules and identity/provenance. Frozen Phase 0–2 contracts and demo data are unchanged. Phase 4 must verify claims against evidence and preserve unsupported states; user-supplied labels are untrusted. No AI, recommendations or deployment is implemented. Stop until Phase 4 is requested.

## Phase 4 — AI Decision Engine + Claim Verification
- Objective: generate recommendations grounded in verified evidence.
- Functionality: backend-only Groq integration, structured outputs, independent numerical/evidence claim checks, abstention and provider failure handling.
- Expected files/modules: backend/app/reasoning/, backend/app/verification/, backend/app/schemas/, docs/AI_CONTRACT.md.
- Acceptance criteria: only verified claims reach users; fabricated numbers/references are rejected; provider secrets never reach the browser.
- Required tests: mocked provider contracts, fabricated claims, schema violations, prompt injection in data, timeouts, rate limits and abstention.
- Out of scope: general chat, agents, RAG, autonomous actions.
- Completion status: complete; locally validated on 2026-10-02.
- Handoff notes: Groq integration, provider abstraction, structured output schemas, independent claim verification, graceful provider failure degradation, and /decisions workspace implemented. 230 backend tests and frontend production build pass.

## Phase 5 — Ask LegacyAI
- Objective: answer supported questions about the active verified dataset.
- Functionality: /ask interface, bounded evidence selection and verified answers with citations; unsupported questions abstain.
- Expected files/modules: backend/app/ask/, frontend/src/pages/Ask.jsx, backend/tests/test_ask.py.
- Acceptance criteria: answers reference active-session evidence, never invent metrics, and clearly identify unsupported requests.
- Required tests: answerable/unanswerable questions, cross-session access, claim verification, malicious prompts and provider failures.
- Out of scope: open-domain assistant, web search, vector retrieval/RAG.
- Completion status: complete; locally validated on 2026-10-02.
- Handoff notes: Natural language intent classification, deterministic Python answer compiler, /ask backend endpoint, graceful AI degradation, and /ask frontend page implemented. 237 backend tests and frontend production build pass.

## Phase 6 — What-If Simulator
- Objective: explore transparent hypothetical business changes.
- Functionality: deterministic scenario inputs/results, baseline comparison, explicit assumptions and hypothetical labels.
- Expected files/modules: backend/app/simulation/, frontend/src/pages/Simulator.jsx, docs/SIMULATION.md.
- Acceptance criteria: identical inputs produce identical results; baseline and scenario remain distinct; unsupported scenarios are rejected.
- Required tests: unchanged baseline, hand-computed scenarios, invalid ranges, zero/missing values and no source-data mutation.
- Out of scope: predictive neural models, reinforcement learning, autonomous purchasing.
- Completion status: complete locally (2026-10-02).
- Handoff notes: deterministic product scenarios, explicit baseline receipt, bounded percentage controls and 7/14/30-day horizons implemented. Exact unit arithmetic, hypothetical comparisons, zero-demand abstention and session lifecycle verified. 298 backend tests pass; one optional live Groq test skips. Frontend build and browser validation pass. See docs/SIMULATION.md and docs/PHASE6_VALIDATION.md. Phase 7 remains not started.

## Phase 7 — Deployment
- Objective: validate split hosting after the complete core vertical slice works locally.
- Functionality: Vercel frontend, Render backend, production environment/CORS configuration and health checks.
- Expected files/modules: deployment configuration as needed, docs/DEPLOYMENT.md, README updates.
- Acceptance criteria: public HTTPS frontend reaches backend health endpoint; secrets remain server-side; deployment is reproducible; the completed upload-to-simulation workflows work in the hosted environment.
- Required tests: deployed health, browser CORS/connectivity, frontend build, backend regression tests and deployed core workflow smoke tests.
- Out of scope: new ingestion/analytics/AI features, new infrastructure beyond Vercel/Render and final UX polish.
- Completion status: not started.
- Handoff notes: use frontend/ and backend/ as service roots; document URLs, environment variables and rollback procedure; preserve bounded temporary-session semantics.

## Phase 8 — UX Polish
- Objective: make the verified workflows clear and cohesive.
- Functionality: polished planned routes, responsive navigation, accessibility, loading/empty/error states and evidence drill-down.
- Expected files/modules: frontend/src/components/, frontend/src/pages/, frontend styles and UI tests.
- Acceptance criteria: all planned routes work; keyboard/mobile flows are usable; uncertainty/evidence remain visible.
- Required tests: critical browser journeys, keyboard access, responsive layouts and failure states.
- Out of scope: new analytics or infrastructure.
- Completion status: not started.
- Handoff notes: document design conventions and remaining accessibility limitations.

## Phase 9 — Adversarial/Reliability Testing
- Objective: demonstrate resilience and trustworthy abstention.
- Functionality: adversarial fixtures, malformed-input/provider-failure coverage and bounded resource checks.
- Expected files/modules: backend/tests/adversarial/, frontend browser tests, docs/RELIABILITY.md.
- Acceptance criteria: fabricated claims are blocked; session isolation holds; failure modes are explicit and reproducible.
- Required tests: malicious uploads/prompts, numerical edge cases, provider outages, session expiry, upload/resource limits and end-to-end regression.
- Out of scope: new product features or infrastructure expansion.
- Completion status: not started.
- Handoff notes: record coverage, known limits, reproducible commands and unresolved risks for packaging.

## Phase 10 — Submission Packaging
- Objective: deliver a reproducible, evidence-backed demonstration.
- Functionality: final README, synthetic demo workflow, architecture narrative, screenshots and submission materials.
- Expected files/modules: docs/DEMO.md, docs/SUBMISSION.md, README.md, demo assets.
- Acceptance criteria: a fresh developer can reproduce setup/demo; claims match implemented functionality; secrets/private data are absent.
- Required tests: fresh-install smoke test, complete build/test suite, demo walkthrough and artifact/secret review.
- Out of scope: last-minute feature expansion.
- Completion status: not started.
- Handoff notes: provide exact deployment/demo links, known limitations and maintenance instructions.
