"""V1 metrics from normalized immutable records. See docs/METRICS.md."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from app.ingestion.validation import AnalysisError, Record

WINDOW_DAYS = 7
ZERO = Decimal("0")


def json_integer(value: int) -> int | str:
    return str(value) if abs(value) > 2**53 - 1 else value


def decimal_string(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(rounded if rounded else ZERO.quantize(Decimal("0.01")), "f")


def metric(name: str, value, unit: str, period: dict | None, reason: str | None = None) -> dict:
    if isinstance(value, Decimal):
        value = decimal_string(value)
    elif isinstance(value, int):
        value = json_integer(value)
    return {"name": name, "value": value, "unit": unit, "period": period,
            "status": "unsupported" if reason else "supported", "reason": reason}


def period(start: date, end: date) -> dict:
    return {"start": start.isoformat(), "end": end.isoformat(), "calendar_days": (end - start).days + 1}


def flows(records: list[Record] | tuple[Record, ...]) -> tuple[Decimal, int]:
    return sum((r.revenue for r in records), ZERO), sum(r.units_sold for r in records)


def latest_snapshots(records) -> list[Record]:
    latest = {}
    for record in records:
        if record.product_id not in latest or latest[record.product_id].date < record.date:
            latest[record.product_id] = record
    return list(latest.values())


def performance(records, reporting_period: dict) -> dict:
    revenue, units = flows(records)
    snapshots = latest_snapshots(records)
    dates = [r.date for r in snapshots]
    return {
        "total_revenue": metric("total_revenue", revenue, "currency", reporting_period),
        "total_units_sold": metric("total_units_sold", units, "units", reporting_period),
        "product_count": metric("product_count", len(snapshots), "products", reporting_period),
        "current_inventory_units": metric("current_inventory_units", sum(r.inventory for r in snapshots), "units", reporting_period),
        "inventory_snapshot_metadata": {
            "policy": "latest_observation_per_product_in_period", "snapshot_product_count": len(snapshots),
            "snapshot_date_range": {"start": min(dates).isoformat(), "end": max(dates).isoformat()},
            "mixed_snapshot_dates": len(set(dates)) > 1,
        },
    }


def comparison(records, cohort: set[str], dataset_start: date, dataset_end: date) -> dict:
    current_period = previous_period = None
    current = previous = []
    incomplete = len(cohort)
    reason = "date_boundary"
    if dataset_end.toordinal() >= WINDOW_DAYS * 2:
        current_start = dataset_end - timedelta(days=WINDOW_DAYS - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = current_start - timedelta(days=WINDOW_DAYS)
        current_period = period(current_start, dataset_end)
        previous_period = period(previous_start, previous_end)
        current = [r for r in records if current_start <= r.date <= dataset_end]
        previous = [r for r in records if previous_start <= r.date <= previous_end]
        current_counts = Counter(r.product_id for r in current)
        previous_counts = Counter(r.product_id for r in previous)
        incomplete = sum(current_counts[key] != WINDOW_DAYS or previous_counts[key] != WINDOW_DAYS for key in cohort)
        if dataset_start > previous_start:
            reason = "insufficient_history"
        elif any(current_counts[key] == 0 or previous_counts[key] == 0 for key in cohort):
            reason = "product_missing_in_period"
        elif incomplete:
            reason = "incomplete_daily_coverage"
        else:
            reason = None
    current_revenue, current_units = flows(current)
    previous_revenue, previous_units = flows(previous)
    changes = {}
    for name, unit, curr, prev in (
        ("total_revenue", "currency", current_revenue, previous_revenue),
        ("total_units_sold", "units", current_units, previous_units),
    ):
        delta = curr - prev
        pct_reason = reason or ("zero_previous_value" if prev == 0 else None)
        pct = None if pct_reason else Decimal(delta) / Decimal(prev) * Decimal(100)
        changes[name] = {
            "name": name, "unit": unit, "basis": "observed_records",
            "current": metric(name, curr if current else None, unit, current_period, None if current else "no_observations"),
            "previous": metric(name, prev if previous else None, unit, previous_period, None if previous else "no_observations"),
            "absolute_change": metric("absolute_change", None if reason else delta, unit, current_period, reason),
            "percentage_change": metric("percentage_change", pct, "percent", current_period, pct_reason),
        }
    return {
        "policy": "latest_7_calendar_days_vs_preceding_7_complete_fixed_cohort",
        "window_days": WINDOW_DAYS, "current_period": current_period, "previous_period": previous_period,
        "status": "unsupported" if reason else "supported", "reason": reason,
        "coverage": {"cohort_product_count": len(cohort), "incomplete_product_count": incomplete,
                     "current_rows": len(current), "previous_rows": len(previous),
                     "current_observed_days": len({r.date for r in current}),
                     "previous_observed_days": len({r.date for r in previous})},
        "metrics": changes,
    }


def calculate_analytics(records: tuple[Record, ...]) -> dict:
    if not records:
        raise AnalysisError("no_observations", "Analytics require a validated, nonempty dataset.")
    # All exact input totals fit within this context; never use binary floats.
    with localcontext() as context:
        context.prec = 50
        by_product = defaultdict(list)
        by_category = defaultdict(list)
        by_day = defaultdict(list)
        for record in records:
            by_product[record.product_id].append(record)
            by_category[record.category].append(record)
            by_day[record.date].append(record)
        start, end = min(by_day), max(by_day)
        reporting_period = period(start, end)
        overview = performance(records, reporting_period)
        overview["category_count"] = metric("category_count", len(by_category), "categories", reporting_period)
        products = []
        for key in sorted(by_product):
            product_records = by_product[key]
            entry = {"product_id": key, "product_name": product_records[0].product_name,
                     "category": product_records[0].category, **performance(product_records, reporting_period)}
            days = len({r.date for r in product_records})
            revenue, units = flows(product_records)
            entry["observed_days"] = days
            entry["inventory_observation_date"] = max(r.date for r in product_records).isoformat()
            entry["average_units_per_active_day"] = {
                **metric("average_units_per_active_day", Decimal(units) / Decimal(days), "units/observed_day", reporting_period),
                "basis": {"numerator": json_integer(units), "denominator": days},
            }
            entry["average_revenue_per_active_day"] = {
                **metric("average_revenue_per_active_day", revenue / Decimal(days), "currency/observed_day", reporting_period),
                "basis": {"numerator": decimal_string(revenue), "denominator": days},
            }
            entry["period_comparison"] = comparison(product_records, {key}, start, end)
            products.append(entry)
        categories = [{"category": key, **performance(by_category[key], reporting_period)} for key in sorted(by_category)]
        series = []
        for day in sorted(by_day):
            revenue, units = flows(by_day[day])
            day_period = period(day, day)
            series.append({"date": day.isoformat(), "observed_product_count": len(by_day[day]),
                           "total_revenue": metric("total_revenue", revenue, "currency", day_period),
                           "total_units_sold": metric("total_units_sold", units, "units", day_period)})
        return {
            "schema_version": "analytics-v1", "period": reporting_period,
            "coverage": {"observed_days": len(by_day), "calendar_days": reporting_period["calendar_days"],
                         "row_count": len(records), "missing_days_imputed": False},
            "overview": overview, "products": products, "categories": categories,
            "daily_time_series": series, "period_comparison": comparison(records, set(by_product), start, end),
        }
