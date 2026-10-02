# Deterministic business metrics · V1

This contract is defined before implementation. Phase 2 consumes immutable normalized V1 records from Phase 1. Python is the sole numerical authority. The default reporting period is all observed data: inclusive minimum through maximum dataset date. No date filter or forecast is implemented. No use of today's date, external facts, AI, unit costs or inferred sales is allowed.

## Shared semantics

Revenue and units_sold are daily flows; sum supplied values across records in the stated period. Supplied revenue is authoritative and is never replaced with units × unit_price. Unit price is a selling price, not a cost. All amounts share the dataset owner's single unspecified currency; the API says `currency`, and the UI uses no invented currency symbol. Profit, margin, cost, working capital, ROI and savings are unsupported because their inputs do not exist.

Each supported metric contains `name`, `value`, `unit`, `period`, `status: supported`, and `reason: null`. Unsupported metrics use `value: null`, `status: unsupported` and a reason code, never a fabricated zero. Counts are JSON integers; money, averages and percentages are decimal strings. Integer quantities outside JavaScript's safe range (absolute value > 2^53−1) also serialize as decimal strings, including average numerators, to preserve exact UI values. Date coverage and comparison support are separate from observed-total support: a sparse dataset can have valid observed sums without supporting calendar-period comparisons.

No missing calendar day or missing product/day is filled with zero. A row with units_sold=0 is a genuine observed day and is included. `observed_days` counts distinct dates; `calendar_days` is the inclusive span. Product counts use distinct product_id; category counts use case-sensitive normalized category labels.

## Metric definitions

The following table applies to each stated scope (business, product, category or observed day). Aggregation only uses records in that scope/period. All count/sum metrics require at least one validated observation; no other minimum history is required. Zero sums are supported, and none of these metrics divides by a denominator.

| Metric | Exact formula and aggregation | Units | Window, assumptions and abstention |
| --- | --- | --- | --- |
| total_revenue | Sum supplied Decimal revenue; business, product, category and daily scopes | currency | Observed flows across period, not estimated revenue on missing dates. No observations → unsupported. Exact 2-place decimal string. |
| total_units_sold | Sum integer units_sold; business, product, category and daily scopes | units | Same observed-flow window; zero supported; exact integer. |
| product_count | Number of distinct product_id; business/category scopes | products | Products with at least one observation in period; exact integer. |
| category_count | Number of distinct category; business scope | categories | Categories represented in period; exact integer. |
| current_inventory_units | For each represented product select its maximum-date observation within the period, then sum those inventory integers once; business/product/category scopes | units | Last-known snapshot aggregate, never sum snapshots across time. No observations → unsupported. It is not guaranteed simultaneous or actual present-day stock. |
| average_units_per_active_day | Product total_units_sold / distinct observed product dates | units/observed_day | Active means observed (including observed zero sales), not only days with positive sales. At least one product/day; zero denominator → unsupported. Missing days are excluded rather than imputed. |
| average_revenue_per_active_day | Product supplied total_revenue / distinct observed product dates | currency/observed_day | Same denominator/minimum as above. Includes zero revenue; not realized selling price or profit. |
| date_range | Inclusive minimum and maximum observed dates | ISO calendar dates | Metadata, not a monetary metric; exists for nonempty validated data only. |

Averages expose exact numerator and integer denominator under `basis` so their rounded values are independently auditable. Product identity/name/category come from the validated contract. Categories aggregate their member products' flows and latest snapshots; category revenue and units reconcile exactly to business totals for the same reporting period.

## Inventory snapshot policy

Use each product's latest observation within the reporting period even if products' latest dates differ. Product output includes inventory observation date. Business/category output includes snapshot_date_range (earliest/latest selected snapshot dates), snapshot_product_count and mixed_snapshot_dates. This is explicitly labeled last-known inventory, not inventory as of today or a synchronized same-day balance. A product with no observation in a period would have unsupported inventory; never carry a pre-period snapshot into that period. Phase 2 inventory is reported only for the full observed period and never in the daily time series or period-change calculation.

