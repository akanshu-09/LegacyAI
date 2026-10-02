# Architecture

## Implemented in Phase 0

React/Vite and one FastAPI/Python modular monolith share a monorepo. Backend modules will share one application and deployment, not independent services.

Current flow: browser → GET /health → FastAPI → fixed JSON status → visible connection state. The frontend checks the response, times out after five seconds, and offers retry. No business data, metrics, sessions, or AI requests exist yet.

The browser reads public VITE_API_BASE_URL; the backend reads CORS_ORIGINS. Local .env files are ignored; examples are committed. CORS permits configured origins only and is not authentication. Phase 0 allows GET without credentials. Later API phases must deliberately extend methods and test preflight behavior.

## Planned boundaries (not implemented)

1. Ingestion validates uploaded sales/inventory data with explicit schema and quality errors.
2. Deterministic Python analytics compute authoritative metrics with documented units, time windows, assumptions, missing values, and aggregation rules.
3. Issue detectors consume validated metrics. Evidence generation attaches stable IDs and traceable source/metric references.
4. Groq reasons only over verified evidence. Structured schemas constrain recommendations and numerical claims.
5. Independent verification checks AI claims against evidence before presentation. Unsupported claims are rejected or cause abstention; schema validity alone is insufficient.
6. Ask LegacyAI uses the same evidence and verification path, never LLM calculations as authoritative metrics.
7. Deterministic simulation calculates hypothetical scenarios from explicit assumptions, separately from observed facts. AI may explain results.
8. Temporary sessions isolate uploaded data and derived evidence with explicit expiry and cleanup. No database or durable persistence is assumed.

Planned flow: validated inputs → deterministic metrics → issues/evidence → reasoning → independent claim checks → recommendations with evidence links. Simulation branches from validated data and user assumptions, labeling results hypothetical.

## Frontend and deployment

The browser owns presentation, never authoritative calculations or provider credentials. Planned routes: /, /data, /insights, /ask, /decisions, /decisions/:issueId, /simulator. Only the root connection page exists in Phase 0.

Vite static output is compatible with Vercel. Uvicorn/FastAPI is compatible with Render. Phase 1 configures the API URL before building and exact deployed frontend origins on the backend. Future Groq credentials stay in backend environment secrets. No deployment occurs in Phase 0.

## Scope control

No authentication, databases, vector databases, RAG, LangChain, multi-agent runtime, Kafka/streaming, microservices, Kubernetes, neural-network forecasting, reinforcement learning, ERP integration, or autonomous purchasing unless the roadmap explicitly changes. Prefer explainable calculations and abstain when data cannot support analysis.
