"""Adversarial and functional unit/integration tests for Phase 5 Ask LegacyAI."""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ask.intent import classify_intent
from app.reasoning.provider import MockDecisionReasoner, ProviderTimeoutError


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def demo_session(client):
    res = client.post("/api/v1/analysis/demo")
    assert res.status_code == 201
    return res.json()["analysis_id"]


def test_classify_intent_supported():
    intent_overview = classify_intent("Give me a high level business overview")
    assert intent_overview.intent_type == "business_overview"
    assert intent_overview.supported is True

    intent_risks = classify_intent("What are our top inventory risks?")
    assert intent_risks.intent_type == "inventory_risk"
    assert intent_risks.supported is True

    intent_recommend = classify_intent("What action should we take next?")
    assert intent_recommend.intent_type == "recommend_action"
    assert intent_recommend.supported is True


def test_classify_intent_unsupported():
    intent_profit = classify_intent("What is our total profit margin this month?")
    assert intent_profit.intent_type == "unsupported"
    assert intent_profit.supported is False
    assert "profit" in intent_profit.reason.lower()

    intent_ml = classify_intent("Use neural network forecast to predict next year sales")
    assert intent_ml.intent_type == "unsupported"
    assert intent_ml.supported is False

    intent_emp = classify_intent("Show employee salaries")
    assert intent_emp.intent_type == "unsupported"
    assert intent_emp.supported is False


def test_ask_endpoint_supported_mock(client, demo_session):
    with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
        res = client.post(
            f"/api/v1/analysis/{demo_session}/ask",
            json={"question": "What are our top inventory risks?"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is True
        assert body["intent"]["supported"] is True
        assert "factual_finding" in body
        assert "finding" in body["factual_finding"]
        assert body["verification"]["status"] == "verified"


def test_ask_endpoint_unsupported_abstain(client, demo_session):
    res = client.post(
        f"/api/v1/analysis/{demo_session}/ask",
        json={"question": "What is our net profit margin?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"]["supported"] is False
    assert body["intent"]["intent_type"] == "unsupported"
    assert "abstained" in body["explanation"].lower()
    assert body["verification"]["status"] == "verified"


def test_ask_endpoint_empty_question(client, demo_session):
    res = client.post(
        f"/api/v1/analysis/{demo_session}/ask",
        json={"question": "   "}
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_request_body"


def test_ask_endpoint_expired_session(client):
    res = client.post(
        "/api/v1/analysis/INVALID-SESSION/ask",
        json={"question": "Business overview"}
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "analysis_unavailable"


def test_ask_endpoint_provider_failure_degradation(client, demo_session):
    mock_reasoner = MockDecisionReasoner(should_fail_with=ProviderTimeoutError("Groq request timed out."))
    with patch("app.analysis.get_reasoner", return_value=mock_reasoner):
        res = client.post(
            f"/api/v1/analysis/{demo_session}/ask",
            json={"question": "Summarize business performance"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ai_available"] is False
        assert "timed out" in body["ai_error"]
        assert body["factual_finding"]["finding"] is not None
