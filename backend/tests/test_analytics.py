import copy
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analytics.metrics import calculate_analytics
from app.ingestion.validation import Record, ingest_csv
from app.main import create_app
from app.sessions.store import SessionStore

FIXTURE = Path(__file__).parent / "fixtures" / "analytics_known.csv"


def record(day, product="A", *, units=1, revenue="0.10", inventory=10, category="Stationery"):
    return Record(date.fromisoformat(day), product, product, category, units, Decimal(revenue), inventory, Decimal("99.00"), None, None)


def test_hand_calculated_totals_products_categories_and_days():
    result = calculate_analytics(ingest_csv(FIXTURE.read_bytes()).records)
    overview = result["overview"]
    assert overview["total_revenue"]["value"] == "23.45"  # 7×.10 + 7×.25 + 7×1 + 7×2
    assert overview["total_units_sold"]["value"] == 70  # 7×2 + 7×4 + 7×1 + 7×3
    assert overview["current_inventory_units"]["value"] == 124  # Latest A=87, B=37 only
    assert overview["product_count"]["value"] == overview["category_count"]["value"] == 2
    assert result["period"] == {"start": "2026-01-01", "end": "2026-01-14", "calendar_days": 14}
    a, b = result["products"]
    assert a["product_id"] == "A"
    assert a["total_revenue"]["value"] == "2.45"
    assert a["total_units_sold"]["value"] == 42
    assert a["current_inventory_units"]["value"] == 87
    assert a["average_units_per_active_day"]["value"] == "3.00"
    assert a["average_revenue_per_active_day"]["value"] == "0.18"  # .175 -> half up
    assert a["average_revenue_per_active_day"]["basis"] == {"numerator": "2.45", "denominator": 14}
    assert b["total_revenue"]["value"] == "21.00"
    assert b["total_units_sold"]["value"] == 28
    assert b["average_revenue_per_active_day"]["value"] == "1.50"
    categories = {row["category"]: row for row in result["categories"]}
    assert categories["Stationery"]["total_revenue"]["value"] == "2.45"
    assert categories["Home"]["current_inventory_units"]["value"] == 37
    assert sum(Decimal(row["total_revenue"]["value"]) for row in result["categories"]) == Decimal("23.45")
    assert sum(row["total_units_sold"]["value"] for row in result["categories"]) == 70
    assert sum(row["current_inventory_units"]["value"] for row in result["categories"]) == 124
    series = result["daily_time_series"]
    assert len(series) == 14
    assert series[0]["date"] == "2026-01-01"
    assert series[0]["total_revenue"]["value"] == "1.10"
    assert series[0]["total_units_sold"]["value"] == 3
    assert series[7]["total_revenue"]["value"] == "2.25"
    assert series[7]["total_units_sold"]["value"] == 7
    assert all("current_inventory_units" not in point for point in series)
    assert sum(Decimal(point["total_revenue"]["value"]) for point in series) == Decimal("23.45")


def test_period_boundaries_and_hand_calculated_changes():
    result = calculate_analytics(ingest_csv(FIXTURE.read_bytes()).records)
    comparison = result["period_comparison"]
    assert comparison["status"] == "supported"
    assert comparison["previous_period"] == {"start": "2026-01-01", "end": "2026-01-07", "calendar_days": 7}
    assert comparison["current_period"] == {"start": "2026-01-08", "end": "2026-01-14", "calendar_days": 7}
    revenue = comparison["metrics"]["total_revenue"]
    assert revenue["previous"]["value"] == "7.70"
    assert revenue["current"]["value"] == "15.75"
    assert revenue["absolute_change"]["value"] == "8.05"
    assert revenue["percentage_change"]["value"] == "104.55"
    units = comparison["metrics"]["total_units_sold"]
    assert units["previous"]["value"] == 21
    assert units["current"]["value"] == 49
    assert units["absolute_change"]["value"] == 28
    assert units["percentage_change"]["value"] == "133.33"
    a = result["products"][0]["period_comparison"]["metrics"]
    assert a["total_revenue"]["percentage_change"]["value"] == "150.00"
    assert a["total_units_sold"]["percentage_change"]["value"] == "100.00"


