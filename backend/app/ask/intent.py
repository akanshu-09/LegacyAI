"""Intent classification module for Ask LegacyAI.

Parses user natural language questions into structured supported intents or explicit abstention.
"""

import re
from typing import Any
from app.schemas.ask import AskIntent

UNSUPPORTED_KEYWORDS = [
    r"\bprofit\b", r"\bmargin\b", r"\bcost\b", r"\bcarrying cost\b",
    r"\bworking capital\b", r"\bemployee\b", r"\bsalary\b", r"\bforecast\b",
    r"\bpredict\b", r"\bml\b", r"\bneural\b", r"\bsql\b", r"\bdatabase\b",
    r"\bweather\b", r"\bcompetitor\b", r"\bdiscount\b"
]


def classify_intent(question: str, records: list[Any] | None = None) -> AskIntent:
    q_lower = question.lower().strip()

    # 1. Check for unsupported topics
    for pattern in UNSUPPORTED_KEYWORDS:
        if re.search(pattern, q_lower):
            matched = pattern.strip(r"\b")
            return AskIntent(
                intent_type="unsupported",
                supported=False,
                reason=f"Topic or metric '{matched}' is not present in the dataset (V1 dataset contains selling unit_price and units, not cost/profit or external predictive data)."
            )

    # 2. Extract potential product target from records if available
    target_product_id = None
    target_product_name = None
    if records:
        for r in records:
            p_name = getattr(r, "product_name", "").lower()
            p_id = getattr(r, "product_id", "").lower()
            if p_name and p_name in q_lower:
                target_product_id = r.product_id
                target_product_name = r.product_name
                break
            elif p_id and p_id == q_lower:
                target_product_id = r.product_id
                target_product_name = r.product_name
                break

    # 3. Rule-based intent matching
    if any(kw in q_lower for kw in ["risk", "stockout", "excess", "overstock", "shortage"]):
        return AskIntent(
            intent_type="inventory_risk",
            target_entity=target_product_name or target_product_id,
            supported=True
        )

    if any(kw in q_lower for kw in ["decline", "spike", "drop", "growth", "demand", "units sold"]):
        return AskIntent(
            intent_type="demand_change",
            target_entity=target_product_name or target_product_id,
            supported=True
        )

    if any(kw in q_lower for kw in ["recommend", "action", "should we do", "what to do", "next step"]):
        return AskIntent(
            intent_type="recommend_action",
            target_entity=target_product_name or target_product_id,
            supported=True
        )

    if any(kw in q_lower for kw in ["category", "categories"]):
        return AskIntent(
            intent_type="category_performance",
            target_entity=None,
            supported=True
        )

    if target_product_id:
        return AskIntent(
            intent_type="product_performance",
            target_entity=target_product_name or target_product_id,
            supported=True
        )

    if any(kw in q_lower for kw in ["overview", "summary", "performance", "business", "total", "revenue", "how is"]):
        return AskIntent(
            intent_type="business_overview",
            target_entity=None,
            supported=True
        )

    if any(kw in q_lower for kw in ["top risk", "risks", "issue", "issues", "problem"]):
        return AskIntent(
            intent_type="top_risks",
            target_entity=None,
            supported=True
        )

    # Default fallback for recognized business queries
    return AskIntent(
        intent_type="business_overview",
        target_entity=None,
        supported=True
    )
