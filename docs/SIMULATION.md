# Deterministic what-if simulation · V1

Phase 6 models one selected product, not a forecast or an autonomous order. All outcomes are hypothetical Python calculations; no LLM, price elasticity, financial claims or probabilities are used. Existing normalized records and observed analytics are never modified.

## Inputs and eligibility

POST `/api/v1/analysis/{analysis_id}/simulate` takes exactly `product_id` (nonempty string, max 200 characters), `baseline_reorder_quantity` (integer 0…1,000,000,000,000), `reorder_adjustment_percent` (integer −50…50), `demand_change_percent` (integer −30…30), and `horizon_days` (integer 7, 14 or 30). No coercion of strings, floats or booleans; extra fields are rejected. The baseline quantity is a user assumption, never inferred from an AI recommendation or selling price. Zero means no assumed receipt; percentage adjustments to zero remain zero.

GET `/{analysis_id}/simulation` lists sorted products, eligibility and aggregate source inputs. E is the maximum dataset date, not today's date. Require a latest inventory snapshot on E and one observation on every day of [E−6,E]. Missing days are not zero-filled. Reasons: `date_boundary`, `stale_inventory_snapshot`, `incomplete_daily_coverage`. Unknown products return 404 `product_not_found`; an ineligible product returns a structured 422 `simulation_unsupported`. Seven days suffice; the previous comparison window is unnecessary. Observed zero demand is eligible, but days-of-inventory and excess evaluation explicitly abstain.

## Exact formulas

I = latest inventory units; U = sum supplied units over the complete latest seven dataset days; D = U/7 units/day; Q = user baseline reorder quantity; H = horizon; a = reorder adjustment percent; b = demand scenario percent.

| Metric | Baseline | Scenario |
| --- | --- | --- |
| assumed receipt quantity R | Q | Q × (100+a)/100 |
| daily demand d | D | D × (100+b)/100 |
| projected demand P | d × H | d × H |
| available inventory A | I + R | I + R |
| projected ending inventory J | max(A−P, 0) | max(A−P, 0) |
| unmet demand units | max(P−A, 0) | max(P−A, 0) |
| days inventory remaining | J/d, if d>0 | J/d, if d>0 |
| potential stockout | P>A | P>A |
| potential excess stock | J/d > 30 days, if d>0 | J/d > 30 days, if d>0 |

The baseline shares the chosen H and Q but always uses zero demand/reorder adjustment. Comparison deltas are **scenario minus baseline**, calculated from exact values before rounding. Exactly depleted at the horizon (P=A) means no unmet demand, ending inventory zero and potential stockout false. The excess flag uses the Phase 3 LOW coverage boundary (>30), applied to hypothetical **ending** stock; equality at 30 is false. These are scenario conditions, not new observed issues or detector outputs. Zero d produces supported demand/ending/unmet/stockout values; remaining days and excess are unsupported/null with `zero_scenario_demand`, never infinity or a healthy classification.

All arithmetic uses exact rational numbers (`Fraction`), since inputs are unit counts and integer percentages. Every calculated numeric metric includes an exact numerator/denominator as strings and a two-place display string. Display alone rounds HALF_UP, implemented with integer quotient/remainder to avoid precision loss at ties; negative rounded zero displays 0.00. No rounding of receipts to purchasable whole units is implied: fractional units represent continuous scenario quantities, not an order instruction. Large quantities remain exact. Frontend only displays backend metrics and deltas.

## Assumptions and transport

The horizon starts immediately after the dataset end-of-day snapshot. The entire assumed receipt is available at its start, with no other receipts, returns, spoilage or reservations. Demand is uniform and constant for the horizon; unmet demand is not served later. No lead time, supplier capacity, seasonality or lost-sales revenue is modeled. Lead-time data, even when supplied, does not alter this immediate-receipt assumption. Calendar end dates are not constructed, so supported dataset dates near year 9999 remain valid. Revenue/unit_price are never inputs.

Both routes return `simulation-v1`, fixed session expiry, dataset as-of date, explicit provenance/periods, assumptions and hypothetical labels. POST returns distinct baseline/scenario plus exact comparison. No raw records, durable results, cache, session extension or new dependencies. Availability is checked before and after computation; unknown/expired/released sessions retain 404 semantics. Existing no-store and POST CORS/preflight apply. UI `/simulator` stores only analysis_id, clears transient inputs/results at expiry, supports retry and never calculates business outcomes in JavaScript.
