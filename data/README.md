# Demo data

`demo_business.csv` contains 540 deterministic synthetic daily observations: six fictional products, three categories, three supplier labels and 90 days (2026-01-01 to 2026-03-31). It matches the canonical V1 contract in docs/DATA_CONTRACT.md. All values/names are invented demo data; no private business information is included.

Load it through POST /api/v1/analysis/demo or the frontend's Load Demo Business button. It passes the same ingestion/validation pipeline as uploads. Varied demand and inventory history is reserved for later analytics/detector phases; Phase 1 only profiles dataset structure and data quality. Do not commit private business data.
