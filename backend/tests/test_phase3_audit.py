"""Independent adversarial expectations for the final Phase 3 audit."""
import csv
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from statistics import median_low, median_high

import pytest
from fastapi.testclient import TestClient

from app.detectors.engine import detect_issues, quartiles
from app.evidence import contract
from app.ingestion.validation import Record, ingest_csv
from app.main import create_app


def rows(values, *, start=date(2026, 1, 1), product="A", inventory=100):
    return tuple(Record(start + timedelta(days=i), product, product, "Test", value,
                        Decimal("0.01"), inventory, Decimal("99.99"), None, None)
                 for i, value in enumerate(values))


def get_evaluation(result, family, product="A"):
    return next(e for e in result["evaluations"] if e["issue_type"] == family and e["entity_id"] == product)


@pytest.mark.parametrize("family,current,expected", [
    ("demand_decline", 8001, None), ("demand_decline", 8000, "LOW"),
    ("demand_decline", 6501, "LOW"), ("demand_decline", 6500, "MEDIUM"),
    ("demand_decline", 5001, "MEDIUM"), ("demand_decline", 5000, "HIGH"),
    ("demand_spike", 12499, None), ("demand_spike", 12500, "LOW"),
    ("demand_spike", 14999, "LOW"), ("demand_spike", 15000, "MEDIUM"),
    ("demand_spike", 19999, "MEDIUM"), ("demand_spike", 20000, "HIGH"),
])
def test_requested_demand_hundredth_percent_boundaries(family, current, expected):
    # B=10000: each unit difference is exactly .01 percentage points.
    result = detect_issues(rows([10000] + [0]*6 + [current] + [0]*6))
    issues = [i for i in result["issues"] if i["issue_type"] == family]
    assert [i["severity"] for i in issues] == ([expected] if expected else [])
    assert get_evaluation(result, family)["status"] == ("issue_detected" if expected else "evaluated_no_issue")


@pytest.mark.parametrize("inventory,expected", [(0,"HIGH"),(100000,"HIGH"),(100001,"MEDIUM"),
    (299999,"MEDIUM"),(300000,"LOW"),(699999,"LOW"),(700000,None),(700001,None)])
def test_stockout_boundaries_with_nearby_exact_ratios(inventory, expected):
    result = detect_issues(rows([100000]*7, inventory=inventory))
    assert [i["severity"] for i in result["issues"] if i["issue_type"] == "stockout_risk"] == ([expected] if expected else [])


@pytest.mark.parametrize("inventory,expected", [(3000000,None),(3000001,"LOW"),(6000000,"LOW"),
    (6000001,"MEDIUM"),(9000000,"MEDIUM"),(9000001,"HIGH")])
def test_excess_strict_boundaries(inventory, expected):
    result = detect_issues(rows([100000]*7, inventory=inventory))
    assert [i["severity"] for i in result["issues"] if i["issue_type"] == "excess_inventory"] == ([expected] if expected else [])


def test_inventory_one_day_stale_is_visible_in_support_metadata():
    product = rows([10]*14, inventory=0)
    newer = rows([1], start=date(2026,1,15), product="B")
    result = detect_issues(product + newer)
    for family in ("stockout_risk", "excess_inventory"):
        e = get_evaluation(result, family)
        assert e["status"] == "unsupported"
        assert e["reason"] == "stale_inventory_snapshot"
        assert e["inventory_observation_date"] == "2026-01-14"
        assert e["period"]["end"] == "2026-01-15"


@pytest.mark.parametrize("baseline,q1,q3", [
    ([0,0,1,1,2,2,3,4,5,5,6,6,7,8], Fraction(1), Fraction(6)),
    ([0,0,1,1,2,2,3,4,5,5,6,6,7,8,9], Fraction(1), Fraction(6)),
    (list(range(16)), Fraction(7,2), Fraction(23,2)),
    ([0]*14, Fraction(0), Fraction(0)),
])
def test_independent_quartile_examples(baseline, q1, q3):
    assert quartiles(baseline) == (q1,q3)


