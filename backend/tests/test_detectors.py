import copy
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.detectors.engine import detect_issues, quartiles
from app.evidence.contract import dataset_identity, display
from app.ingestion.validation import Record, ingest_csv
from app.main import create_app
from app.sessions.store import SessionStore


def daily(values, *, start=date(2026, 1, 1), inventory=100, product="A"):
    return tuple(Record(start + timedelta(days=i), product, f"Product {product}", "Synthetic", units,
                        Decimal("0.01"), inventory, Decimal("99.99"), None, None) for i, units in enumerate(values))


def windows(previous, current, inventory=100):
    # Hand-specified totals; the six zero days are actual observations, not imputation.
    return daily([previous] + [0] * 6 + [current] + [0] * 6, inventory=inventory)


def evaluation(result, family, product="A"):
    return next(e for e in result["evaluations"] if e["issue_type"] == family and e["entity_id"] == product)


def family_issues(result, family):
    return [i for i in result["issues"] if i["issue_type"] == family]


def evidence_for(result, issue):
    return {e["metric"]: e for e in result["evidence"] if e["evidence_id"] in issue["evidence_ids"]}


@pytest.mark.parametrize("previous,current,severity", [(10000, 8001, None), (100, 80, "LOW"),
    (100, 65, "MEDIUM"), (100, 50, "HIGH"), (100, 0, "HIGH"), (100000, 80001, None)])
def test_decline_boundaries_without_display_rounding(previous, current, severity):
    result = detect_issues(windows(previous, current))
    issues = family_issues(result, "demand_decline")
    assert [i["severity"] for i in issues] == ([severity] if severity else [])
    assert evaluation(result, "demand_decline")["status"] == ("issue_detected" if severity else "evaluated_no_issue")
    if severity:
        ev = evidence_for(result, issues[0])
        assert ev["previous_units"]["value"] == previous
        assert ev["current_units"]["value"] == current
        assert ev["absolute_change"]["value"] == current - previous


@pytest.mark.parametrize("previous,current,severity", [(10000, 12499, None), (100, 125, "LOW"),
    (100, 150, "MEDIUM"), (100, 200, "HIGH"), (1, 1000000, "HIGH"), (100000, 124999, None)])
def test_spike_boundaries_without_display_rounding(previous, current, severity):
    result = detect_issues(windows(previous, current))
    assert [i["severity"] for i in family_issues(result, "demand_spike")] == ([severity] if severity else [])


@pytest.mark.parametrize("current", [0, 100])
def test_zero_previous_is_unsupported_not_infinite(current):
    result = detect_issues(windows(0, current))
    for family in ("demand_decline", "demand_spike"):
        assert evaluation(result, family)["reason"] == "zero_previous_demand"
        assert evaluation(result, family)["status"] == "unsupported"
        assert family_issues(result, family) == []


def test_tiny_missing_and_absent_product_history():
    tiny = detect_issues(daily([1]))
    assert evaluation(tiny, "demand_decline")["reason"] == "insufficient_history"
    assert evaluation(tiny, "stockout_risk")["reason"] == "incomplete_daily_coverage"
    rows = windows(100, 20)
    missing = detect_issues(rows[:9] + rows[10:])
    assert evaluation(missing, "demand_decline")["reason"] == "incomplete_daily_coverage"
    combined = detect_issues((*rows, *daily([10] * 7, start=date(2026, 1, 8), product="B")))
    assert evaluation(combined, "demand_spike", "B")["reason"] == "product_missing_in_period"
    assert evaluation(combined, "demand_decline")["status"] == "issue_detected"


@pytest.mark.parametrize("inventory,severity", [(0, "HIGH"), (10, "HIGH"), (11, "MEDIUM"), (29, "MEDIUM"),
    (30, "LOW"), (50, "LOW"), (69, "LOW"), (70, None), (100, None)])
def test_stockout_coverage_boundaries(inventory, severity):
    result = detect_issues(daily([10] * 7, inventory=inventory))
    issues = family_issues(result, "stockout_risk")
    assert [i["severity"] for i in issues] == ([severity] if severity else [])
    if severity:
        ev = evidence_for(result, issues[0])
        assert ev["latest_inventory"]["value"] == inventory
        assert ev["latest_inventory"]["observation_date"] == "2026-01-07"
        assert ev["current_units"]["value"] == 70
        assert ev["recent_daily_demand"]["value"] == "10.00"
        assert Fraction(int(ev["days_of_inventory"]["exact"]["numerator"]), int(ev["days_of_inventory"]["exact"]["denominator"])) == Fraction(inventory, 10)


