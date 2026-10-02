# Engineering rules

- Never fabricate business metrics.
- Deterministic Python analytics are the source of truth for numerical business claims.
- The LLM reasons only over verified evidence supplied by the application.
- LLM output must eventually use structured schemas and independent validation.
- Never expose or commit API keys/secrets. Browser VITE_* configuration is public.
- Never silently remove working functionality.
- Run relevant tests after modifications.
- Do not add dependencies without justification.
- Do not introduce new infrastructure unless ROADMAP.md explicitly requires it.
- Do not implement later roadmap phases while working on an earlier phase unless required to unblock that phase.
- Update roadmap/handoff information after completing a phase.
- Prefer simple, explainable calculations over unjustified ML complexity.
- Unsupported analyses should abstain rather than fabricate answers.

## Boundaries

Keep a React/Vite frontend and a FastAPI/Python modular monolith. Follow docs/ARCHITECTURE.md and ROADMAP.md. No authentication, database, vector database, RAG, LangChain, multi-agent runtime, Kafka, microservices, Kubernetes, neural-network forecasting, reinforcement learning, ERP integrations, or autonomous purchasing unless the roadmap is explicitly changed.

## Verification

From frontend/: `npm ci` and `npm run build`.
From backend/ with the virtual environment active: `python -m pytest`.
For connectivity changes, start both applications and verify the browser reports Backend connected, then exercise failure and retry.