def test_baseline_is_28_calendar_days_not_28_records_and_no_imputation():
    # Dataset E=Feb 4 => baseline Jan 1–28. Thirteen old outliers must be excluded.
    old = rows([999]*13, start=date(2025,12,19))
    sparse = tuple(replace(r, date=date(2026,1,1)+timedelta(days=2*i))
                   for i,r in enumerate(rows([10]*7+[14]*7)))
    target = rows([12]*6+[40], start=date(2026,1,29))
    result = detect_issues(old+sparse+target)
    e = get_evaluation(result,"sales_anomaly")
    assert e["baseline_sample_count"] == 14
    assert e["comparison_period"] == {"start":"2026-01-01","end":"2026-01-28","calendar_days":28}
    anomaly = next(i for i in result["issues"] if i["issue_type"] == "sales_anomaly")
    values = {v["metric"]:v["value"] for v in result["evidence"] if v["evidence_id"] in anomaly["evidence_ids"]}
    assert (values["q1"],values["q3"],values["iqr"],values["baseline_samples"]) == ("10.00","14.00","4.00",14)
    result = detect_issues(old+sparse[:-1]+target)
    assert get_evaluation(result,"sales_anomaly")["reason"] == "insufficient_anomaly_samples"
    assert get_evaluation(result,"sales_anomaly")["baseline_sample_count"] == 13


@pytest.mark.parametrize("value,severity", [(16,None),(15,"LOW"),(10,"LOW"),(9,"MEDIUM"),
    (4,"MEDIUM"),(3,"HIGH"),(32,None),(33,"LOW"),(38,"LOW"),(39,"MEDIUM"),(44,"MEDIUM"),(45,"HIGH")])
def test_lower_and_upper_anomaly_fences_and_severity(value,severity):
    # Q1=22, Q3=26, IQR=4: fences16/32; distances 3 at10/38, 4.5 at4/44.
    baseline = [22]*7+[26]*7
    result = detect_issues(rows(baseline+[24]*6+[value]))
    assert [i["severity"] for i in result["issues"] if i["issue_type"] == "sales_anomaly"] == ([severity] if severity else [])


def evidence_args():
    return {"entity_id":"A","detector_version":"stockout_risk_v1","metric":"days_of_inventory",
            "value":Fraction(100001,100000),"unit":"days","period":{"start":"2026-01-01","end":"2026-01-07"},
            "method":"inventory * 7 / current_units","source":{"kind":"derived","name":"detector_calculation"},
            "inputs":{"inventory":"100001","current_units":"700000","window_days":"7"},
            "observation_date":"2026-01-07"}


def test_identity_is_independent_of_display_strings_and_evidence_order(monkeypatch):
    builder = contract.EvidenceBuilder("dataset-scope")
    first = builder.add(**evidence_args())
    monkeypatch.setattr(contract,"display",lambda value: "1.00001000")
    second = contract.EvidenceBuilder("dataset-scope").add(**evidence_args())
    assert first == second
    assert first == contract.EvidenceBuilder("dataset-scope").add(**{**evidence_args(),"method":"Equivalent human-readable method wording"})
    body = {"issue_type":"stockout_risk","entity_type":"product","entity_id":"A","entity_name":"Alpha",
            "severity":"MEDIUM","detected_at":"2026-01-07","observation_date":None,
            "detector_version":"stockout_risk_v1","title":"Stockout risk","summary":"Coverage 1.00 days (rounded).",
            "evidence_ids":[first,"ev_other"]}
    a = builder.issue(body)["issue_id"]
    b = builder.issue({**body,"summary":"Coverage 1.00001000 days (rounded).","evidence_ids":list(reversed(body["evidence_ids"]))})["issue_id"]
    assert a == b


