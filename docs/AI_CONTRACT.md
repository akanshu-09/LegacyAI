# AI Decision Engine and Claim Verification Contract (Phase 4)

## Architecture Overview
The AI Decision Engine transforms deterministic issue detections and verified evidence into actionable operational decision recommendations without allowing LLM hallucination to become factual business truth.

```
Issue + Verified Evidence 
       ↓
Groq API / Provider Abstraction 
       ↓
Structured Output Schema (Pydantic)
       ↓
Independent Deterministic Claim Verifier
       ↓
Decision Workspace UI (/decisions)
```

## Provider Abstraction (`app/reasoning/provider.py`)
- Base interface: `BaseDecisionReasoner`
- Integrations:
  - `GroqDecisionReasoner`: Uses Groq API with structured JSON output enforcement (`response_format={"type": "json_object"}`). Configured via `GROQ_API_KEY` and `LLM_MODEL` (default: `openai/gpt-oss-120b`).
  - `MockDecisionReasoner`: Deterministic provider for unit and integration testing without network calls or API keys.
- Factory: `get_reasoner()` automatically selects provider based on `LLM_PROVIDER` (`groq` or `mock`).

### Evidence normalization

Provider inputs use the actual evidence-v1 contract: `value` is an integer for safe counts, a numeric string for large counts, or a two-place numeric string for Decimal/Fraction-derived display values. Zero is a valid fact, not a missing value. Raw Decimal/Fraction objects are serialized by EvidenceBuilder before this boundary; nested `value.display_string` objects exist only in old mock fixtures and are not canonical runtime evidence.

`normalize_evidence` preserves each original value and every evidence field (ID, schema/version, entity, exact numerator/denominator, unit, periods, source name/kind, inputs, method and observation date), adding a separate `display_string` for readable prompting. Numeric strings retain their precision/sign exactly; integers get a decimal display string. Unsupported/missing values, booleans, floats, nulls and nested objects fail explicitly with ProviderSchemaError, allowing existing unavailable handling rather than stringifying unknown facts. The verifier still receives the original deterministic evidence, never the provider's normalized copy. Runtime HTTPX is pinned in requirements.txt so a production-only install can import the provider transport.

## Verification Policy (`app/verification/verifier.py`)
Verification runs independently of the LLM using Python logic:
1. **Citation Verification:** All cited evidence IDs in `reasoning.evidence_ids` and `root_causes[].evidence_ids` must exist in the dataset's evidence pool for that issue.
2. **Citation Requirement:** Non-abstaining recommendations must cite at least one verified evidence ID.
3. **Status Taxonomy:**
   - `verified`: All cited evidence IDs are present in the dataset and valid.
   - `partially_verified`: Some cited evidence IDs are valid, but ungrounded/unknown evidence IDs were also cited.
   - `rejected`: No valid evidence IDs cited, or invalid evidence IDs used exclusively.
   - `unverified`: AI provider was unavailable or error occurred.

## Graceful Failure & Degradation
If Groq API key is missing, network request times out (15s), rate limit is exceeded (HTTP 429), or schema validation fails:
- Backend returns `ai_available: false` with specific `ai_error` and `verification.status = "unverified"`.
- Application dashboard, analytics, issue detection, and evidence inspection remain 100% functional.
