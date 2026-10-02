"""Exact V1 rules. See docs/DETECTORS.md for thresholds, support and provenance."""
from collections import defaultdict
from datetime import timedelta
from decimal import localcontext
from fractions import Fraction

from app.analytics.metrics import WINDOW_DAYS, comparison, flows, latest_snapshots, period
from app.ingestion.validation import AnalysisError
from app.evidence.contract import EvidenceBuilder, EVIDENCE_SCHEMA, ISSUE_SCHEMA, dataset_identity, exact
from app.detectors import config as rules

TITLES = {"demand_decline": "Demand decline", "demand_spike": "Demand spike",
          "stockout_risk": "Stockout risk", "excess_inventory": "Excess inventory", "sales_anomaly": "Daily sales anomaly"}


def quartiles(values):
    """Median of halves, excluding the middle observation for odd samples."""
    ordered = sorted(values)

    def median(items):
        middle = len(items) // 2
        return Fraction(items[middle]) if len(items) % 2 else Fraction(items[middle - 1] + items[middle], 2)

    middle = len(ordered) // 2
    return median(ordered[:middle]), median(ordered[middle + len(ordered) % 2:])


def detect_issues(records):
    if not records:
        raise AnalysisError("no_observations", "Detection requires a validated, nonempty dataset.")
    with localcontext() as context:
        context.prec = 50
        return _detect(records)


