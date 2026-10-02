"""Deterministic query execution engine for Ask LegacyAI.

Computes authoritative factual business answers and evidence using Python analytics only.
"""

from typing import Any
from app.analytics.metrics import calculate_analytics
from app.detectors.engine import detect_issues
from app.schemas.ask import AskIntent, FactualFinding


def execute_ask(
    records: list[Any],
    intent: AskIntent
) -> tuple[FactualFinding, list[dict[str, Any]], dict[str, Any] | None]:
    if not intent.supported or intent.intent_type == "unsupported":
        finding = FactualFinding(
            finding="LegacyAI cannot answer this request reliably using the active dataset.",
            why=intent.reason or "The requested question or metric is unsupported by dataset evidence.",
            metrics={}
        )
        return finding, [], None

    analytics = calculate_analytics(records)
    detection = detect_issues(records)
    all_issues = detection.get("issues", [])
    all_evidence = detection.get("evidence", [])
    evidence_by_id = {ev["evidence_id"]: ev for ev in all_evidence}

    overview = analytics.get("business_overview", {})
    products = analytics.get("product_summaries", [])
    categories = analytics.get("category_summaries", [])

    recommendation = None
    relevant_evidence: list[dict[str, Any]] = []

    if intent.intent_type == "business_overview":
        finding = FactualFinding(
            finding=f"Total business revenue was {overview.get('total_revenue', '0.00')} across {overview.get('total_units_sold', 0)} units sold ({overview.get('total_products', 0)} products, {overview.get('total_categories', 0)} categories).",
            why=f"Analyzed {overview.get('total_observations', 0)} daily sales observations from {overview.get('start_date')} to {overview.get('end_date')}.",
            metrics=overview
        )
        # Select representative evidence from detection or analytics
        relevant_evidence = all_evidence[:5]

    elif intent.intent_type in ("top_risks", "inventory_risk"):
        if all_issues:
            high_sev = [i for i in all_issues if i.get("severity") == "HIGH"]
            med_sev = [i for i in all_issues if i.get("severity") == "MEDIUM"]
            primary = high_sev[0] if high_sev else (med_sev[0] if med_sev else all_issues[0])

            finding = FactualFinding(
                finding=f"Detected {len(all_issues)} priority risk(s) in active session. Top issue: {primary.get('title')} on {primary.get('entity_name')} ({primary.get('severity')} severity).",
                why=primary.get("summary", "Rule detector triggered based on verified thresholds."),
                metrics={"total_issues": len(all_issues), "high_severity": len(high_sev)}
            )

            cited_ids = set(primary.get("evidence_ids", []))
            relevant_evidence = [ev for ev in all_evidence if ev.get("evidence_id") in cited_ids]

            recommendation = {
                "action": f"Investigate {primary.get('title')} for {primary.get('entity_name')}.",
                "target": primary.get("entity_name"),
                "timeframe_days": 14,
                "issue_id": primary.get("issue_id")
            }
        else:
            finding = FactualFinding(
                finding="No critical inventory or demand risk issues were detected in the active dataset.",
                why="All evaluated products satisfied normal demand coverage and statistical anomaly thresholds.",
                metrics={"total_issues": 0}
            )
            relevant_evidence = []

    elif intent.intent_type in ("product_performance", "demand_change"):
        target = intent.target_entity
        p_match = None
        if target:
            p_match = next((p for p in products if p.get("product_name", "").lower() == target.lower() or p.get("product_id", "").lower() == target.lower()), None)

        if p_match:
            finding = FactualFinding(
                finding=f"Product {p_match.get('product_name')} ({p_match.get('product_id')}) generated {p_match.get('total_revenue')} revenue across {p_match.get('total_units_sold')} units sold, with {p_match.get('latest_inventory')} units currently in stock.",
                why=f"Observed from {p_match.get('observation_count')} daily records between {p_match.get('start_date')} and {p_match.get('end_date')}.",
                metrics=p_match
            )
            # Find evidence related to product
            pid = p_match.get("product_id")
            relevant_evidence = [ev for ev in all_evidence if ev.get("entity_id") == pid]
        else:
            top_p = products[0] if products else {}
            finding = FactualFinding(
                finding=f"Top performing product is {top_p.get('product_name')} with {top_p.get('total_revenue')} revenue and {top_p.get('total_units_sold')} units sold.",
                why="Ranked by total revenue across all dataset products.",
                metrics=top_p
            )
            relevant_evidence = all_evidence[:3]

    elif intent.intent_type == "category_performance":
        cat_summary = ", ".join([f"{c.get('category')}: {c.get('total_revenue')}" for c in categories])
        finding = FactualFinding(
            finding=f"Business operates across {len(categories)} categories: {cat_summary}.",
            why="Aggregated daily sales totals by category.",
            metrics={"category_count": len(categories), "categories": categories}
        )
        relevant_evidence = all_evidence[:3]

    elif intent.intent_type == "recommend_action":
        if all_issues:
            top_issue = all_issues[0]
            finding = FactualFinding(
                finding=f"Recommended priority action: Review {top_issue.get('title')} for {top_issue.get('entity_name')}.",
                why=top_issue.get("summary", "Highest priority issue detected by Python analytics."),
                metrics={"issue_id": top_issue.get("issue_id")}
            )
            cited_ids = set(top_issue.get("evidence_ids", []))
            relevant_evidence = [ev for ev in all_evidence if ev.get("evidence_id") in cited_ids]
            recommendation = {
                "action": f"Review reorder quantity and supply lead time for {top_issue.get('entity_name')}.",
                "target": top_issue.get("entity_name"),
                "timeframe_days": 14,
                "issue_id": top_issue.get("issue_id")
            }
        else:
            finding = FactualFinding(
                finding="No immediate corrective action required based on current dataset observations.",
                why="No stockout, excess inventory, or demand decline issues were detected.",
                metrics={}
            )
            relevant_evidence = []

    else:
        finding = FactualFinding(
            finding=f"Business total sales: {overview.get('total_revenue', '0.00')} across {overview.get('total_units_sold', 0)} units.",
            why="Computed from verified sales records.",
            metrics=overview
        )
        relevant_evidence = all_evidence[:3]

    return finding, relevant_evidence, recommendation
