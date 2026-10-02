# Deterministic detectors and evidence · V1

Contract defined before detector implementation. Phase 3 consumes immutable V1 records and Phase 2 `comparison`, `flows`, `latest_snapshots` and period semantics. No Phase 0–2 contract change is required. No AI, recommendations, financial assumptions, unit-price substitution or revenue reconstruction occurs. All five families operate per product using units sold; inventory is a snapshot selected once, never a sum over dates.

## Common windows, arithmetic and outcomes

E is the dataset maximum date, never today. Current period C=[E−6,E], previous P=[E−13,E−7], inclusive. Demand requires Phase 2's supported per-product comparison (seven observations in each window), with the same reason precedence. Inventory requires only complete C and a latest snapshot dated E; a prior comparison is unnecessary. No missing observations are zero-filled. Recorded zeros are valid observations.

`backend/app/detectors/config.py` is the single threshold/version location. Integer totals and rational arithmetic (`Fraction`) decide thresholds exactly; no rounded analytics percentages are inputs. Shared Phase 2 sums preserve Decimal money, though these detectors make no monetary claims. Derived ratios serialize as two-place ROUND_HALF_UP strings using a local 50-digit Decimal context. Every numeric evidence object also carries an exact numerator/denominator pair as integer strings; a later verifier must use this pair for exact thresholds and calculations. Integers remain exact JSON-safe values, using Phase 2's large-integer string rule. Rounding is presentation only, including normalization of rounded negative zero.

One evaluation per product/family: `issue_detected`, `evaluated_no_issue`, or `unsupported` with a machine-readable reason. Unsupported never means healthy. Evaluation metadata includes periods, observation/sample counts where relevant, and linked issue IDs. No orphan evidence is emitted: only detected issues create evidence. No-issue/unsupported evaluations are explicit even when the issue list is empty.

## Demand decline and spike

Versions: `demand_decline_v1`, `demand_spike_v1`. Let previous units B, current units N, delta=N−B, percentage=100×delta/B. Reuse supported Phase 2 comparison and its exact integer totals. B=0 causes `zero_previous_demand` for both families, even N=0. Unsupported Phase 2 coverage propagates its reason. No revenue-based demand assumptions.

| Family | LOW | MEDIUM | HIGH | No issue |
| --- | --- | --- | --- | --- |
| Decline | −35% < change ≤ −20% | −50% < change ≤ −35% | change ≤ −50% | change > −20% |
| Spike | 25% ≤ change < 50% | 50% ≤ change < 100% | change ≥ 100% | change < 25% |

Evidence: previous/current units and exact periods (`phase2_period_comparison`, aggregated), signed absolute units and percentage (`detector_calculation`, derived), with exact ratio inputs. Limits: week-to-week signals, no seasonality or causal claim; new demand from zero is intentionally unsupported. These fixed bands follow the requested V1 policy, not demo tuning.

## Stockout risk and excess inventory

Versions: `stockout_risk_v1`, `excess_inventory_v1`. Latest snapshot I must be dated E; older dates cause `stale_inventory_snapshot` before demand coverage checks. Require seven observations in C or `incomplete_daily_coverage`; unrepresentable C causes `date_boundary`. Recent demand U=sum units in C, daily demand D=U/7, coverage K=I×7/U days. U=0 causes `zero_recent_demand` for both families regardless of inventory; no infinity and no sixth detector.

| Family | LOW | MEDIUM | HIGH | No issue |
| --- | --- | --- | --- | --- |
| Stockout | 3 ≤ K < 7 | 1 < K < 3 | K ≤ 1 | K ≥ 7 |
| Excess | 30 < K ≤ 60 | 60 < K ≤ 90 | K > 90 | K ≤ 30 |

Zero inventory with positive demand yields K=0/HIGH stockout. Thirty days represents roughly one month of stock at the observed weekly rate; 60 and 90 days escalate to two/three months. These are transparent review thresholds, not optimized stocking targets. Inventory can still be outdated relative to real time: freshness is relative to the dataset only. No lead-time, incoming-order, seasonality, lost-sales or future-demand assumptions are made. Coverage is a constant-rate calculation, not a forecast or purchasing recommendation.

Evidence: latest inventory and date (`latest_inventory_snapshot`, observed); seven-day units (`phase2_current_period_units`, aggregated via shared flows); daily demand and inventory coverage (`detector_calculation`, derived), exact inputs and calculation method, current period. Latest inventory evidence uses a one-day observation period; derived coverage uses C and carries the snapshot date.

## Sales anomaly

Version `sales_anomaly_v1`. Target C is the latest seven calendar days; baseline is [E−34,E−7], the preceding 28 calendar days, excluding every target observation. Require all seven target product/day observations and at least 14 observed baseline product/days. Missing baseline days are excluded, never imputed; the baseline period and actual sample count make this explicit. Reasons in order: `date_boundary`, `incomplete_daily_coverage`, `insufficient_anomaly_samples`, `zero_iqr`. This minimum gives at least seven samples per half while allowing partially observed baseline history; it is a heuristic, not a significance test.

