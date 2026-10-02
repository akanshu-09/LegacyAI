"""Adversarial and functional unit/integration tests for Phase 4 AI Decision Engine & Claim Verifier."""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.ai import DecisionReasoning, RootCause
from app.reasoning.provider import (
    MockDecisionReasoner,
    ProviderTimeoutError,
    ProviderConfigurationError,
    ProviderSchemaError,
    get_reasoner
)
from app.verification.verifier import verify_claims


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def demo_session(client):
    res = client.post("/api/v1/analysis/demo")
    assert res.status_code == 201
    return res.json()["analysis_id"]


def test_verify_claims_valid():
    evidence = [
        {"evidence_id": "EV-101", "metric": "current_units", "value": {"display_string": "100"}},
        {"evidence_id": "EV-102", "metric": "latest_inventory", "value": {"display_string": "50"}}
    ]
    reasoning = DecisionReasoning(
        summary="Test reasoning",
        root_causes=[RootCause(explanation="High demand", evidence_ids=["EV-101"])],
        recommendation={"action": "Reorder", "target": "Product A", "timeframe_days": 14},
        assumptions=["Normal demand"],
        uncertainties=[],
        what_would_change_this_decision=[],
        evidence_ids=["EV-101", "EV-102"],
        abstain=False
    )
    res = verify_claims(reasoning, {"issue_id": "ISSUE-1"}, evidence)
    assert res.status == "verified"
    assert "EV-101" in res.valid_citations
    assert "EV-102" in res.valid_citations
    assert len(res.invalid_citations) == 0


def test_verify_claims_invalid_citation():
    evidence = [{"evidence_id": "EV-101", "metric": "current_units"}]
    reasoning = DecisionReasoning(
        summary="Test reasoning",
        root_causes=[],
        recommendation={"action": "Reorder", "target": "Product A", "timeframe_days": 14},
        assumptions=[],
        uncertainties=[],
        what_would_change_this_decision=[],
        evidence_ids=["EV-101", "EV-FAKE-999"],
        abstain=False
    )
    res = verify_claims(reasoning, {"issue_id": "ISSUE-1"}, evidence)
    assert res.status == "partially_verified"
    assert "EV-FAKE-999" in res.invalid_citations


def test_verify_claims_missing_citations():
    evidence = [{"evidence_id": "EV-101"}]
    reasoning = DecisionReasoning(
        summary="Test reasoning",
        root_causes=[],
        recommendation={"action": "Reorder", "target": "Product A", "timeframe_days": 14},
        assumptions=[],
        uncertainties=[],
        what_would_change_this_decision=[],
        evidence_ids=[],
        abstain=False
    )
    res = verify_claims(reasoning, {"issue_id": "ISSUE-1"}, evidence)
    assert res.status == "rejected"
    assert "no evidence citations" in res.details[0]


def test_verify_claims_abstain():
    reasoning = DecisionReasoning(
        summary="Abstain summary",
        root_causes=[],
        recommendation={"action": "Abstain", "target": "Product A", "timeframe_days": 14},
        assumptions=[],
        uncertainties=["Insufficient data"],
        what_would_change_this_decision=[],
        evidence_ids=[],
        abstain=True,
        abstain_reason="Insufficient data available"
    )
    res = verify_claims(reasoning, {"issue_id": "ISSUE-1"}, [])
    assert res.status == "verified"
    assert "explicitly abstained" in res.details[0]


def test_decision_endpoint_mock_success(client, demo_session):
    issues_res = client.get(f"/api/v1/analysis/{demo_session}/issues")
    assert issues_res.status_code == 200
    issues = issues_res.json()["issues"]
    assert len(issues) > 0
    target_issue_id = issues[0]["issue_id"]

    with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
        res = client.post(f"/api/v1/analysis/{demo_session}/decisions/{target_issue_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is True
        assert body["issue_id"] == target_issue_id
        assert body["verification"]["status"] == "verified"
        assert body["reasoning"] is not None
        assert "recommendation" in body["reasoning"]


def test_decision_endpoint_body_success(client, demo_session):
    issues_res = client.get(f"/api/v1/analysis/{demo_session}/issues")
    issues = issues_res.json()["issues"]
    target_issue_id = issues[0]["issue_id"]

    with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
        res = client.post(
            f"/api/v1/analysis/{demo_session}/decisions",
            json={"issue_id": target_issue_id}
        )
        assert res.status_code == 200
        assert res.json()["issue_id"] == target_issue_id


def test_decision_endpoint_nonexistent_issue(client, demo_session):
    res = client.post(f"/api/v1/analysis/{demo_session}/decisions/NONEXISTENT-ISSUE-123")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "issue_not_found"


def test_decision_endpoint_expired_session(client):
    res = client.post("/api/v1/analysis/INVALID-SESSION-ID/decisions/ISSUE-123")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "analysis_unavailable"


def test_decision_endpoint_missing_api_key_degradation(client, demo_session):
    issues_res = client.get(f"/api/v1/analysis/{demo_session}/issues")
    target_issue_id = issues_res.json()["issues"][0]["issue_id"]

    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": ""}):
        res = client.post(f"/api/v1/analysis/{demo_session}/decisions/{target_issue_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is False
        assert "GROQ_API_KEY" in body["ai_error"]
        assert body["reasoning"] is None
        assert body["verification"]["status"] == "unverified"


def test_decision_endpoint_timeout_degradation(client, demo_session):
    issues_res = client.get(f"/api/v1/analysis/{demo_session}/issues")
    target_issue_id = issues_res.json()["issues"][0]["issue_id"]

    mock_reasoner = MockDecisionReasoner(should_fail_with=ProviderTimeoutError("Groq request timed out."))

    with patch("app.analysis.get_reasoner", return_value=mock_reasoner):
        res = client.post(f"/api/v1/analysis/{demo_session}/decisions/{target_issue_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is False
        assert "timed out" in body["ai_error"]


def test_live_groq_smoke():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        pytest.skip("GROQ_API_KEY environment variable not set, skipping live Groq smoke test.")

    app = create_app()
    client = TestClient(app)
    demo_res = client.post("/api/v1/analysis/demo")
    session_id = demo_res.json()["analysis_id"]

    issues_res = client.get(f"/api/v1/analysis/{session_id}/issues")
    issues = issues_res.json()["issues"]

    if not issues:
        pytest.skip("No issues found in demo dataset for live smoke test.")

    target_issue_id = issues[0]["issue_id"]

    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": key}):
        res = client.post(f"/api/v1/analysis/{session_id}/decisions/{target_issue_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is True
        assert body["reasoning"] is not None
        assert body["verification"]["status"] in ("verified", "partially_verified")
