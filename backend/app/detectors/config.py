"""V1 thresholds. Changing these rules requires a detector version change."""
from fractions import Fraction

FAMILIES = ("demand_decline", "demand_spike", "stockout_risk", "excess_inventory", "sales_anomaly")
VERSIONS = {name: f"{name}_v1" for name in FAMILIES}
DECLINE_BANDS = ((-50, "HIGH"), (-35, "MEDIUM"), (-20, "LOW"))
SPIKE_BANDS = ((100, "HIGH"), (50, "MEDIUM"), (25, "LOW"))
STOCKOUT_HIGH_DAYS = 1
STOCKOUT_MEDIUM_DAYS = 3
STOCKOUT_LOW_DAYS = 7
EXCESS_BANDS = ((90, "HIGH"), (60, "MEDIUM"), (30, "LOW"))
ANOMALY_BASELINE_DAYS = 28
ANOMALY_MIN_SAMPLES = 14
ANOMALY_BANDS = ((Fraction(9, 2), "HIGH"), (Fraction(3), "MEDIUM"), (Fraction(3, 2), "LOW"))
ANOMALY_FENCE = Fraction(3, 2)
