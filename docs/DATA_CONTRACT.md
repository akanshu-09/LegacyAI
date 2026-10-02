# Canonical CSV data contract · V1

Each row is one product's daily sales and end-of-day inventory observation. Use one row per `(date, product_id)`. All data must belong to one business, one currency and one consistent reporting timezone; currency/timezone are supplied by the dataset owner and are not inferred or converted in Phase 1. Do not combine warehouses or businesses without preparing a supported daily aggregate upstream.

## Fields

| Column | Required | Meaning and internal type | Units and validation |
| --- | --- | --- | --- |
| date | Yes | Observation day; Python `date` | Exact valid `YYYY-MM-DD`; no timestamps or guessed day/month order. |
| product_id | Yes | Stable product identifier; `str` | Nonblank, at most 200 characters; preserve case and leading zeros. One ID must map to the same name/category throughout the dataset. |
| product_name | Yes | Human-readable product label; `str` | Nonblank, at most 200 characters. |
| category | Yes | Product category label; `str` | Nonblank, at most 200 characters; case-sensitive. |
| units_sold | Yes | Units sold on that day; `int` | Nonnegative whole units, ASCII digits only; at most 1,000,000,000,000. Fractional units and negative returns are unsupported. |
| revenue | Yes | Reported sales revenue for the product/day; `Decimal` | Nonnegative currency amount, plain decimal, at most two fractional digits and 1,000,000,000,000. No symbols, separators, exponent, NaN or infinity. |
| inventory | Yes | End-of-day units on hand; `int` | Nonnegative whole units with the same integer bound. This is a snapshot, not a daily flow. |
| unit_price | Yes | Reported reference selling price per unit; `Decimal` | Currency per unit, same decimal rules/bound as revenue. Zero is allowed. |
| supplier | No | Supplier label; `str` or `None` | Up to 200 characters; blank/absent becomes null. |
| lead_time_days | No | Stated replenishment lead time; `int` or `None` | Nonnegative whole calendar days, same integer bound; blank/absent becomes null. |

Text values cannot contain control characters (including embedded tabs/newlines). Header names must match exactly, case-sensitively. Column order may vary; repeated headers, unsupported additional columns and missing required headers cause rejection. No aliases or unrelated columns are renamed.

## CSV format and normalization

UTF-8, optionally with a BOM; comma separator; standard CSV quoted fields; CRLF or LF line endings. Quoted commas and doubled quotes inside quoted fields are supported. Bare quotes in unquoted fields and characters after closing quotes are rejected. Every data row must have exactly the header's field count. Blank physical rows are errors, not silently skipped. Empty files and header-only files are rejected. Parser/encoding errors have structured responses.

Leading/trailing whitespace in values is trimmed and counted in the quality report; header whitespace is not repaired. Identifiers stay strings, dates become `date`, counts become `int`, and money becomes `Decimal` without floating-point conversion or rounding. Original bytes and filenames are not persisted. No imputation, currency conversion, time aggregation, business metric calculation or AI processing occurs.

Revenue is accepted as a reported amount. Phase 1 does not assert `revenue == units_sold * unit_price`: discounts and reporting conventions can differ. Its economic correctness and later supported business formulas belong to Phase 2. Returns, fractional unit sales, multiple currencies and conflicting product labels are unsupported; prepare a compliant source rather than relying on guesses.

## Missing values and duplicates

Required blank values reject the entire dataset. Optional blank/absent values stay null and appear in per-field missing counts and warnings. Strings such as `NA`, `null` or `-` are not missing-value aliases: numeric/date fields reject them, while textual fields preserve them as literal labels.

Exact normalized duplicates reject the entire dataset; no rows are dropped or summed. Numeric equivalents such as `20` and `20.00` compare equal. A second row for the same product/day with different values also rejects the dataset as a conflicting daily observation. Resolve duplicates upstream; inventory snapshots cannot safely be summed. No partially validated dataset creates a session.