@pytest.mark.parametrize("inventory,severity", [(299, None), (300, None), (301, "LOW"), (600, "LOW"),
    (601, "MEDIUM"), (900, "MEDIUM"), (901, "HIGH"), (1000000000000, "HIGH")])
def test_excess_boundaries(inventory, severity):
    result = detect_issues(daily([10] * 7, inventory=inventory))
    assert [i["severity"] for i in family_issues(result, "excess_inventory")] == ([severity] if severity else [])


@pytest.mark.parametrize("inventory", [0, 500])
def test_zero_recent_demand_abstains_both_inventory_families(inventory):
    result = detect_issues(daily([0] * 7, inventory=inventory))
    for family in ("stockout_risk", "excess_inventory"):
        assert evaluation(result, family)["reason"] == "zero_recent_demand"
        assert evaluation(result, family)["status"] == "unsupported"


def test_inventory_freshness_precedes_coverage_and_snapshots_are_not_summed():
    rows = daily([10] * 7, inventory=500)
    rows = rows[:-1] + (replace(rows[-1], inventory=0),)
    result = detect_issues(rows)
    assert family_issues(result, "stockout_risk")[0]["severity"] == "HIGH"
    assert not family_issues(result, "excess_inventory")
    stale = detect_issues((*rows, *daily([1], start=date(2026, 1, 8), product="B")))
    for family in ("stockout_risk", "excess_inventory"):
        assert evaluation(stale, family)["reason"] == "stale_inventory_snapshot"


@pytest.mark.parametrize("values,expected", [([1,2,3,4], (Fraction(3,2),Fraction(7,2))),
    ([1,2,3,4,5], (Fraction(3,2),Fraction(9,2))), (list(range(1,15)), (Fraction(4),Fraction(11))),
    (list(range(1,16)), (Fraction(4),Fraction(12))), ([0]*7+[2]*7, (Fraction(0),Fraction(2)))])
def test_quartile_algorithm_even_odd_and_zero_observations(values, expected):
    assert quartiles(values) == expected
    assert quartiles(list(reversed(values))) == expected


def anomaly_rows(targets, baseline=None):
    # Q1=10, Q3=14, IQR=4; fences 4 and 20, from 14 independent baseline days.
    return daily((baseline if baseline is not None else [10]*7+[14]*7) + targets)


@pytest.mark.parametrize("target,severity", [(4,None),(20,None),(21,"LOW"),(26,"LOW"),(27,"MEDIUM"),
    (32,"MEDIUM"),(33,"HIGH"),(0,"LOW"),(10,None),(14,None)])
def test_anomaly_exact_fences_severity_and_observed_zero(target,severity):
    result=detect_issues(anomaly_rows([12]*6+[target]))
    issues=family_issues(result,"sales_anomaly")
    assert [i["severity"] for i in issues] == ([severity] if severity else [])
    if severity:
        ev=evidence_for(result,issues[0])
        assert ev["q1"]["value"] == "10.00"
        assert ev["q3"]["value"] == "14.00"
        assert ev["iqr"]["value"] == "4.00"
        assert ev["baseline_samples"]["value"] == 14
        assert ev["relevant_bound"]["value"] == ("4.00" if target==0 else "20.00")
        assert issues[0]["observation_date"] == "2026-01-21"


def test_multiple_anomalies_exclude_all_targets_from_baseline():
    result=detect_issues(anomaly_rows([33,34,12,12,12,12,0]))
    issues=family_issues(result,"sales_anomaly")
    assert [i["observation_date"] for i in issues] == ["2026-01-15","2026-01-16","2026-01-21"]
    assert [i["severity"] for i in issues] == ["HIGH","HIGH","LOW"]
    assert len({i["issue_id"] for i in issues}) == 3
    for issue in issues:
        assert evidence_for(result,issue)["baseline_samples"]["value"] == 14


@pytest.mark.parametrize("baseline,reason", [([10]*14,"zero_iqr"),([0]*14,"zero_iqr"),([10]*13,"insufficient_anomaly_samples")])
def test_constant_and_small_baselines_abstain(baseline,reason):
    result=detect_issues(anomaly_rows([100]*7,baseline))
    assert evaluation(result,"sales_anomaly")["reason"] == reason
    assert not family_issues(result,"sales_anomaly")


def test_anomaly_missing_current_day_and_calendar_boundary():
    rows=anomaly_rows([12]*6+[33])
    result=detect_issues(rows[:16]+rows[17:])
    assert evaluation(result,"sales_anomaly")["reason"] == "incomplete_daily_coverage"
    result=detect_issues(daily([1],start=date(1,1,1)))
    assert all(e["reason"] == "date_boundary" for e in result["evaluations"])
    assert result["detection_period"] is None


