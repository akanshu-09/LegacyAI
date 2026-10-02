"""Exercise actual detector evidence through Groq serialization, without network."""

import asyncio
import copy
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.evidence.contract import EvidenceBuilder
from app.main import create_app
from app.reasoning.provider import GroqDecisionReasoner, ProviderSchemaError, normalize_evidence


def evidence(value):
    builder = EvidenceBuilder("synthetic-test-dataset")
    builder.add(entity_id="A", detector_version="stockout_risk_v1", metric="test_units", value=value,
                unit="units", period={"start": "2026-01-01", "end": "2026-01-07", "calendar_days": 7},
                comparison_period={"start": "2025-12-25", "end": "2025-12-31", "calendar_days": 7},
                method="Synthetic test input", source={"name": "latest_inventory_snapshot", "kind": "observed"},
                inputs={"units": "0"}, observation_date="2026-01-07")
    return next(iter(builder.items.values()))


@pytest.mark.parametrize("input_value,expected,readable", [
    (0, 0, "0"), (73, 73, "73"), (-28, -28, "-28"),
    (2**53, "9007199254740992", "9007199254740992"),
    (Fraction(0), "0.00", "0.00"), (Fraction(1, 8), "0.13", "0.13"),
    (Fraction(-1, 8), "-0.13", "-0.13"), (Decimal("0.10"), "0.10", "0.10"),
])
def test_canonical_runtime_values_keep_types_exact_facts_and_provenance(input_value, expected, readable):
    original = evidence(input_value)
    before = copy.deepcopy(original)
    result = normalize_evidence([original])[0]
    assert result["value"] == expected
    assert type(result["value"]) is type(expected)
    assert result["display_string"] == readable
    assert {k: v for k, v in result.items() if k != "display_string"} == original
    assert original == before  # No provider mutation of deterministic/verifier evidence.
    assert result["exact"] == {"numerator": str(Fraction(input_value).numerator), "denominator": str(Fraction(input_value).denominator)}
    assert result["source"] == {"name": "latest_inventory_snapshot", "kind": "observed"}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value", [None, True, False, 0.0, float('nan'), float('inf'),
                                  {"display_string": "0"}, [], "NaN", "Infinity", "not a number",
                                  Decimal("0.10"), Fraction(1, 7)])
def test_noncanonical_values_fail_explicitly_without_stringifying(value):
    ev = evidence(0)
    ev["value"] = value
    with pytest.raises(ProviderSchemaError, match="unsupported value"):
        normalize_evidence([ev])


def test_missing_value_is_not_fabricated_zero():
    ev = evidence(0)
    del ev["value"]
    with pytest.raises(ProviderSchemaError):
        normalize_evidence([ev])


@pytest.fixture
def groq_transport(monkeypatch):
    """Real provider + HTTPX serialization, mocked only at HTTP transport."""
    captured = []
    extra_citations = []
    original_client = httpx.AsyncClient

    def handler(request):
        payload = json.loads(request.content)
        prompt = payload['messages'][1]['content'].split('\n', 1)[1]
        context = json.loads(prompt)
        captured.append(context)
        ids = [ev['evidence_id'] for ev in context['verified_evidence']] + extra_citations
        reasoning = {
            'summary': 'Review the supplied inventory evidence.',
            'root_causes': [{'explanation': 'The observed stock condition warrants review.', 'evidence_ids': ids[:1]}],
            'recommendation': {'action': 'Review replenishment assumptions.', 'target': 'Harbor Pen Set', 'timeframe_days': 14},
            'assumptions': [], 'uncertainties': ['Incoming receipts are not recorded.'],
            'what_would_change_this_decision': [], 'evidence_ids': ids, 'abstain': False,
        }
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(reasoning)}}]})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    reasoner = GroqDecisionReasoner(api_key='synthetic-unit-test-key')
    monkeypatch.setattr('app.analysis.get_reasoner', lambda: reasoner)
    return captured, extra_citations, reasoner


