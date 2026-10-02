# Architecture

## Implemented through Phase 1

React/Vite and one FastAPI/Python modular monolith share a monorepo. Backend modules will share one application and deployment, not independent services.

The root page retains the Phase 0 flow: browser → GET /health → fixed JSON status → visible connection state, with a five-second timeout and retry.

Phase 1 flow: `/data` → streamed raw CSV upload or repository demo → deterministic Python CSV/schema validation → immutable normalized records → bounded in-memory session → structural profile. Invalid data returns structured errors and creates no session. The browser receives no normalized rows and persists only the opaque analysis ID. See [DATA_CONTRACT.md](DATA_CONTRACT.md) for fields, policies, API and limits.

`app/ingestion/validation.py` owns parsing, schema validation, normalization and quality profiling; `app/sessions/store.py` owns independent IDs, capacity and expiry; `app/analysis.py` owns the versioned transport endpoints; `app/main.py` composes these modules and the periodic cleanup lifecycle. Backend data exists only in one process's memory, expires absolutely after 30 minutes, and clears on restart. No business analytics or AI requests are implemented.

The browser reads public VITE_API_BASE_URL; the backend reads CORS_ORIGINS. Local .env files are ignored; examples are committed. CORS permits configured origins only and is not authentication. Phase 1 adds POST for upload/demo and DELETE for release to GET; configured/unconfigured origins and preflight behavior are tested. No credentials are used.

## Boundaries and later work

1. Ingestion and temporary sessions are implemented in Phase 1 using the V1 contract. Future extensions must preserve explicit validation and session isolation.
2. Deterministic Python analytics compute authoritative metrics with documented units, time windows, assumptions, missing values, and aggregation rules.
3. Issue detectors consume validated metrics. Evidence generation attaches stable IDs and traceable source/metric references.
4. Groq reasons only over verified evidence. Structured schemas constrain recommendations and numerical claims.
5. Independent verification checks AI claims against evidence before presentation. Unsupported claims are rejected or cause abstention; schema validity alone is insufficient.
6. Ask LegacyAI uses the same evidence and verification path, never LLM calculations as authoritative metrics.
7. Deterministic simulation calculates hypothetical scenarios from explicit assumptions, separately from observed facts. AI may explain results.
8. Later metrics/evidence will attach to the existing bounded temporary sessions and share their expiry. No database or durable persistence is assumed.

Planned flow: validated inputs → deterministic metrics → issues/evidence → reasoning → independent claim checks → recommendations with evidence links. Simulation branches from validated data and user assumptions, labeling results hypothetical.

## Frontend and deployment

The browser owns presentation, never authoritative calculations or provider credentials. Routes `/` and `/data` exist; `/insights`, `/ask`, `/decisions`, `/decisions/:issueId` and `/simulator` belong to later phases. The current navigation uses standard links with Vite's local SPA fallback; no routing dependency is needed for these two routes.

Vite static output is compatible with Vercel. Uvicorn/FastAPI is compatible with Render. Deployment is Phase 7, after ingestion, analytics, evidence, verified AI reasoning, Ask and simulation work locally. Phase 7 configures the API URL before building and exact deployed frontend origins on the backend. Future Groq credentials stay in backend environment secrets. No deployment occurs in Phase 1.

## Scope control

No authentication, databases, vector databases, RAG, LangChain, multi-agent runtime, Kafka/streaming, microservices, Kubernetes, neural-network forecasting, reinforcement learning, ERP integration, or autonomous purchasing unless the roadmap explicitly changes. Prefer explainable calculations and abstain when data cannot support analysis.