def _detect(records):
    by_product = defaultdict(list)
    for record in records:
        by_product[record.product_id].append(record)
    start, end = min(r.date for r in records), max(r.date for r in records)
    current_start = end - timedelta(days=WINDOW_DAYS - 1) if end.toordinal() >= WINDOW_DAYS else None
    current_period = period(current_start, end) if current_start else None
    builder = EvidenceBuilder(dataset_identity(records))
    issues, evaluations = [], []

    for product_id in sorted(by_product):
        rows = sorted(by_product[product_id], key=lambda r: r.date)
        latest = latest_snapshots(rows)[0]
        comp = comparison(rows, {product_id}, start, end)
        recent = [r for r in rows if current_start and r.date >= current_start]
        recent_units = flows(recent)[1]

        for family in rules.FAMILIES:
            version = rules.VERSIONS[family]
            evaluation = {"entity_type": "product", "entity_id": product_id, "entity_name": latest.product_name,
                          "detector_version": version, "issue_type": family, "status": "evaluated_no_issue",
                          "reason": None, "period": current_period, "comparison_period": None, "issue_ids": []}
            evaluations.append(evaluation)

            def unsupported(reason):
                evaluation.update(status="unsupported", reason=reason)

            def evidence(metric, value, unit, window, source_name, kind, method, *, inputs=None,
                         previous=None, observed=None):
                return builder.add(entity_id=product_id, detector_version=version, metric=metric, value=value,
                                   unit=unit, period=window, comparison_period=previous, method=method,
                                   source={"name": source_name, "kind": kind}, inputs=inputs, observation_date=observed)

            def emit(severity, ids, summary, observed=None):
                # Summaries are rendered exclusively from the attached serialized evidence values.
                values = {builder.items[key]["metric"]: builder.items[key]["value"] for key in ids}
                issue = builder.issue({"issue_type": family, "entity_type": "product", "entity_id": product_id,
                                       "entity_name": latest.product_name, "severity": severity,
                                       "detected_at": end.isoformat(), "observation_date": observed,
                                       "title": TITLES[family], "summary": summary.format(**values),
                                       "evidence_ids": ids, "detector_version": version})
                issues.append(issue)
                evaluation["status"] = "issue_detected"
                evaluation["issue_ids"].append(issue["issue_id"])

            if family in ("demand_decline", "demand_spike"):
                evaluation["comparison_period"] = comp["previous_period"]
                evaluation["coverage"] = comp["coverage"]
                if comp["status"] != "supported":
                    unsupported(comp["reason"])
                    continue
                units = comp["metrics"]["total_units_sold"]
                previous, current = int(units["previous"]["value"]), int(units["current"]["value"])
                if previous == 0:
                    unsupported("zero_previous_demand")
                    continue
                delta = current - previous
                change = Fraction(delta * 100, previous)
                bands = rules.DECLINE_BANDS if family == "demand_decline" else rules.SPIKE_BANDS
                severity = next((label for threshold, label in bands if
                                 (change <= threshold if family == "demand_decline" else change >= threshold)), None)
                if severity:
                    inputs = {"previous_units": str(previous), "current_units": str(current)}
                    ids = [evidence("previous_units", previous, "units", comp["previous_period"],
                                    "phase2_period_comparison", "aggregated", "sum observed units in previous supported window"),
                           evidence("current_units", current, "units", comp["current_period"],
                                    "phase2_period_comparison", "aggregated", "sum observed units in current supported window"),
                           evidence("absolute_change", delta, "units", comp["current_period"], "detector_calculation", "derived",
                                    "current_units - previous_units", inputs=inputs, previous=comp["previous_period"]),
                           evidence("percentage_change", change, "percent", comp["current_period"], "detector_calculation", "derived",
                                    "100 * (current_units - previous_units) / previous_units", inputs=inputs, previous=comp["previous_period"])]
                    emit(severity, ids, "Observed units changed from {previous_units} to {current_units}: {absolute_change} units; {percentage_change}% (rounded).")

            elif family in ("stockout_risk", "excess_inventory"):
                evaluation["inventory_observation_date"] = latest.date.isoformat()
                evaluation["current_observed_days"] = len(recent)
                if not current_period:
                    unsupported("date_boundary")
                elif latest.date != end:
                    unsupported("stale_inventory_snapshot")
                elif len(recent) != WINDOW_DAYS:
                    unsupported("incomplete_daily_coverage")
                elif recent_units == 0:
                    unsupported("zero_recent_demand")
                else:
                    coverage = Fraction(latest.inventory * WINDOW_DAYS, recent_units)
                    if family == "stockout_risk":
                        severity = ("HIGH" if coverage <= rules.STOCKOUT_HIGH_DAYS else
                                    "MEDIUM" if coverage < rules.STOCKOUT_MEDIUM_DAYS else
                                    "LOW" if coverage < rules.STOCKOUT_LOW_DAYS else None)
                    else:
                        severity = next((label for threshold, label in rules.EXCESS_BANDS if coverage > threshold), None)
                    if severity:
                        inputs = {"inventory": str(latest.inventory), "current_units": str(recent_units),
                                  "window_days": str(WINDOW_DAYS), "inventory_observation_date": latest.date.isoformat()}
                        ids = [evidence("latest_inventory", latest.inventory, "units", period(latest.date, latest.date),
                                        "latest_inventory_snapshot", "observed", "latest product snapshot, required on dataset end date", observed=latest.date.isoformat()),
                               evidence("current_units", recent_units, "units", current_period, "phase2_current_period_units", "aggregated",
                                        "sum observed units in complete current window"),
                               evidence("recent_daily_demand", Fraction(recent_units, WINDOW_DAYS), "units/day", current_period,
                                        "detector_calculation", "derived", "current_units / window_days", inputs=inputs),
                               evidence("days_of_inventory", coverage, "days", current_period, "detector_calculation", "derived",
                                        "inventory * window_days / current_units", inputs=inputs, observed=latest.date.isoformat())]
                        emit(severity, ids, "Latest inventory is {latest_inventory} units; recent daily demand is {recent_daily_demand} units/day and stock coverage is {days_of_inventory} days (ratios rounded).")

            else:
                baseline_start = (current_start - timedelta(days=rules.ANOMALY_BASELINE_DAYS)
                                  if end.toordinal() >= WINDOW_DAYS + rules.ANOMALY_BASELINE_DAYS else None)
                if not baseline_start:
                    unsupported("date_boundary")
                    continue
                baseline_period = period(baseline_start, current_start - timedelta(days=1))
                baseline = [r.units_sold for r in rows if baseline_start <= r.date < current_start]
                evaluation.update(comparison_period=baseline_period, baseline_sample_count=len(baseline), current_observed_days=len(recent))
                if len(recent) != WINDOW_DAYS:
                    unsupported("incomplete_daily_coverage")
                    continue
                if len(baseline) < rules.ANOMALY_MIN_SAMPLES:
                    unsupported("insufficient_anomaly_samples")
                    continue
                q1, q3 = quartiles(baseline)
                iqr = q3 - q1
                if iqr == 0:
                    unsupported("zero_iqr")
                    continue
                for row in recent:
                    high = row.units_sold > q3
                    distance = (Fraction(row.units_sold) - q3) / iqr if high else (q1 - row.units_sold) / iqr
                    severity = next((label for threshold, label in rules.ANOMALY_BANDS if distance > threshold), None)
                    if not severity:
                        continue
                    bound = q3 + rules.ANOMALY_FENCE * iqr if high else q1 - rules.ANOMALY_FENCE * iqr
                    inputs = {"q1": exact(q1), "q3": exact(q3), "iqr": exact(iqr), "fence_multiplier": exact(rules.ANOMALY_FENCE),
                              "observed_units": str(row.units_sold), "direction": "high" if high else "low"}
                    ids = [evidence("observed_units", row.units_sold, "units", period(row.date, row.date), "observed_daily_units", "observed",
                                    "validated product/day units", observed=row.date.isoformat(), previous=baseline_period)]
                    for name, number, unit in (("q1", q1, "units"), ("q3", q3, "units"), ("iqr", iqr, "units"),
                                               ("baseline_samples", len(baseline), "observations")):
                        ids.append(evidence(name, number, unit, baseline_period, "statistical_baseline",
                                            "aggregated" if name == "baseline_samples" else "derived",
                                            "median of halves; exclude odd middle; IQR = Q3 - Q1; observed baseline days only"))
                    ids.append(evidence("relevant_bound", bound, "units", baseline_period, "detector_calculation", "derived",
                                        "Q3 + 1.5 * IQR (high) or Q1 - 1.5 * IQR (low); strict outside", inputs=inputs))
                    ids.append(evidence("quartile_distance", distance, "IQR multiples", period(row.date, row.date), "detector_calculation", "derived",
                                        "(observed - Q3) / IQR (high) or (Q1 - observed) / IQR (low)", inputs=inputs, previous=baseline_period))
                    emit(severity, ids, "Observed daily units {observed_units} are outside the relevant IQR bound {relevant_bound}, from {baseline_samples} baseline observations.", row.date.isoformat())

    return {"detector_schema_version": "detectors-v1", "issue_schema_version": ISSUE_SCHEMA,
            "evidence_schema_version": EVIDENCE_SCHEMA, "detection_period": current_period,
            "issues": issues, "evidence": sorted(builder.items.values(), key=lambda item: item["evidence_id"]),
            "evaluations": evaluations}
