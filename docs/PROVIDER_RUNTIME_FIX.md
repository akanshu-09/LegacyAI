# Reasoning provider evidence runtime fix · 2026-10-02

## Root cause and scope

The committed Groq provider treated every evidence value as a nested mapping with display_string. Actual evidence-v1, produced by EvidenceBuilder, contains safe integer counts (including inventory 0), large integer strings, and two-place Decimal/Fraction-derived numeric strings. Harbor's zero inventory therefore raised AttributeError before the HTTP request and outside provider error handling. Existing MockDecisionReasoner tests bypassed that serializer; old verifier-only fixtures used invented nested display objects.

Independently executed the committed provider from Git with integer-zero evidence and confirmed the exact reported AttributeError before any network call. Inspected EvidenceBuilder, detector output, Decision/Ask transport, claim verifier and both evidence UIs. Decision and Ask pass canonical evidence unchanged to the same provider; the verifier reads IDs rather than dereferencing value, and JavaScript optional property access safely falls back to displaying primitive zero/string values. No further unsafe Python evidence-value mapping assumptions were found in those paths. This is a targeted serialization/dependency correction, not a full re-audit or redesign of existing Ask/verification policy.

## Normalization

normalize_evidence accepts canonical integer values (excluding booleans) and numeric strings. It preserves value/type/precision and the complete evidence object, adding only a separate human-readable display_string: int 0 → value 0 plus display "0"; string "0.00" remains "0.00"; signed ratios and large integer strings retain their exact text. Exact numerator/denominator, evidence ID/schema/version, entity, units, current/comparison periods, observation date, source name/kind, inputs and method all reach Groq. Original evidence is not mutated, and independent verification still receives the original objects/IDs.

Missing/null/boolean/float/non-finite/nonnumeric/nested values are not canonical evidence-v1. They explicitly raise ProviderSchemaError and use existing unavailable handling, rather than broad exception swallowing or guessed string conversions. Raw Decimal/Fraction values are intentionally handled at EvidenceBuilder's serialization boundary, not introduced as new provider formats. The prompt JSON rejects non-finite values. No detector thresholds, demo data, simulator formulas or verifier behavior changed.

## Dependency correction

httpx==0.28.1 was present only in requirements-dev.txt, although Groq imports it at runtime. Moved that exact existing pin to requirements.txt; dev requirements inherit it via -r requirements.txt. No new dependency family or version upgrade. A fresh ignored tests/.venv installed **only requirements.txt** successfully and imported HTTPX 0.28.1, app/main and the provider with primitive zero. Then installed requirements-dev.txt for tests. The original local backend/.venv points at a removed Python installation, so it was left untouched. An attempted cache-based environment encountered host directory access restrictions; the separate ignored tests/.venv resolved verification.

## Regression evidence

Added 29 cases in backend/tests/test_provider_evidence.py:

- canonical zero/positive/negative integer counts, JavaScript-unsafe count strings, zero/positive/negative fractional display strings and Decimal-derived strings;
- preservation of all exact/provenance fields, JSON safety and source immutability;
- explicit rejection of missing values, null, booleans, float/non-finite, nested objects, lists, nonnumeric strings and raw Decimal/Fraction objects;
- real demo Harbor stockout evidence through the actual Groq provider and HTTPX JSON serialization into both Decision routes and Ask; only HTTP transport is mocked, no credentials/network required;
- all five detector-family fixture payloads, structured response parsing, citation preservation and unknown-citation regression;
- malformed evidence gracefully unavailable with no transport request/internal exception leakage;
- production HTTPX pin and development inheritance.

Commands from backend/ use tests/.venv/Scripts/python.exe. Set GROQ_API_KEY to an empty value only in the test process before importing pytest/app, preventing dotenv from triggering a live call with any locally stored key. No .env file was read into output or modified.

Focused tests: **29 passed**. Complete suite: **327 passed, 1 optional live Groq smoke test skipped, 1 existing Starlette/HTTPX deprecation warning**, 6.73 seconds. Live provider availability/credentials were not tested; mocked transport verifies the failing real-provider serialization path.

Frontend npm ci: successful, 65 packages/66 audited, **0 vulnerabilities**. Initial install hit the running LegacyAI esbuild.exe lock; verified/stopped only the project's Vite/esbuild processes, reran successfully, then restored Vite. npm run build: **passed**, 35 modules, 793 ms, unchanged JS/CSS assets. No frontend source/dependency/lockfile change.

git diff --check and candidate credential/artifact scans pass. Both test environments, .env, node_modules, dist and caches are ignored. instructions.md.txt stays untracked. No staging, commit, push, deployment or Phase 7 work.

Changed: backend/app/reasoning/provider.py; backend/requirements.txt; backend/requirements-dev.txt; docs/AI_CONTRACT.md. Created: backend/tests/test_provider_evidence.py; docs/PROVIDER_RUNTIME_FIX.md. Deleted: none. Fix and tests are verified; leave for review/commit authorization.
