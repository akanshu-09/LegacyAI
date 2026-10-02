"""Exact unit-based scenarios. Contract: docs/SIMULATION.md."""

from collections import defaultdict
from datetime import timedelta
from fractions import Fraction

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from app.analytics.metrics import latest_snapshots, json_integer, period
from app.ingestion.validation import AnalysisError


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: StrictStr = Field(min_length=1, max_length=200)
    baseline_reorder_quantity: StrictInt = Field(ge=0, le=10**12)
    reorder_adjustment_percent: StrictInt = Field(ge=-50, le=50)
    demand_change_percent: StrictInt = Field(ge=-30, le=30)
    horizon_days: StrictInt

    @field_validator("horizon_days")
    @classmethod
    def supported_horizon(cls, value):
        if value not in (7, 14, 30):
            raise ValueError("Horizon must be 7, 14 or 30 days.")
        return value


ASSUMPTIONS = [
    "Hypothetical scenario, not a forecast, probability or purchasing instruction.",
    "Baseline reorder quantity is a user assumption; no planned orders exist in the dataset.",
    "All assumed receipts arrive immediately after the dataset end-of-day snapshot; lead time is not modeled.",
    "Demand is constant and uniform, based on the complete latest seven dataset calendar days.",
    "No other receipts, returns, spoilage or reservations; unmet demand is not served later.",
    "Fractional quantities are continuous scenario units, not whole-unit order recommendations.",
    "Potential excess means ending stock exceeds 30 days at the assumed demand rate.",
    "No revenue, profit, cost savings, seasonality or price elasticity is modeled.",
]


def display(value: Fraction) -> str:
    """Round only display, exactly HALF_UP, independent of Decimal context."""
    cents, remainder = divmod(abs(value.numerator) * 100, value.denominator)
    if remainder * 2 >= value.denominator:
        cents += 1
    sign = "-" if value < 0 and cents else ""
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def number(value: Fraction | None, unit: str, reason=None) -> dict:
    return {"value": None if value is None else display(value), "unit": unit,
            "exact": None if value is None else {"numerator": str(value.numerator), "denominator": str(value.denominator)},
            "status": "unsupported" if reason else "supported", "reason": reason}


def flag(value: bool | None, reason=None) -> dict:
    return {"value": value, "status": "unsupported" if reason else "supported", "reason": reason}


def simulation_options(records) -> dict:
    end = max(r.date for r in records)
    window = period(end - timedelta(days=6), end) if end.toordinal() >= 7 else None
    groups = defaultdict(list)
    for row in records:
        groups[row.product_id].append(row)
    products = []
    for key in sorted(groups):
        rows = groups[key]
        snapshot = latest_snapshots(rows)[0]
        recent = [r for r in rows if window and window["start"] <= r.date.isoformat() <= window["end"]]
        reason = ("date_boundary" if window is None else
                  "stale_inventory_snapshot" if snapshot.date != end else
                  "incomplete_daily_coverage" if len(recent) != 7 else None)
        # Unit-only simulation never needs a monetary aggregate.
        units = sum(r.units_sold for r in recent)
        products.append({"product_id": key, "product_name": snapshot.product_name,
                         "status": "unsupported" if reason else "supported", "reason": reason,
                         "source": {"inventory_units": json_integer(snapshot.inventory),
                                    "inventory_observation_date": snapshot.date.isoformat(),
                                    "inventory_method": "latest_observation_per_product",
                                    "recent_units": json_integer(units), "observed_days": len(recent),
                                    "demand_period": window,
                                    "demand_method": "sum_supplied_units_over_complete_7_calendar_days"}})
    return {"schema_version": "simulation-v1", "hypothetical": True,
            "dataset_as_of": end.isoformat(), "products": products, "assumptions": list(ASSUMPTIONS)}


def outcomes(inventory: int, receipt: Fraction, daily: Fraction, horizon: int) -> dict:
    projected = daily * horizon
    available = inventory + receipt
    ending = max(available - projected, Fraction(0))
    unmet = max(projected - available, Fraction(0))
    remaining = ending / daily if daily else None
    reason = None if daily else "zero_scenario_demand"
    return {"assumed_receipt_quantity": number(receipt, "units"),
            "daily_demand": number(daily, "units/day"),
            "projected_demand": number(projected, "units"),
            "available_inventory": number(available, "units"),
            "projected_ending_inventory": number(ending, "units"),
            "unmet_demand": number(unmet, "units"),
            "days_inventory_remaining": number(remaining, "days", reason),
            "potential_stockout": flag(projected > available),
            "potential_excess_stock": flag(remaining > 30 if remaining is not None else None, reason)}


def simulate(records, inputs: SimulationInput) -> dict:
    options = simulation_options(records)
    product = next((p for p in options["products"] if p["product_id"] == inputs.product_id), None)
    if product is None:
        raise AnalysisError("product_not_found", "Select a product belonging to this analysis session.", 404)
    if product["reason"]:
        raise AnalysisError("simulation_unsupported", "This product lacks complete recent demand or a fresh inventory snapshot.",
                            422, reason=product["reason"])
    source = product["source"]
    daily = Fraction(int(source["recent_units"]), 7)
    receipt = Fraction(inputs.baseline_reorder_quantity)
    baseline = outcomes(int(source["inventory_units"]), receipt, daily, inputs.horizon_days)
    scenario = outcomes(int(source["inventory_units"]), receipt * Fraction(100 + inputs.reorder_adjustment_percent, 100),
                        daily * Fraction(100 + inputs.demand_change_percent, 100), inputs.horizon_days)
    comparison = {}
    for key, before in baseline.items():
        if "exact" not in before:
            continue
        after = scenario[key]
        if before["exact"] is None or after["exact"] is None:
            comparison[key] = number(None, before["unit"], "zero_scenario_demand")
        else:
            exact_before = Fraction(int(before["exact"]["numerator"]), int(before["exact"]["denominator"]))
            exact_after = Fraction(int(after["exact"]["numerator"]), int(after["exact"]["denominator"]))
            comparison[key] = number(exact_after - exact_before, before["unit"])
    return {"schema_version": options["schema_version"], "hypothetical": True,
            "dataset_as_of": options["dataset_as_of"],
            "product": {"product_id": product["product_id"], "product_name": product["product_name"]},
            "source": source, "inputs": inputs.model_dump(), "baseline": baseline, "scenario": scenario,
            "comparison_method": "scenario_minus_baseline_exact_before_display_rounding",
            "comparison": comparison, "assumptions": list(ASSUMPTIONS)}
