# Model card — Anomaly flags and the review queue (`src/models/anomaly.py`)

## What it does
Flags unusual vendor-agency-year payments and agency-code-year budget lines with an isolation forest, and puts them
in `mart.review_queue` (exported as `review_queue.csv`) for human triage.

## What it does not do
Payments are **yearly totals per vendor and agency, not invoices**. Duplicate invoices, off-cycle payments and
unit-price variances cannot appear in this data and are not claimed. A flag means "worth a look", never "wrong":
the status column (`Under review` / `Approved variance` / `Refer to OLA`) is the human decision layer.

## Inputs
- `mart.vendor_agency_year` (full years only; partial years excluded)
- `core.fact_budget_scope` joined to `ref.dim_stage` (controllable purchases, actual years)
- `mart.d_opps`, `mart.d_bid_list` for the rule-detector overlap column

## Features (each robustly scaled: median and interquartile range)
Vendor grain: log amount, year-over-year change (consecutive years only), share of the agency's payments that year,
share of the vendor's statewide payments, how many agencies paid the vendor.
Budget grain: log amount, year-over-year change, share of the agency's controllable budget, share of the code
statewide.

## Validation
- Every vendor flag ties to its `vendor_agency_year` row to the dollar (stop check)
- Flagged share warned when far from the configured contamination (3%)
- Deterministic: fixed seed (`anomaly.seed`); same data, same flags
- Constructed-case tests: a planted 40x spike is flagged; a jittered smooth panel is not flooded

## Limits
- First build (Nov 2026): 2,459 flags from 81,928 scored rows (3.0%); 672 already covered by the rule detectors
- Flags are unlabelled screening: precision depends on triage, which the status history records
