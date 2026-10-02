"""Structured schemas for AI reasoning and claim verification."""

from typing import Any, Literal
from pydantic import BaseModel, Field


class RootCause(BaseModel):
    explanation: str = Field(..., description="Explanation of plausible root cause based on evidence.")
    evidence_ids: list[str] = Field(default_factory=list, description="Evidence IDs supporting this root cause.")


class Recommendation(BaseModel):
    action: str = Field(..., description="Specific, operationally modest recommended action.")
    target: str = Field(..., description="Target entity, product, or scope of action.")
    timeframe_days: int = Field(14, ge=1, le=365, description="Recommended operational timeframe in days.")


class DecisionReasoning(BaseModel):
    summary: str = Field(..., description="High-level reasoning summary grounded in evidence.")
    root_causes: list[RootCause] = Field(default_factory=list, description="Plausible root causes supported by evidence.")
    recommendation: Recommendation = Field(..., description="Operational decision recommendation.")
    assumptions: list[str] = Field(default_factory=list, description="Explicit operational assumptions.")
    uncertainties: list[str] = Field(default_factory=list, description="Uncertainties or absent context.")
    what_would_change_this_decision: list[str] = Field(default_factory=list, description="Factors that would alter this decision.")
    evidence_ids: list[str] = Field(default_factory=list, description="All cited evidence IDs used in reasoning.")
    abstain: bool = Field(False, description="Whether the AI abstained from making a recommendation.")
    abstain_reason: str | None = Field(None, description="Reason for abstention if abstain is True.")


class ClaimVerificationResult(BaseModel):
    status: Literal["verified", "partially_verified", "rejected", "unverified"] = Field(
        ..., description="Verification status of the AI reasoning against dataset evidence."
    )
    details: list[str] = Field(default_factory=list, description="Specific verification findings or checks.")
    valid_citations: list[str] = Field(default_factory=list, description="Cited evidence IDs verified in dataset.")
    invalid_citations: list[str] = Field(default_factory=list, description="Cited evidence IDs missing from dataset.")


class DecisionResponse(BaseModel):
    analysis_id: str
    expires_at: str
    issue_id: str
    issue: dict[str, Any]
    ai_available: bool
    ai_error: str | None = None
    reasoning: DecisionReasoning | None = None
    verification: ClaimVerificationResult
    cited_evidence: list[dict[str, Any]] = Field(default_factory=list)