def test_inventory_latest_dates_and_observed_day_averages_no_imputation():
    records = (
        record("2026-01-01", inventory=100, units=2, revenue="1.01"),
        record("2026-01-03", inventory=7, units=0, revenue="0.10"),
        record("2026-01-02", "B", inventory=30, revenue="0.20"),
        record("2026-01-04", "B", inventory=4, units=3, revenue="0.30"),
        record("2026-01-03", "C", inventory=8, revenue="0.05"),
    )
    result = calculate_analytics(records)
    assert result["overview"]["total_revenue"]["value"] == "1.66"
    assert result["overview"]["current_inventory_units"]["value"] == 19  # 7+4+8, never 149
    assert result["categories"][0]["current_inventory_units"]["value"] == 19
    snapshots = result["overview"]["inventory_snapshot_metadata"]
    assert snapshots["mixed_snapshot_dates"] is True
    assert snapshots["snapshot_date_range"] == {"start": "2026-01-03", "end": "2026-01-04"}
    a = result["products"][0]
    assert a["inventory_observation_date"] == "2026-01-03"
    assert a["observed_days"] == 2
    assert a["average_units_per_active_day"]["value"] == "1.00"  # Includes observed zero-sales day
    assert a["average_revenue_per_active_day"]["value"] == "0.56"  # 1.11/2 half up


@pytest.mark.parametrize("current_units,current_revenue", [(0, "0.00"), (3, "0.30")])
def test_zero_previous_preserves_absolute_change_and_abstains_percentage(current_units, current_revenue):
    records = tuple(record(f"2026-01-{day:02}", units=0 if day <= 7 else current_units,
                           revenue="0.00" if day <= 7 else current_revenue) for day in range(1, 15))
    changes = calculate_analytics(records)["period_comparison"]
    assert changes["status"] == "supported"
    for key in ("total_revenue", "total_units_sold"):
        assert changes["metrics"][key]["absolute_change"]["status"] == "supported"
        percent = changes["metrics"][key]["percentage_change"]
        assert percent["value"] is None
        assert percent["reason"] == "zero_previous_value"
    assert changes["metrics"]["total_units_sold"]["absolute_change"]["value"] == 7 * current_units
    assert changes["metrics"]["total_revenue"]["absolute_change"]["value"] == ("0.00" if current_units == 0 else "2.10")


def test_negative_changes_and_half_up_percent():
    records = tuple(record(f"2026-01-{day:02}", units=3 if day <= 7 else 1,
                           revenue="0.03" if day <= 7 else "0.01") for day in range(1, 15))
    changes = calculate_analytics(records)["period_comparison"]["metrics"]
    assert changes["total_revenue"]["absolute_change"]["value"] == "-0.14"
    assert changes["total_revenue"]["percentage_change"]["value"] == "-66.67"
    assert changes["total_units_sold"]["absolute_change"]["value"] == -14


@pytest.mark.parametrize("current,expected", [("8.01", "0.13"), ("7.99", "-0.13")])
def test_percentage_half_up_at_exact_positive_and_negative_ties(current, expected):
    # Each seven-day window totals 8.00 vs 8.01/7.99: ±.01/8×100 = ±.125%.
    records = tuple(record(f"2026-01-{day:02}", revenue="8.00" if day == 1 else
                           current if day == 8 else "0.00") for day in range(1, 15))
    change = calculate_analytics(records)["period_comparison"]["metrics"]["total_revenue"]
    assert change["previous"]["value"] == "8.00"
    assert change["current"]["value"] == current
    assert change["percentage_change"]["value"] == expected


@pytest.mark.parametrize("days", [1, 2, 7, 13])
def test_tiny_and_insufficient_history(days):
    records = tuple(record(f"2026-01-{day:02}") for day in range(1, days + 1))
    result = calculate_analytics(records)
    assert result["overview"]["total_units_sold"]["value"] == days
    assert result["period_comparison"]["reason"] == "insufficient_history"
    assert result["period_comparison"]["metrics"]["total_revenue"]["absolute_change"]["value"] is None


