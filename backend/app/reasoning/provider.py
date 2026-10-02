"""Reasoning provider abstraction for Groq API and mock testing.

Enforces provider separation, structured JSON outputs, and graceful failure handling.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

from app.schemas.ai import DecisionReasoning, RootCause


class ProviderError(Exception):
    """Base exception for LLM provider errors."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProviderConfigurationError(ProviderError):
    """Raised when provider API key or config is missing."""
    pass


class ProviderTimeoutError(ProviderError):
    """Raised when provider call times out."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""
    pass


class ProviderSchemaError(ProviderError):
    """Raised when provider output violates structured schema."""
    pass


def normalize_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Present evidence-v1 values without changing their exact facts or identity.

    EvidenceBuilder serializes counts as ints (large counts as strings) and
    Decimal/Fraction ratios as numeric strings. Nested display objects are not
    part of that contract. Keep the complete provenance and exact ratio fields.
    """
    normalized = []
    for ev in evidence:
        value = ev.get("value")
        if type(value) is int:
            readable = str(value)
        elif isinstance(value, str) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
            readable = value
        else:
            raise ProviderSchemaError("Verified evidence has an unsupported value type or format.")
        normalized.append({**ev, "display_string": readable})
    return normalized


class BaseDecisionReasoner(ABC):
    @abstractmethod
    async def generate_decision(
        self,
        issue: dict[str, Any],
        evidence: list[dict[str, Any]],
        context: dict[str, Any] | None = None
    ) -> DecisionReasoning:
        """Generate structured AI decision reasoning for a verified issue and evidence set."""
        pass


SYSTEM_PROMPT = """You are LegacyAI, an evidence-backed decision engine for sales and inventory data.
Your task is to analyze a detected business issue and its verified deterministic evidence, then produce operational decision reasoning.

CRITICAL CONSTRAINTS:
1. You MUST NOT invent business numbers, percentages, dates, revenue, cost savings, or unverified facts.
2. You MUST cite ONLY the evidence IDs explicitly provided in the prompt (e.g. EV-...). Do not invent fake evidence IDs.
3. Your recommendation must be operationally modest (e.g., "Review reorder point with supplier", "Monitor demand decline over next 14 days", "Adjust next replenishment quantity"). No autonomous purchasing or exaggerated claims.
4. Output MUST be valid JSON adhering strictly to the JSON schema.

JSON SCHEMA REQUIREMENT:
{
  "summary": "Concise summary grounded strictly in evidence.",
  "root_causes": [
    {
      "explanation": "Plausible root cause grounded in evidence.",
      "evidence_ids": ["EV-..."]
    }
  ],
  "recommendation": {
    "action": "Clear, operationally modest recommendation.",
    "target": "Target product or category.",
    "timeframe_days": 14
  },
  "assumptions": ["Explicit operational assumption."],
  "uncertainties": ["Uncertainty or missing context."],
  "what_would_change_this_decision": ["Factor that would alter this decision."],
  "evidence_ids": ["EV-..."],
  "abstain": false,
  "abstain_reason": null
}"""


class GroqDecisionReasoner(BaseDecisionReasoner):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ProviderConfigurationError("GROQ_API_KEY is not set.")
        self.model = model or os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    async def generate_decision(
        self,
        issue: dict[str, Any],
        evidence: list[dict[str, Any]],
        context: dict[str, Any] | None = None
    ) -> DecisionReasoning:
        import httpx

        evidence_summary = normalize_evidence(evidence)

        user_content = json.dumps({
            "issue": {
                "issue_id": issue.get("issue_id"),
                "title": issue.get("title"),
                "severity": issue.get("severity"),
                "summary": issue.get("summary"),
                "entity_name": issue.get("entity_name"),
                "entity_id": issue.get("entity_id"),
                "observation_date": issue.get("observation_date")
            },
            "verified_evidence": evidence_summary,
            "business_context": context or {}
        }, indent=2, allow_nan=False)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this issue and verified evidence:\n{user_content}"}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                if response.status_code == 429:
                    raise ProviderRateLimitError("Groq API rate limit exceeded.", status_code=429)
                elif response.status_code in (401, 403):
                    raise ProviderConfigurationError("Invalid Groq API key or unauthorized.", status_code=response.status_code)
                elif response.status_code != 200:
                    raise ProviderError(f"Groq API returned HTTP status {response.status_code}: {response.text}", status_code=response.status_code)

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return DecisionReasoning.model_validate_json(content)

        except httpx.TimeoutException:
            raise ProviderTimeoutError("Groq API request timed out after 15 seconds.", status_code=504)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ProviderSchemaError(f"Failed to parse or validate structured AI output: {exc}") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Unexpected error communicating with Groq: {exc}") from exc


class MockDecisionReasoner(BaseDecisionReasoner):
    def __init__(self, override_reasoning: DecisionReasoning | dict[str, Any] | None = None, should_fail_with: Exception | None = None):
        self.override_reasoning = override_reasoning
        self.should_fail_with = should_fail_with

    async def generate_decision(
        self,
        issue: dict[str, Any],
        evidence: list[dict[str, Any]],
        context: dict[str, Any] | None = None
    ) -> DecisionReasoning:
        if self.should_fail_with:
            raise self.should_fail_with

        if self.override_reasoning:
            if isinstance(self.override_reasoning, dict):
                return DecisionReasoning.model_validate(self.override_reasoning)
            return self.override_reasoning

        ev_ids = [ev["evidence_id"] for ev in evidence]
        entity = issue.get("entity_name", "Target product")

        return DecisionReasoning(
            summary=f"Analysis of {issue.get('title', 'issue')} for {entity} indicates an operational condition requiring attention based on verified evidence.",
            root_causes=[
                RootCause(
                    explanation=f"Observed inventory metrics for {entity} indicate risk bounds were reached.",
                    evidence_ids=ev_ids[:2] if ev_ids else []
                )
            ],
            recommendation={
                "action": f"Review inventory and reorder parameters for {entity}.",
                "target": entity,
                "timeframe_days": 14
            },
            assumptions=["Demand pattern over the last window remains representative."],
            uncertainties=["Supplier lead time and exact carrying costs are not present in dataset."],
            what_would_change_this_decision=["An immediate influx of customer orders or vendor price adjustments."],
            evidence_ids=ev_ids,
            abstain=False,
            abstain_reason=None
        )


def get_reasoner() -> BaseDecisionReasoner:
    provider = os.getenv("LLM_PROVIDER", "groq").lower().strip()
    if provider == "mock":
        return MockDecisionReasoner()

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ProviderConfigurationError("GROQ_API_KEY environment variable is missing or empty.")

    return GroqDecisionReasoner(api_key=api_key)