def test_exact_ratios_near_inventory_thresholds_and_rounding_ties():
    # Coverage rounds to 30.00, but is strictly above 30 and must flag.
    result=detect_issues(windows(100,700000,inventory=3000001))
    issue=family_issues(result,"excess_inventory")[0]
    assert issue["severity"] == "LOW"
    assert evidence_for(result,issue)["days_of_inventory"]["value"] == "30.00"
    assert display(Fraction(1,8)) == "0.13"
    assert display(Fraction(-1,8)) == "-0.13"
    assert display(Fraction(-1,10000)) == "0.00"


def test_deterministic_identity_order_provenance_links_and_immutability():
    rows=(*anomaly_rows([33,34,12,12,12,12,0]),*daily([10]*14,product="B",inventory=0))
    original=copy.deepcopy(rows)
    result=detect_issues(rows)
    with localcontext() as ctx:
        ctx.prec=3
        assert detect_issues(tuple(reversed(rows))) == result
    assert rows == original
    assert len({i["issue_id"] for i in result["issues"]}) == len(result["issues"])
    ev={e["evidence_id"]: e for e in result["evidence"]}
    references={key for i in result["issues"] for key in i["evidence_ids"]}
    assert references == set(ev)
    for issue in result["issues"]:
        for key in issue["evidence_ids"]:
            assert ev[key]["entity_id"] == issue["entity_id"]
            assert ev[key]["detector_version"] == issue["detector_version"]
            assert ev[key]["source"]["kind"] in {"observed","aggregated","derived"}
            assert ev[key]["source"]["name"] != "dataset"
        assert issue["detected_at"] == "2026-01-21"
    assert [e["evidence_id"] for e in result["evidence"]] == sorted(ev)
    assert json.loads(json.dumps(result,allow_nan=False)) == result
    changed=detect_issues((replace(rows[0],revenue=Decimal("0.02")),*rows[1:]))
    assert {i["issue_id"] for i in changed["issues"]}.isdisjoint({i["issue_id"] for i in result["issues"]})
    assert {e["evidence_id"] for e in changed["evidence"]}.isdisjoint(ev)
    # Normalized Decimal representation does not alter content identity.
    assert dataset_identity(rows) == dataset_identity(tuple(replace(r,revenue=Decimal("0.010")) for r in rows))


def test_summaries_are_rendered_only_from_attached_evidence():
    rows=(*anomaly_rows([33]*7),*daily([0]*7+[10]*7,product="B",inventory=0))
    result=detect_issues(rows)
    for issue in result["issues"]:
        ev={name:e["value"] for name,e in evidence_for(result,issue).items()}
        if issue["issue_type"] in {"demand_decline","demand_spike"}:
            expected=f"Observed units changed from {ev['previous_units']} to {ev['current_units']}: {ev['absolute_change']} units; {ev['percentage_change']}% (rounded)."
        elif issue["issue_type"] in {"stockout_risk","excess_inventory"}:
            expected=f"Latest inventory is {ev['latest_inventory']} units; recent daily demand is {ev['recent_daily_demand']} units/day and stock coverage is {ev['days_of_inventory']} days (ratios rounded)."
        else:
            expected=f"Observed daily units {ev['observed_units']} are outside the relevant IQR bound {ev['relevant_bound']}, from {ev['baseline_samples']} baseline observations."
        assert issue["summary"] == expected


def test_api_determinism_isolation_expiry_release_and_no_store(monkeypatch):
    now=[0.0]
    store=SessionStore(clock=lambda:now[0])
    with TestClient(create_app(session_store=store)) as client:
        assert client.get('/api/v1/analysis/unknown/issues').status_code == 404
        first=client.post('/api/v1/analysis/demo').json()
        key=first['analysis_id']
        original=copy.deepcopy(store.get(key).dataset)
        response=client.get(f'/api/v1/analysis/{key}/issues',headers={'Origin':'http://localhost:5173'})
        body=response.json()
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
        assert client.get(f'/api/v1/analysis/{key}/issues').json() == body
        assert body['expires_at'] == first['expires_at']
        assert store.get(key).dataset == original
        second=client.post('/api/v1/analysis/demo').json()['analysis_id']
        assert second != key
        assert client.get(f'/api/v1/analysis/{second}/issues').json()['issues'] == body['issues']
        client.delete(f'/api/v1/analysis/{key}')
        assert client.get(f'/api/v1/analysis/{key}/issues').json()['error']['code'] == 'analysis_unavailable'
        assert client.get(f'/api/v1/analysis/{second}/issues').status_code == 200
        now[0]=1800
        assert client.get(f'/api/v1/analysis/{second}/issues').status_code == 404
        third=client.post('/api/v1/analysis/demo').json()['analysis_id']
        def expire(records):
            result=detect_issues(records)
            now[0]+=1800
            return result
        monkeypatch.setattr('app.analysis.detect_issues',expire)
        assert client.get(f'/api/v1/analysis/{third}/issues').status_code == 404