@pytest.mark.parametrize("change", [
    {"entity_id":"B"}, {"detector_version":"stockout_risk_v2"}, {"metric":"other_metric"},
    {"observation_date":"2026-01-06"}, {"period":{"start":"2025-12-31","end":"2026-01-06"}},
    {"value":Fraction(100002,100000)}, {"unit":"other_unit"},
])
def test_evidence_identity_separates_semantic_changes_even_when_display_equal(change):
    builder = contract.EvidenceBuilder("scope")
    first = builder.add(**evidence_args())
    second = builder.add(**{**evidence_args(),**change})
    assert first != second


def test_canonical_identity_ignores_dictionary_insertion_order():
    original = evidence_args()
    reversed_args = dict(reversed(list(original.items())))
    reversed_args["period"] = dict(reversed(list(original["period"].items())))
    reversed_args["inputs"] = dict(reversed(list(original["inputs"].items())))
    builder = contract.EvidenceBuilder("scope")
    assert builder.add(**original) == builder.add(**reversed_args)
    assert contract.canonical_hash({"x":1,"y":{"a":2,"b":3}}) == contract.canonical_hash({"y":{"b":3,"a":2},"x":1})


def test_fixture_referential_integrity_and_exact_family_trace():
    records = ingest_csv((Path(__file__).parent/"fixtures"/"detectors_business.csv").read_bytes()).records
    result = detect_issues(records)
    assert detect_issues(tuple(reversed(records))) == detect_issues(records) == result
    evidence = {e["evidence_id"]:e for e in result["evidence"]}
    issues = {i["issue_id"]:i for i in result["issues"]}
    assert len(evidence) == len(result["evidence"])
    assert len(issues) == len(result["issues"])
    assert {key for i in issues.values() for key in i["evidence_ids"]} == set(evidence)
    for i in issues.values():
        attached = {evidence[key]["metric"]:evidence[key] for key in i["evidence_ids"]}
        assert all(e["entity_id"] == i["entity_id"] and e["detector_version"] == i["detector_version"] for e in attached.values())
        product = [r for r in records if r.product_id == i["entity_id"]]
        if i["issue_type"] in ("demand_decline","demand_spike"):
            prior = sum(r.units_sold for r in product if date(2026,1,22)<=r.date<=date(2026,1,28))
            current = sum(r.units_sold for r in product if date(2026,1,29)<=r.date<=date(2026,2,4))
            assert attached["previous_units"]["value"] == prior == 70
            assert attached["current_units"]["value"] == current
            assert attached["percentage_change"]["exact"] == {"numerator":str((current-prior)*100//prior),"denominator":"1"}
        elif i["issue_type"] in ("stockout_risk","excess_inventory"):
            latest = max(product,key=lambda r:r.date)
            total = sum(r.units_sold for r in product if r.date>=date(2026,1,29))
            assert attached["latest_inventory"]["value"] == latest.inventory
            assert attached["current_units"]["value"] == total == 70
            assert attached["days_of_inventory"]["exact"] == {"numerator":str(latest.inventory//10),"denominator":"1"}
        else:
            assert attached["observed_units"]["value"] == 40
            assert attached["observed_units"]["observation_date"] == "2026-02-04"
            assert attached["q1"]["exact"] == {"numerator":"10","denominator":"1"}
            assert attached["q3"]["exact"] == {"numerator":"14","denominator":"1"}
            assert attached["iqr"]["exact"] == {"numerator":"4","denominator":"1"}
            assert attached["relevant_bound"]["exact"] == {"numerator":"20","denominator":"1"}
    assert json.loads(json.dumps(result,allow_nan=False)) == result


@pytest.mark.parametrize("change", [
    {"entity_id":"B"}, {"detector_version":"stockout_risk_v2"}, {"issue_type":"excess_inventory"},
    {"observation_date":"2026-01-06"}, {"detected_at":"2026-01-08"},
    {"evidence_ids":["ev_different_period"]}, {"severity":"HIGH"},
])
def test_issue_identity_separates_semantic_changes(change):
    builder=contract.EvidenceBuilder("scope")
    body={"issue_type":"stockout_risk","entity_type":"product","entity_id":"A","entity_name":"A",
          "severity":"MEDIUM","detected_at":"2026-01-07","observation_date":"2026-01-07",
          "detector_version":"stockout_risk_v1","title":"Stockout risk","summary":"Summary","evidence_ids":["ev_period"]}
    assert builder.issue(body)["issue_id"] != builder.issue({**body,**change})["issue_id"]


def test_demo_independent_raw_csv_oracle_and_absence_of_other_findings():
    payload=(Path(__file__).parents[2]/"data"/"demo_business.csv").read_bytes()
    raw=list(csv.DictReader(payload.decode().splitlines()))
    expected_coverage={"P-002":Fraction(0),"P-003":Fraction(5796,101),"P-005":Fraction(126,37)}
    for pid in sorted({r["product_id"] for r in raw}):
        product=[r for r in raw if r["product_id"]==pid]
        previous=[int(r["units_sold"]) for r in product if "2026-03-18"<=r["date"]<="2026-03-24"]
        current=[int(r["units_sold"]) for r in product if "2026-03-25"<=r["date"]<="2026-03-31"]
        change=Fraction((sum(current)-sum(previous))*100,sum(previous))
        assert len(previous)==len(current)==7
        assert -20 < change < 25  # Independently rules out both demand conditions.
        baseline=sorted(int(r["units_sold"]) for r in product if "2026-02-25"<=r["date"]<="2026-03-24")
        assert len(baseline)==28
        lower_half,upper_half=baseline[:14],baseline[14:]
        q1=Fraction(median_low(lower_half)+median_high(lower_half),2)
        q3=Fraction(median_low(upper_half)+median_high(upper_half),2)
        assert q3 > q1
        assert all(q1-Fraction(3,2)*(q3-q1) <= value <= q3+Fraction(3,2)*(q3-q1) for value in current)
        if pid in expected_coverage:
            inventory=int(max(product,key=lambda r:r["date"])["inventory"])
            assert Fraction(inventory*7,sum(current))==expected_coverage[pid]
    result=detect_issues(ingest_csv(payload).records)
    assert {(i["entity_id"],i["issue_type"],i["severity"]) for i in result["issues"]} == {
        ("P-002","stockout_risk","HIGH"),("P-003","excess_inventory","LOW"),("P-005","stockout_risk","LOW")}
    assert all(e["status"] != "unsupported" for e in result["evaluations"])


def test_api_exposes_unsupported_without_raw_normalized_rows():
    # Seven real zero-demand observations, fresh stock: all five rules must abstain.
    payload="date,product_id,product_name,category,units_sold,revenue,inventory,unit_price\n"
    payload += "".join(f"2026-01-{day:02},A,A,Test,0,0.00,100,1.00\n" for day in range(1,8))
    with TestClient(create_app()) as client:
        profile=client.post("/api/v1/analysis/upload",content=payload.encode(),headers={"Content-Type":"text/csv"}).json()
        body=client.get(f"/api/v1/analysis/{profile['analysis_id']}/issues").json()
        assert body["expires_at"] == profile["expires_at"]
        assert body["issues"] == body["evidence"] == []
        assert len(body["evaluations"]) == 5
        assert all(e["status"] == "unsupported" and e["reason"] for e in body["evaluations"])
        assert get_evaluation(body,"stockout_risk")["reason"] == "zero_recent_demand"
        assert get_evaluation(body,"excess_inventory")["reason"] == "zero_recent_demand"
        assert set(body)=={"analysis_id","expires_at","detector_schema_version","issue_schema_version",
                           "evidence_schema_version","detection_period","issues","evidence","evaluations"}
