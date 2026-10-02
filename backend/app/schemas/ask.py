"""Pydantic schemas for Phase 5 Ask LegacyAI functionality."""

from typing import Any, Literal
from pydantic import BaseModel, Field
from app.schemas.ai import ClaimVerificationResult


class AskIntent(BaseModel):
    intent_type: Literal[
        "business_overview",
        "top_risks",
        "product_performance",
        "category_performance",
        "inventory_risk",
        "demand_change",
        "recommend_action",
        "unsupported"
    ] = Field(..., description="Parsed intent type.")
    target_entity: str | None = Field(None, description="Extracted product or category target if applicable.")
    supported: bool = Field(True, description="Whether the question is supported by dataset evidence.")
    reason: str | None = Field(None, description="Reason if question is unsupported.")


class FactualFinding(BaseModel):
    finding: str = Field(..., description="Authoritative factual summary calculated deterministically in Python.")
    why: str = Field(..., description="Explanation of calculation or underlying evidence.")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Key metrics extracted from analytics.")


class AskResponse(BaseModel):
    analysis_id: str
    expires_at: str
    question: str
    intent: AskIntent
    factual_finding: FactualFinding
    ai_available: bool
    ai_error: str | None = None
    explanation: str | None = Field(None, description="AI-assisted explanation grounded in evidence.")
    recommendation: dict[str, Any] | None = Field(None, description="Recommended operational action if applicable.")
    verification: ClaimVerificationResult
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Machine-readable evidence objects.")