@pytest.mark.parametrize("route", ['decisions_path', 'decisions_body', 'ask'])
def test_real_demo_harbor_zero_inventory_reaches_groq_and_verifier(groq_transport, route):
    captured, _, _ = groq_transport
    with TestClient(create_app()) as client:
        aid = client.post('/api/v1/analysis/demo').json()['analysis_id']
        base = f'/api/v1/analysis/{aid}'
        detection = client.get(base+'/issues').json()
        issue = next(i for i in detection['issues'] if i['entity_id'] == 'P-002' and i['issue_type'] == 'stockout_risk')
        expected = [e for e in detection['evidence'] if e['evidence_id'] in issue['evidence_ids']]
        snapshot = next(e for e in expected if e['metric'] == 'latest_inventory')
        assert snapshot['value'] == 0 and type(snapshot['value']) is int
        if route == 'decisions_path':
            response = client.post(base+'/decisions/'+issue['issue_id'])
        elif route == 'decisions_body':
            response = client.post(base+'/decisions', json={'issue_id': issue['issue_id']})
        else:
            response = client.post(base+'/ask', json={'question': 'What are our top inventory risks?'})
        assert response.status_code == 200
        result = response.json()
        assert result['ai_available'] is True
        assert result['verification']['status'] == 'verified'
        assert set(result['verification']['valid_citations']) == set(issue['evidence_ids'])
        assert len(captured) == 1
        received = captured[0]['verified_evidence']
        assert [{k: v for k, v in e.items() if k != 'display_string'} for e in received] == expected
        assert next(e for e in received if e['metric'] == 'latest_inventory')['display_string'] == '0'
        assert next(e for e in received if e['metric'] == 'days_of_inventory')['display_string'] == '0.00'
        returned_evidence = result['cited_evidence'] if route != 'ask' else result['evidence']
        assert returned_evidence == expected  # Verifier/API keep original canonical evidence.


def test_all_detector_families_serialize_and_preserve_evidence(groq_transport):
    captured, _, reasoner = groq_transport
    from app.detectors.engine import detect_issues
    from app.ingestion.validation import ingest_csv
    from app.verification.verifier import verify_claims
    fixture = Path(__file__).parent/'fixtures'/'detectors_business.csv'
    detection = detect_issues(ingest_csv(fixture.read_bytes()).records)
    assert {i['issue_type'] for i in detection['issues']} == {'stockout_risk', 'excess_inventory', 'demand_decline', 'demand_spike', 'sales_anomaly'}
    for issue in detection['issues']:
        selected = [e for e in detection['evidence'] if e['evidence_id'] in issue['evidence_ids']]
        reasoning = asyncio.run(reasoner.generate_decision(issue, selected))
        assert verify_claims(reasoning, issue, selected).status == 'verified'
        assert captured[-1]['verified_evidence'] == normalize_evidence(selected)


def test_unknown_groq_citation_remains_unverified(groq_transport):
    _, unknown, _ = groq_transport
    unknown.append('EV-UNKNOWN')
    with TestClient(create_app()) as client:
        aid = client.post('/api/v1/analysis/demo').json()['analysis_id']
        issue = client.get(f'/api/v1/analysis/{aid}/issues').json()['issues'][0]
        response = client.post(f'/api/v1/analysis/{aid}/decisions/{issue["issue_id"]}')
        assert response.status_code == 200
        assert response.json()['verification']['status'] == 'partially_verified'
        assert response.json()['verification']['invalid_citations'] == ['EV-UNKNOWN']


def test_invalid_value_degrades_without_network_or_internal_exception(groq_transport, monkeypatch):
    captured, _, _ = groq_transport
    from app import analysis
    original = analysis.detect_issues
    def invalid_detection(records):
        result = original(records)
        for ev in result['evidence']:
            ev['value'] = None
        return result
    monkeypatch.setattr(analysis, 'detect_issues', invalid_detection)
    with TestClient(create_app()) as client:
        aid = client.post('/api/v1/analysis/demo').json()['analysis_id']
        issue = client.get(f'/api/v1/analysis/{aid}/issues').json()['issues'][0]
        response = client.post(f'/api/v1/analysis/{aid}/decisions/{issue["issue_id"]}')
        assert response.status_code == 200
        assert response.json()['ai_available'] is False
        assert response.json()['verification']['status'] == 'unverified'
        assert response.json()['ai_error'] == 'Verified evidence has an unsupported value type or format.'
        assert not captured


def test_httpx_is_pinned_in_production_requirements():
    root = Path(__file__).resolve().parents[1]
    assert 'httpx==0.28.1' in (root/'requirements.txt').read_text().splitlines()
    assert '-r requirements.txt' in (root/'requirements-dev.txt').read_text().splitlines()
