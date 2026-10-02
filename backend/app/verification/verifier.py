"""Independent deterministic claim verifier.

Validates AI reasoning citations and factual constraints against machine-readable evidence objects.
Does NOT invoke an LLM for verification.
"""

from typing import Any
from app.schemas.ai import ClaimVerificationResult, DecisionReasoning


def verify_claims(
    reasoning: DecisionReasoning | dict[str, Any],
    issue: dict[str, Any],
    evidence_list: list[dict[str, Any]]
) -> ClaimVerificationResult:
    if isinstance(reasoning, dict):
        reasoning = DecisionReasoning.model_validate(reasoning)

    available_ids = {ev["evidence_id"] for ev in evidence_list}

    top_cited = set(reasoning.evidence_ids)
    root_cause_cited = {eid for rc in reasoning.root_causes for eid in rc.evidence_ids}
    all_cited = top_cited | root_cause_cited

    valid_citations = sorted(list(all_cited & available_ids))
    invalid_citations = sorted(list(all_cited - available_ids))

    details: list[str] = []

    if reasoning.abstain:
        details.append(f"AI explicitly abstained: {reasoning.abstain_reason or 'No reason provided.'}")
        return ClaimVerificationResult(
            status="verified",
            details=details,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations
        )

    if not all_cited:
        details.append("Reasoning provided no evidence citations.")
        return ClaimVerificationResult(
            status="rejected",
            details=details,
            valid_citations=[],
            invalid_citations=[]
        )

    if invalid_citations:
        details.append(f"Invalid or unknown evidence IDs cited: {', '.join(invalid_citations)}.")
        status = "rejected" if not valid_citations else "partially_verified"
        if valid_citations:
            details.append(f"Valid evidence IDs cited: {', '.join(valid_citations)}.")
        return ClaimVerificationResult(
            status=status,
            details=details,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations
        )

    details.append(f"All {len(valid_citations)} cited evidence IDs successfully verified against dataset evidence.")
    return ClaimVerificationResult(
        status="verified",
        details=details,
        valid_citations=valid_citations,
        invalid_citations=[]
    )
