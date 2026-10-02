import hashlib
import json
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction

from app.analytics.metrics import json_integer

ISSUE_SCHEMA = "issues-v1"
EVIDENCE_SCHEMA = "evidence-v1"


def canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def dataset_identity(records) -> str:
    rows = []
    for record in sorted(records, key=lambda r: (r.date, r.product_id)):
        row = asdict(record)
        row["date"] = record.date.isoformat()
        row["revenue"] = format(record.revenue, ".2f")
        row["unit_price"] = format(record.unit_price, ".2f")
        rows.append(row)
    return canonical_hash(rows)


def exact(value) -> dict:
    ratio = Fraction(value)
    return {"numerator": str(ratio.numerator), "denominator": str(ratio.denominator)}


def display(value):
    if isinstance(value, int):
        return json_integer(value)
    ratio = Fraction(value)
    with localcontext() as context:
        context.prec = 50
        result = (Decimal(ratio.numerator) / Decimal(ratio.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(abs(result) if not result else result, ".2f")


class EvidenceBuilder:
    def __init__(self, dataset_id):
        self.dataset_id = dataset_id
        self.items = {}

    def add(self, *, entity_id, detector_version, metric, value, unit, period,
            comparison_period=None, method, source, inputs=None, observation_date=None):
        body = {"evidence_schema_version": EVIDENCE_SCHEMA, "entity_type": "product", "entity_id": entity_id,
                "detector_version": detector_version, "metric": metric, "value": display(value), "exact": exact(value),
                "unit": unit, "period": period, "comparison_period": comparison_period,
                "method": method, "source": source, "inputs": inputs or {}, "observation_date": observation_date}
        # Identity represents the exact fact, independent of display precision/prose.
        identity = {key: item for key, item in body.items() if key not in {"value", "method"}}
        key = "ev_" + canonical_hash([self.dataset_id, EVIDENCE_SCHEMA, identity])
        self.items[key] = {"evidence_id": key, **body}
        return key

    def issue(self, body):
        identity = {key: item for key, item in body.items() if key not in {"title", "summary", "entity_name"}}
        identity["evidence_ids"] = sorted(body["evidence_ids"])
        return {"issue_id": "iss_" + canonical_hash([self.dataset_id, ISSUE_SCHEMA, identity]), **body}