## Daily time series

One date-sorted entry for each actually observed dataset date: total supplied revenue, total units_sold and observed_product_count. No artificial points on missing dates. A day's totals describe represented products only. No inventory sum or carry-forward is included. At most 10,000 entries because Phase 1 caps rows. Product/category arrays are sorted by product_id/category for deterministic output independent of CSV order.

## Comparable-period policy

Let E be the maximum observed dataset date, W=7 calendar days. Inclusive current window = [E−6, E]; previous window = [E−13, E−7]. They are adjacent, non-overlapping and equal-length. Both exact boundaries and length are returned. Windows never shift to today or shrink to hide insufficient history. If E is too early to represent both windows in Python's supported calendar, periods are null and comparisons abstain with date_boundary.

For each product, require one validated observation on all seven dates of both windows. The V1 unique product/date contract makes this equivalent to seven distinct observed dates per window. For business comparison require that coverage for **every product represented anywhere in the full dataset**; this conservative fixed cohort avoids assuming introduction/retirement or treating absent products as zero. Per-product comparisons are evaluated independently, so a complete product can be comparable when the business is not.

Reasons, in precedence order: `date_boundary`; `insufficient_history` when the dataset starts after previous-window start; `product_missing_in_period` if any cohort product has no observations in either window; `incomplete_daily_coverage` for remaining missing product/day observations. Metadata returns cohort product count, row/observed-day counts per window, incomplete_product_count and support/reason. No large list of inferred missing rows is generated.

Period observed totals may still be shown with a `basis: observed_records` label when the comparison is unsupported; if a window has no observations, its total metric is unsupported/null. Neither absolute nor percentage changes are emitted for unsupported comparisons.

For supported revenue and units_sold comparisons:

| Metric | Formula | Unit and precision | Support / zero behavior |
| --- | --- | --- | --- |
| absolute_change | current sum − previous sum | currency as exact 2-place decimal string, or units as integer | Requires supported comparable coverage. Signed values and zero are valid. |
| percentage_change | (current − previous) / previous × 100 | percent, 2-place decimal string | Requires supported comparison and previous > 0. Previous = 0 → unsupported/null with zero_previous_value even if current is also zero. Absolute change remains supported. |

No percentage growth from zero is labeled infinity or 100%; missing observations are not equivalent to zero recorded values. Category period changes are not implemented in Phase 2 (category performance is full-period aggregation). No inventory percentage trend is inferred from mixed-date snapshots.

## Precision, rounding and API

All money additions/subtractions are exact Decimal arithmetic. Calculations use a local Decimal context with 50 significant digits, sufficient for V1's 10,000 rows and 1e12 per-value limits and isolating results from a caller's global Decimal context. Division can recur, so ratios use that documented precision; exact numerator/denominator bases are preserved for averages. Only API-boundary averages and percentages are quantized to 0.01 with ROUND_HALF_UP. Supplied-money sums already have at most two fractional digits, so 2-place serialization does not discard precision. Integer counts/units are never rounded. Negative rounded zero is normalized to 0.00. The frontend displays returned strings without parsing money into binary floating point or recomputing business metrics.

GET `/api/v1/analysis/{analysis_id}/analytics` returns schema_version, analysis_id, fixed expires_at, reporting period/coverage, overview, products, categories, daily_time_series and period_comparison. Responses contain only aggregated metrics/metadata, not raw records. Product/day aggregates may necessarily coincide with an observation when the scope contains one row; this is not a raw-record export. Arrays are bounded by the 10,000-row contract; computation sorts/groups observed data rather than expanding the entire possible date span. No analytics cache is retained in sessions; the existing memory reservation and expiry contract remain unchanged.

Unknown, expired or released IDs retain Phase 1's 404 analysis_unavailable response. Session lifetime is not renewed. Availability is checked again after computation; a session expired/released during calculation is rejected before returning results. No Phase 1 ingestion/schema policies change.