def test_demo_rules_and_frozen_revenue():
    records=ingest_csv((Path(__file__).parents[2]/'data'/'demo_business.csv').read_bytes()).records
    result=detect_issues(records)
    assert len(result['evaluations']) == 30
    assert all(e['source']['name'] != 'unit_price' for e in result['evidence'])
    assert all(e['unit'] != 'currency' for e in result['evidence'])
    assert [(i['entity_id'], i['issue_type'], i['severity']) for i in result['issues']] == [
        ('P-002','stockout_risk','HIGH'), ('P-003','excess_inventory','LOW'), ('P-005','stockout_risk','LOW')]


def test_all_families_fixture_has_hand_verified_conditions():
    payload=(Path(__file__).parent/'fixtures'/'detectors_business.csv').read_bytes()
    result=detect_issues(ingest_csv(payload).records)
    assert [(i['entity_id'],i['issue_type'],i['severity']) for i in result['issues']] == [
        ('Anomaly','sales_anomaly','HIGH'), ('Decline','demand_decline','MEDIUM'),
        ('Excess','excess_inventory','HIGH'), ('Spike','demand_spike','MEDIUM'), ('Stockout','stockout_risk','HIGH')]
    anomaly=evidence_for(result,result['issues'][0])
    assert anomaly['observed_units']['value'] == 40
    assert anomaly['relevant_bound']['value'] == '20.00'
    assert anomaly['baseline_samples']['value'] == 28
    assert anomaly['quartile_distance']['value'] == '6.50'
    decline=evidence_for(result,result['issues'][1])
    assert decline['previous_units']['value'] == 70
    assert decline['current_units']['value'] == 42
    assert decline['percentage_change']['value'] == '-40.00'
    assert evidence_for(result,result['issues'][2])['days_of_inventory']['value'] == '100.00'
    assert evidence_for(result,result['issues'][3])['percentage_change']['value'] == '60.00'


def test_release_during_calculation_and_changed_content_cannot_reuse_session(monkeypatch):
    with TestClient(create_app()) as client:
        key=client.post('/api/v1/analysis/demo').json()['analysis_id']
        def release(records):
            client.app.state.sessions.delete(key)
            return detect_issues(records)
        monkeypatch.setattr('app.analysis.detect_issues',release)
        response=client.get(f'/api/v1/analysis/{key}/issues')
        assert response.status_code == 404
        assert not client.app.state.sessions._sessions


def test_extreme_sparse_dates_bounded_and_no_invented_history():
    rows=(*daily([1],start=date(1,1,1)),*daily([1],start=date(9999,12,31)))
    result=detect_issues(rows)
    assert len(result['evaluations']) == 5
    assert result['issues'] == result['evidence'] == []
    assert all(e['status']=='unsupported' for e in result['evaluations'])


def test_inventory_one_day_rounding_does_not_escalate_severity():
    # 1.00001 days serializes as 1.00 but belongs to MEDIUM, not HIGH.
    result=detect_issues(windows(100,700000,inventory=100001))
    issue=family_issues(result,'stockout_risk')[0]
    assert issue['severity']=='MEDIUM'
    assert evidence_for(result,issue)['days_of_inventory']['value']=='1.00'


def test_json_identity_disambiguates_entity_labels_and_escapes_untrusted_text():
    rows=(*daily([10]*7,product='A:B',inventory=0),*daily([10]*7,product='A',inventory=0))
    rows=tuple(replace(r,product_name='<script>42</script> {current_units}') for r in rows)
    result=detect_issues(rows)
    assert len({i['issue_id'] for i in result['issues']})==2
    assert len({e['evidence_id'] for e in result['evidence']})==8
    assert all('<script>' not in i['summary'] for i in result['issues'])


def test_maximum_row_count_and_integer_bound_are_json_safe():
    rows=tuple(daily([1000000000000],product=str(i),inventory=1000000000000)[0] for i in range(10000))
    result=detect_issues(rows)
    assert len(result['evaluations'])==50000
    assert result['issues']==result['evidence']==[]
    json.dumps(result,allow_nan=False)