Sort observed baseline integer units. Median of even n is the mean of the middle two; median of odd n is the middle value. For quartiles split sorted values into lower/upper halves, excluding the overall middle when n is odd; Q1 and Q3 are those halves' medians. IQR=Q3−Q1. Lower fence Q1−1.5×IQR, upper fence Q3+1.5×IQR. A target x strictly outside either fence is an anomaly; equality is not. IQR=0 abstains even for a different target value (including constant series); no arbitrary epsilon. Recorded zero target/baseline values participate normally. Negative lower fences are not clamped.

Severity uses the distance beyond the relevant quartile in IQR units: LOW when distance >1.5 and ≤3; MEDIUM when >3 and ≤4.5; HIGH when >4.5. Equality at 3 stays LOW, at 4.5 stays MEDIUM. Emit one issue per anomalous target day; multiple days are supported. Never flag a mere minimum/maximum inside the fences. Evidence includes observed units/date (`observed_daily_units`, observed), Q1, Q3, IQR, baseline sample count (`statistical_baseline`, derived/aggregated), relevant 1.5×IQR bound and quartile-distance ratio (`detector_calculation`, derived). Baseline values are not exported as raw rows. Limitations: sparse baseline, small history, trends, intermittent sales and seasonality can affect this descriptive heuristic; no probability, confidence or cause is claimed.

## Versioned contracts and deterministic identity

Response: `detector_schema_version: detectors-v1`, `issue_schema_version: issues-v1`, `evidence_schema_version: evidence-v1`, `analysis_id`, `expires_at`, `detection_period` C (null at date boundary), `issues`, `evidence`, `evaluations`. Each issue has `issue_id`, `issue_type`, `entity_type: product`, `entity_id`, `entity_name`, `severity`, `detected_at`, `title`, `summary`, `evidence_ids`, `detector_version`, and `observation_date` (null except anomaly). `detected_at` is the ISO **dataset as-of date E**, not execution time or a fabricated timestamp. Anomaly observation date is separate. Summaries are fixed templates filled exclusively from attached evidence, with approximate ratios explicitly labeled rounded.

Evidence fields: `evidence_schema_version`, `evidence_id`, `entity_type`, `entity_id`, `metric`, `value`, `exact: {numerator, denominator}`, `unit`, `period`, `comparison_period` (null when inapplicable), `method`, `source: {name, kind}`, `inputs`, `observation_date`, `detector_version`. Source kind is `observed`, `aggregated` or `derived`; source names above specify provenance. Inputs are JSON-safe integer strings, dates, exact rational objects or method parameters. Evidence presents verified data, not trusted instructions; user-supplied product names remain untrusted labels for future AI work.

Canonical JSON uses sorted object keys, compact separators, UTF-8/ensure_ascii=False, and rejects non-finite numbers. Dataset identity hashes all normalized records sorted by (date, product_id), with dates ISO, money fixed to two decimals (already exact under V1), integers exact and optional nulls preserved. Whitespace/column-order/row-order variants with identical normalized content share identity. IDs are full SHA-256 digests with `iss_`/`ev_` prefixes.

Evidence hash input is `[dataset_digest, evidence-v1, semantic_evidence]`. Semantic evidence contains every evidence field before ID **except** rounded `value` and explanatory `method` text: schema version, entity type/ID, detector version, metric, exact numerator/denominator, unit, periods, source, calculation inputs and observation date. Issue hash input is `[dataset_digest, issues-v1, semantic_issue]`: every issue field before ID except `title`, `summary` and presentation `entity_name`; evidence IDs are sorted before hashing. Thus exact facts and classifications determine identity, not display precision, explanation wording or reference ordering. Response text and evidence order are preserved for presentation. Method/threshold semantics are fixed by detector version; changing them requires a version change, even if the explanatory wording is unchanged.

No unhashed raw values/dataset digest appear in IDs. SHA-256 collision resistance is assumed, not a mathematical uniqueness guarantee. IDs are reproducible across sessions containing identical normalized datasets; they grant no access and are never used as session handles. Changes anywhere in normalized content change IDs. No frontend order, dictionary insertion order, locale or wall clock contributes. The pre-commit adversarial audit corrected an earlier implementation that included display strings in the hash. Existing pre-audit Phase 3 IDs/screenshots were regenerated; Phase 0–2 contracts remain unchanged.

Output sorts products by ID, families by config order (decline, spike, stockout, excess, anomaly), anomalous dates ascending, and evidence by ID. Each evidence ID must resolve once and each evidence object must be referenced. All arrays/work are bounded by V1's 10,000 rows: five evaluations per product, at most four non-anomaly issues per product plus seven anomaly issues (the latter require 21+ rows/product), and at most eight evidence objects per issue. No calendar-span expansion, raw-row export, persistent cache or new infrastructure. Existing sessions/expiry/no-store/CORS remain; availability is checked before and after calculation.

GET `/api/v1/analysis/{analysis_id}/issues` retains Phase 1's 404 semantics for unknown/expired/released IDs. `/insights` keeps Phase 2 analytics accessible and adds issue-family filters, explicit evaluation status/reasons, and attached evidence inspection. Frontend filtering, pagination and text presentation never calculate detector metrics or assign severity.