def test_calendar_lower_boundary_and_wide_sparse_date_span():
    result = calculate_analytics((record("0001-01-01"),))
    assert result["period_comparison"]["reason"] == "date_boundary"
    assert result["period_comparison"]["previous_period"] is None
    result = calculate_analytics((record("0001-01-01"), record("9999-12-31")))
    assert len(result["daily_time_series"]) == 2  # No multi-million-day expansion.
    assert result["coverage"]["observed_days"] == 2
    assert result["period_comparison"]["reason"] == "product_missing_in_period"


def test_incomplete_product_daily_coverage_abstains_not_zero_filled():
    records = ingest_csv(FIXTURE.read_bytes()).records
    filtered = tuple(r for r in records if not (r.product_id == "A" and r.date == date(2026, 1, 9)))
    result = calculate_analytics(filtered)
    assert result["period_comparison"]["reason"] == "incomplete_daily_coverage"
    assert result["products"][0]["period_comparison"]["status"] == "unsupported"
    assert result["products"][1]["period_comparison"]["status"] == "supported"
    assert result["period_comparison"]["coverage"]["incomplete_product_count"] == 1
    assert result["daily_time_series"][8]["observed_product_count"] == 1


@pytest.mark.parametrize("missing_window", ["previous", "current"])
def test_product_absent_from_one_window_is_not_assumed_zero(missing_window):
    records = ingest_csv(FIXTURE.read_bytes()).records
    filtered = tuple(r for r in records if r.product_id == "B" or
                     (r.date.day >= 8 if missing_window == "previous" else r.date.day <= 7))
    result = calculate_analytics(filtered)
    assert result["period_comparison"]["reason"] == "product_missing_in_period"
    a = result["products"][0]["period_comparison"]
    assert a["reason"] == "product_missing_in_period"
    assert a["metrics"]["total_revenue"][missing_window]["value"] is None
    assert a["metrics"]["total_revenue"]["percentage_change"]["value"] is None


def test_old_product_in_fixed_cohort_causes_explicit_abstention():
    records = (*ingest_csv(FIXTURE.read_bytes()).records, record("2025-12-01", "Retired"))
    result = calculate_analytics(records)
    assert result["period_comparison"]["reason"] == "product_missing_in_period"
    assert result["period_comparison"]["coverage"]["cohort_product_count"] == 3


def test_order_independence_no_mutation_and_context_isolation():
    dataset = ingest_csv(FIXTURE.read_bytes())
    original = copy.deepcopy(dataset)
    expected = calculate_analytics(dataset.records)
    with localcontext() as context:
        context.prec = 3
        result = calculate_analytics(tuple(reversed(dataset.records)))
    assert result == expected
    assert dataset == original
    assert result["overview"]["total_revenue"]["value"] == "23.45"
    assert dataset.records[0].unit_price == Decimal("99.00")  # Never used to replace revenue.


def test_maximum_v1_money_and_unit_totals_remain_exact():
    records = tuple(replace(record("2026-01-01", str(i)), revenue=Decimal("1000000000000.00"),
                            units_sold=1000000000000) for i in range(10000))
    result = calculate_analytics(records)
    assert result["overview"]["total_revenue"]["value"] == "10000000000000000.00"
    assert result["overview"]["total_units_sold"]["value"] == "10000000000000000"
    records = (*records[:-1], replace(records[-1], revenue=Decimal("999999999999.99"), units_sold=999999999999))
    result = calculate_analytics(records)
    assert result["overview"]["total_revenue"]["value"] == "9999999999999999.99"
    assert result["overview"]["total_units_sold"]["value"] == "9999999999999999"


def test_observed_zero_and_sparse_days_do_not_change_denominators():
    result = calculate_analytics((record("2026-01-01", units=0, revenue="0.00", inventory=0),
                                  record("2026-01-03", units=1, revenue="0.01", inventory=3)))
    assert result["products"][0]["average_revenue_per_active_day"]["value"] == "0.01"  # .005 half up
    assert result["products"][0]["average_units_per_active_day"]["value"] == "0.50"
    assert [p["date"] for p in result["daily_time_series"]] == ["2026-01-01", "2026-01-03"]
    assert result["overview"]["current_inventory_units"]["value"] == 3


