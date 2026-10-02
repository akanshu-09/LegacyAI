"""Independent unit arithmetic and lifecycle/contract regressions for Phase 6."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.validation import Record, ingest_csv, AnalysisError
from app.main import create_app
from app.sessions.store import SessionStore
from app.simulation.engine import SimulationInput, display, simulate, simulation_options


def records(*, units=10, inventory=100, end=date(2026, 1, 7), product="A"):
    return tuple(Record(end - timedelta(days=6-i), product, product, "Synthetic", units,
                        Decimal("0.01"), inventory, Decimal("999.99"), None, None) for i in range(7))


def inputs(**overrides):
    return SimulationInput(**({"product_id": "A", "baseline_reorder_quantity": 100,
                              "reorder_adjustment_percent": 0, "demand_change_percent": 0,
                              "horizon_days": 14} | overrides))


def exact(metric):
    return Fraction(int(metric["exact"]["numerator"]), int(metric["exact"]["denominator"]))


def test_unchanged_baseline_and_hand_calculated_scenario():
    rows = records()
    unchanged = simulate(rows, inputs())
    assert unchanged["baseline"] == unchanged["scenario"]
    assert all(exact(value) == 0 for value in unchanged["comparison"].values())
    # U=70, d=10; baseline I100+Q100-P140=60, remaining6.
    # scenario Q150, d13, P182, J68, remaining68/13.
    result = simulate(rows, inputs(reorder_adjustment_percent=50, demand_change_percent=30))
    before, after = result["baseline"], result["scenario"]
    assert exact(before["projected_demand"]) == 140
    assert exact(before["projected_ending_inventory"]) == 60
    assert exact(before["days_inventory_remaining"]) == 6
    assert exact(after["assumed_receipt_quantity"]) == 150
    assert exact(after["projected_demand"]) == 182
    assert exact(after["projected_ending_inventory"]) == 68
    assert exact(after["days_inventory_remaining"]) == Fraction(68, 13)
    assert after["days_inventory_remaining"]["value"] == "5.23"
    assert exact(result["comparison"]["days_inventory_remaining"]) == Fraction(-10, 13)
    assert exact(result["comparison"]["projected_demand"]) == 42
    assert after["potential_stockout"]["value"] is False
    assert after["potential_excess_stock"]["value"] is False
    assert result["hypothetical"] is True


@pytest.mark.parametrize("horizon", [7, 14, 30])
@pytest.mark.parametrize("a,b", [(-50, -30), (50, 30), (-50, 30), (50, -30)])
def test_control_boundaries_exact_fractional_receipts(horizon, a, b):
    result = simulate(records(units=1, inventory=0), inputs(baseline_reorder_quantity=1,
                      horizon_days=horizon, reorder_adjustment_percent=a, demand_change_percent=b))
    after = result["scenario"]
    receipt = Fraction(100+a, 100)
    demand = Fraction(100+b, 100) * horizon
    assert exact(after["assumed_receipt_quantity"]) == receipt
    assert exact(after["projected_demand"]) == demand
    assert exact(after["projected_ending_inventory"]) == max(receipt-demand, 0)
    assert exact(after["unmet_demand"]) == max(demand-receipt, 0)


@pytest.mark.parametrize("inventory,stockout,unmet", [(0, True, 70), (69, True, 1), (70, False, 0), (71, False, 0)])
def test_stockout_exact_boundary_not_negative_inventory(inventory, stockout, unmet):
    result = simulate(records(inventory=inventory), inputs(baseline_reorder_quantity=0, horizon_days=7))
    after = result["scenario"]
    assert after["potential_stockout"]["value"] is stockout
    assert exact(after["unmet_demand"]) == unmet
    assert exact(after["projected_ending_inventory"]) == max(inventory-70, 0)


@pytest.mark.parametrize("inventory,excess", [(369, False), (370, False), (371, True)])
def test_excess_ending_stock_exact_30_day_boundary(inventory, excess):
    after = simulate(records(inventory=inventory), inputs(baseline_reorder_quantity=0, horizon_days=7))["scenario"]
    assert after["potential_excess_stock"]["value"] is excess
    assert exact(after["days_inventory_remaining"]) == Fraction(inventory-70, 10)


def test_zero_demand_no_infinity_or_false_health():
    result = simulate(records(units=0), inputs(reorder_adjustment_percent=-50))
    for branch in [result["baseline"], result["scenario"]]:
        assert exact(branch["projected_demand"]) == 0
        assert branch["potential_stockout"]["value"] is False
        for key in ["days_inventory_remaining", "potential_excess_stock"]:
            assert branch[key]["status"] == "unsupported"
            assert branch[key]["value"] is None
            assert branch[key]["reason"] == "zero_scenario_demand"
    assert exact(result["scenario"]["projected_ending_inventory"]) == 150
    assert result["comparison"]["days_inventory_remaining"]["value"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value,expected", [(Fraction(1, 8), "0.13"), (Fraction(-1, 8), "-0.13"),
                                         (Fraction(1, 200), "0.01"), (Fraction(-1, 1000), "0.00")])
def test_actual_half_up_ties(value, expected):
    assert display(value) == expected


def test_unrounded_deltas_context_invariance_and_no_mutation():
    rows = records(units=1, inventory=10)
    before = copy.deepcopy(rows)
    args = inputs(baseline_reorder_quantity=1, reorder_adjustment_percent=1, demand_change_percent=1, horizon_days=7)
    expected = simulate(rows, args)
    assert exact(expected["scenario"]["days_inventory_remaining"]) == Fraction(394, 101)
    with localcontext() as context:
        context.prec = 2
        assert simulate(rows, args) == expected
    assert simulate(tuple(reversed(rows)), args) == expected
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(item == expected for item in pool.map(lambda _: simulate(rows, args), range(32)))
    assert rows == before
    # Neither revenue nor selling price nor lead time affects unit-based scenarios.
    changed = tuple(replace(r, revenue=Decimal("999999.99"), unit_price=Decimal("0"), lead_time_days=999) for r in rows)
    assert simulate(changed, args) == expected


@pytest.mark.parametrize("kind,reason", [("tiny", "incomplete_daily_coverage"), ("missing", "incomplete_daily_coverage"),
                                       ("stale", "stale_inventory_snapshot"), ("early", "date_boundary")])
def test_unsupported_never_repairs_missing_inputs(kind, reason):
    rows = records()
    if kind == "tiny": rows = rows[-1:]
    if kind == "missing": rows = rows[:3]+rows[4:]
    if kind == "stale": rows = rows[:-1]+records(product="B")
    if kind == "early": rows = (replace(rows[-1], date=date.min),)
    options = simulation_options(rows)
    assert options["products"][0]["reason"] == reason
    with pytest.raises(AnalysisError) as error:
        simulate(rows, inputs())
    assert error.value.detail["code"] == "simulation_unsupported"
    assert error.value.detail["reason"] == reason


def test_latest_snapshot_once_and_dataset_clock_only():
    rows = records(inventory=100, end=date.max)
    rows = tuple(replace(r, inventory=99999) for r in rows[:-1]) + rows[-1:]
    result = simulate(rows, inputs())
    assert result["dataset_as_of"] == "9999-12-31"
    assert result["source"]["inventory_units"] == 100
    assert exact(result["baseline"]["available_inventory"]) == 200
    assert result["source"]["demand_period"]["start"] == "9999-12-25"


def test_maximum_counts_json_safe_and_zero_receipt_cannot_invent_order():
    result = simulate(records(units=10**12, inventory=10**12), inputs(baseline_reorder_quantity=10**12,
                      horizon_days=30, demand_change_percent=30, reorder_adjustment_percent=50))
    assert exact(result["scenario"]["projected_demand"]) == 39*10**12
    assert exact(result["scenario"]["assumed_receipt_quantity"]) == 15*10**11
    json.dumps(result, allow_nan=False)
    result = simulate(records(), inputs(baseline_reorder_quantity=0, reorder_adjustment_percent=50))
    assert exact(result["scenario"]["assumed_receipt_quantity"]) == 0


def test_independent_demo_hand_calculations():
    rows = ingest_csv((Path(__file__).resolve().parents[2]/"data"/"demo_business.csv").read_bytes()).records
    # Raw fixture's Mar25–31 Harbor73, Summit101, Orbit185; stock0,828,90.
    harbor = simulate(rows, inputs(product_id="P-002", baseline_reorder_quantity=100, horizon_days=7))
    assert exact(harbor["baseline"]["projected_demand"]) == 73
    assert exact(harbor["baseline"]["projected_ending_inventory"]) == 27
    assert exact(harbor["baseline"]["days_inventory_remaining"]) == Fraction(189, 73)
    summit = simulate(rows, inputs(product_id="P-003", baseline_reorder_quantity=0, horizon_days=14))
    assert exact(summit["baseline"]["projected_demand"]) == 202
    assert exact(summit["baseline"]["projected_ending_inventory"]) == 626
    assert exact(summit["baseline"]["days_inventory_remaining"]) == Fraction(4382, 101)
    assert summit["baseline"]["potential_excess_stock"]["value"] is True
    orbit = simulate(rows, inputs(product_id="P-005", baseline_reorder_quantity=0, horizon_days=7))
    assert exact(orbit["baseline"]["unmet_demand"]) == 95
    assert orbit["baseline"]["potential_stockout"]["value"] is True


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def url(client):
    session = client.post('/api/v1/analysis/demo').json()
    return f"/api/v1/analysis/{session['analysis_id']}", session


def body(**overrides):
    return inputs(product_id="P-002").model_dump() | overrides


@pytest.mark.parametrize("overrides", [
    {"baseline_reorder_quantity": -1}, {"baseline_reorder_quantity": 10**12+1},
    {"baseline_reorder_quantity": "1"}, {"baseline_reorder_quantity": 1.5}, {"baseline_reorder_quantity": True},
    {"reorder_adjustment_percent": -51}, {"reorder_adjustment_percent": 51}, {"reorder_adjustment_percent": 0.0},
    {"demand_change_percent": -31}, {"demand_change_percent": 31}, {"demand_change_percent": "0"},
    {"horizon_days": 8}, {"horizon_days": True}, {"horizon_days": 7.0}, {"horizon_days": "7"},
    {"product_id": ""}, {"product_id": 1}, {"product_id": "a"*201}, {"price_adjustment": 1},
])
def test_api_rejects_unsupported_types_ranges_and_extra_fields(client, overrides):
    base, _ = url(client)
    assert client.post(base+'/simulate', json=body(**overrides)).status_code == 422


def test_api_contract_repeat_expiry_isolation_release_cors(client):
    base, session = url(client)
    other, _ = url(client)
    response = client.get(base+'/simulation')
    assert response.status_code == 200
    assert len(response.json()["products"]) == 6
    assert response.json()["expires_at"] == session["expires_at"]
    result = client.post(base+'/simulate', json=body(), headers={"Origin": "http://localhost:5173"})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert result.json() == client.post(base+'/simulate', json=body()).json()
    assert result.json()["expires_at"] == session["expires_at"]
    assert "records" not in result.json()
    assert client.post(base+'/simulate', json=body(product_id="foreign")).status_code == 404
    assert client.post(base+'/simulate', json={}).status_code == 422
    assert client.post(base+'/simulate', content='{', headers={"Content-Type": "application/json"}).status_code == 422
    preflight = client.options(base+'/simulate', headers={"Origin": "http://localhost:5173",
                               "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert preflight.status_code == 200
    assert client.options(base+'/simulate', headers={"Origin": "https://unconfigured.invalid",
                          "Access-Control-Request-Method": "POST"}).status_code == 400
    client.delete(base)
    for suffix in ['/simulation', '/simulate']:
        response = client.get(base+suffix) if suffix == '/simulation' else client.post(base+suffix, json=body())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_unavailable"
    assert client.post(other+'/simulate', json=body()).status_code == 200


@pytest.mark.parametrize("endpoint", ['simulation', 'simulate'])
@pytest.mark.parametrize("action", ['expire', 'release'])
def test_session_unavailable_during_computation(monkeypatch, endpoint, action):
    clock = [0]
    store = SessionStore(clock=lambda: clock[0])
    with TestClient(create_app(session_store=store)) as client:
        base, session = url(client)
        from app import analysis
        name = 'simulation_options' if endpoint == 'simulation' else 'simulate'
        original = getattr(analysis, name)
        def compute(*args):
            result = original(*args)
            if action == 'expire': clock[0] = 1800
            else: store.delete(session["analysis_id"])
            return result
        monkeypatch.setattr(analysis, name, compute)
        response = client.get(base+'/'+endpoint) if endpoint == 'simulation' else client.post(base+'/'+endpoint, json=body())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_unavailable"


def test_api_ineligible_product_structured_error(client):
    content = (Path(__file__).parent/'fixtures'/'analytics_tiny.csv').read_bytes()
    session = client.post('/api/v1/analysis/upload', content=content, headers={"Content-Type": "text/csv"}).json()
    base = f"/api/v1/analysis/{session['analysis_id']}"
    product = client.get(base+'/simulation').json()['products'][0]
    response = client.post(base+'/simulate', json=body(product_id=product['product_id']))
    assert response.status_code == 422
    assert response.json()['error']['reason'] == 'incomplete_daily_coverage'


def test_actual_simulation_rounding_tie_and_unrounded_excess_flag():
    result = simulate(records(units=8, inventory=57), inputs(baseline_reorder_quantity=0, horizon_days=7))
    assert exact(result['scenario']['days_inventory_remaining']) == Fraction(1, 8)
    assert result['scenario']['days_inventory_remaining']['value'] == '0.13'
    result = simulate(records(units=10**9, inventory=37*10**9+1), inputs(baseline_reorder_quantity=0, horizon_days=7))
    assert result['scenario']['days_inventory_remaining']['value'] == '30.00'
    assert result['scenario']['potential_excess_stock']['value'] is True


def test_ten_thousand_rows_remain_bounded_without_calendar_expansion():
    rows = tuple(replace(records()[0], date=date(2000, 1, 1)+timedelta(days=i)) for i in range(10_000))
    options = simulation_options(rows)
    assert len(options['products']) == 1
    assert options['products'][0]['source']['observed_days'] == 7
    assert exact(simulate(rows, inputs())['baseline']['projected_demand']) == 140


def test_zero_fixture_through_real_ingestion_and_api(client):
    content = (Path(__file__).parent/'fixtures'/'simulation_zero.csv').read_bytes()
    session = client.post('/api/v1/analysis/upload', content=content, headers={'Content-Type': 'text/csv'}).json()
    response = client.post(f"/api/v1/analysis/{session['analysis_id']}/simulate", json=body(product_id='ZERO', baseline_reorder_quantity=0))
    assert response.status_code == 200
    assert response.json()['scenario']['projected_ending_inventory']['value'] == '10.00'
    assert response.json()['scenario']['potential_excess_stock']['status'] == 'unsupported'


def test_unknown_and_expired_on_entry():
    clock = [0]
    with TestClient(create_app(session_store=SessionStore(clock=lambda: clock[0]))) as client:
        base, _ = url(client)
        clock[0] = 1800
        for path in [base, '/api/v1/analysis/unknown']:
            assert client.get(path+'/simulation').status_code == 404
            assert client.post(path+'/simulate', json=body()).json()['error']['code'] == 'analysis_unavailable'