Errors identify the CSV record number (header = record 1), column when applicable, code and corrective message. Embedded CSV line breaks can mean a record spans multiple physical lines. At most 100 detailed issues are returned, with the total error count and a truncation flag. Input values are not echoed in field errors. The quality report includes missing counts, duplicates, conflicting product/date counts, normalization counts and policies. For rejected datasets, missing counts cover rows with the expected width; malformed-width rows have their own error. Row order is preserved in normalized data; no sorting or aggregation is performed.

## API

All endpoints use `/api/v1/analysis`; JSON responses have `Cache-Control: no-store`.

| Method/path | Request | Response |
| --- | --- | --- |
| POST `/upload` | Raw CSV bytes, `Content-Type: text/csv` (or `application/octet-stream`); not multipart | 201 with `analysis_id`, `expires_at` (UTC ISO timestamp), `source: upload`, and `profile` |
| POST `/demo` | No body required | Same 201 response, `source: demo`; same validation pipeline |
| GET `/{analysis_id}` | Opaque analysis ID | 200 session metadata and structural profile; never raw records |
| DELETE `/{analysis_id}` | Opaque analysis ID | 204, releases session immediately |

Profile: row/product/category counts, minimum/maximum dates, exact recognized schema and absent optional columns, per-field missing counts, duplicate information, warnings and validation status. Counts describe dataset structure; they are not sales/inventory insights.

Error shape: `{"error":{"code":"validation_failed","message":"...","errors":[{"row":2,"column":"date","code":"invalid_date","message":"..."}],"errors_truncated":false,"row_count":1,"schema":{...},"data_quality":{...}}`. Schema/parser/transport failures include only relevant details. Codes include `invalid_schema`, `empty_csv`, `malformed_csv`, `invalid_encoding`, `validation_failed`, `upload_too_large`, `too_many_rows`, `unsupported_media_type`, `invalid_content_length`, `session_capacity`, `demo_unavailable` and `analysis_unavailable`.

Status codes: 422 for data validation, 413 for byte/row limits, 415 for unsupported media, 400 for invalid Content-Length, 503 for capacity/unavailable demo, and 404 for unknown/expired/released sessions. A failed new upload preserves any existing frontend session.

## Limits and session lifecycle

- Maximum upload: 2 MiB (2,097,152 bytes), enforced from Content-Length when supplied and from accumulated streamed bytes even without it. Maximum data rows: 10,000. Both are fixed V1 limits.
- Lifetime: absolute 30 minutes of elapsed monotonic time from creation, not extended by reads or wall-clock corrections. The UTC expires_at timestamp is computed once for display. Independent opaque IDs use 32 random bytes. Sessions are isolated; immutable records and separate profile copies prevent cross-session modification.
- Process-local capacity: 20 sessions and 64 MiB of conservative normalized-data reservations. Each reserves 2 MiB plus 4 KiB per row; with text and number bounds this budgets overhead beyond raw file size. This bounds retained data, not total interpreter/RSS or simultaneous transport buffers. Full capacity returns 503 and does not evict active sessions.
- Expired sessions are removed on create/read/delete and by a sweep every 60 seconds while the app runs. Requests at/after expiry return 404 even before the sweep. Unknown, expired and released IDs share the same recovery response. Shutdown/restart clears memory; users must upload/load again.
- No database, filesystem upload persistence or raw record retrieval API. Only the synthetic repository demo is read from disk. The browser saves only `analysis_id` in tab-scoped sessionStorage; profile/expiry metadata is held transiently for display. Files are cleared from the input after sending.
- Loading a new dataset creates a separate session; previous sessions remain bounded by their original expiry. Release the current session before replacing it if immediate cleanup is desired. Closing a browser tab does not immediately delete its backend session.
- IDs are capability handles, not authenticated user identities. Anyone who possesses an ID can read its profile or release it. Do not share IDs. This is a local, unauthenticated phase; CORS is not an authorization boundary. A single backend process is required because multiple workers would hold separate stores. Deployment planning belongs to Phase 7.

## Demo

`data/demo_business.csv` is entirely synthetic: 540 daily rows, six products, three categories, three fictional supplier labels, 2026-01-01 through 2026-03-31, and all ten columns. Its fixed history includes varied demand/inventory patterns to support later tests. Phase 1 only validates/profiles these observations; it labels no issues and makes no recommendations.