def test_api_upload_analytics_json_cors_no_cache_and_session_unchanged():
    with TestClient(create_app()) as client:
        uploaded = client.post("/api/v1/analysis/upload", content=FIXTURE.read_bytes(), headers={"Content-Type": "text/csv"}).json()
        key = uploaded["analysis_id"]
        before = copy.deepcopy(client.app.state.sessions.get(key).dataset)
        response = client.get(f"/api/v1/analysis/{key}/analytics", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "analytics-v1"
        assert body["analysis_id"] == key
        assert body["expires_at"] == uploaded["expires_at"]
        assert body["overview"]["total_revenue"]["value"] == "23.45"
        assert isinstance(body["overview"]["total_revenue"]["value"], str)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "records" not in body
        assert client.app.state.sessions.get(key).dataset == before
        assert client.get(f"/api/v1/analysis/{key}/analytics").json() == body
        assert len(client.app.state.sessions._sessions) == 1
        assert client.get(f"/api/v1/analysis/{key}").json() == uploaded
        client.delete(f"/api/v1/analysis/{key}")
        assert client.get(f"/api/v1/analysis/{key}/analytics").status_code == 404


def test_api_unknown_expired_and_expiry_during_calculation(monkeypatch):
    now = [0.0]
    store = SessionStore(clock=lambda: now[0])
    with TestClient(create_app(session_store=store)) as client:
        assert client.get("/api/v1/analysis/unknown/analytics").json()["error"]["code"] == "analysis_unavailable"
        first = client.post("/api/v1/analysis/demo").json()["analysis_id"]
        now[0] = 1800
        assert client.get(f"/api/v1/analysis/{first}/analytics").status_code == 404
        second = client.post("/api/v1/analysis/demo").json()["analysis_id"]
        original = calculate_analytics

        def expire_during(records):
            now[0] += 1800
            return original(records)

        monkeypatch.setattr("app.analysis.calculate_analytics", expire_during)
        assert client.get(f"/api/v1/analysis/{second}/analytics").status_code == 404


def test_demo_analytics_reconciles_and_comparison_is_supported():
    with TestClient(create_app()) as client:
        key = client.post("/api/v1/analysis/demo").json()["analysis_id"]
        body = client.get(f"/api/v1/analysis/{key}/analytics").json()
        assert body["coverage"] == {"observed_days": 90, "calendar_days": 90, "row_count": 540, "missing_days_imputed": False}
        assert body["period_comparison"]["status"] == "supported"
        assert body["period_comparison"]["current_period"]["start"] == "2026-03-25"
        assert body["period_comparison"]["previous_period"]["end"] == "2026-03-24"
        # Independently audited from raw CSV with integer cents, without analytics helpers.
        assert body["overview"]["total_revenue"]["value"] == "157094.00"
        assert body["overview"]["total_units_sold"]["value"] == 6556
        assert body["overview"]["current_inventory_units"]["value"] == 1439
        revenue = body["period_comparison"]["metrics"]["total_revenue"]
        assert revenue["previous"]["value"] == "14607.00"
        assert revenue["current"]["value"] == "14813.00"
        assert revenue["absolute_change"]["value"] == "206.00"
        assert revenue["percentage_change"]["value"] == "1.41"
        assert sum(Decimal(p["total_revenue"]["value"]) for p in body["products"]) == Decimal(body["overview"]["total_revenue"]["value"])
        assert sum(p["current_inventory_units"]["value"] for p in body["products"]) == body["overview"]["current_inventory_units"]["value"]


def test_one_day_upload_keeps_observed_zeros_and_abstains_comparison():
    with TestClient(create_app()) as client:
        uploaded = client.post("/api/v1/analysis/upload", content=(FIXTURE.parent / "analytics_tiny.csv").read_bytes(),
                               headers={"Content-Type": "text/csv"}).json()
        body = client.get(f"/api/v1/analysis/{uploaded['analysis_id']}/analytics").json()
        assert body["overview"]["total_revenue"]["value"] == "0.00"
        assert body["overview"]["total_units_sold"]["value"] == 0
        assert body["overview"]["current_inventory_units"]["value"] == 5
        assert body["products"][0]["average_units_per_active_day"]["value"] == "0.00"
        comparison = body["period_comparison"]
        assert comparison["reason"] == "insufficient_history"
        assert comparison["metrics"]["total_revenue"]["previous"]["value"] is None
        assert comparison["metrics"]["total_revenue"]["absolute_change"]["value"] is None
