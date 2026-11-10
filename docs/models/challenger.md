# Model card — LightGBM quantile challenger (`src/models/challenger.py`)

## What it does
Forecasts next year's controllable spending for every agency x spending-code series (2,609 series for FY2026) with a
global LightGBM quantile model (alpha 0.1 / 0.5 / 0.9 — the fiscal risk corridor), **kept only where it beats the
naive last-value forecast** in rolling-origin validation. Everything else stays naive, and each row names its model.

## Why quantile regression
Decision #25/#26 of the review: P10-P90 corridors instead of a point estimate, produced by quantile objectives rather
than bootstrap alone, so best- and worst-case bounds come from the model itself.

## Features (lagged only — no current or future value enters a training row)
Log spend lags 1-3, lag-1 log growth, 3-lag mean, the agency's and the code's prior-year log totals, and the year index.

## Validation (rolling origin, never shuffled)
- Origins FY2022, FY2023, FY2024: train through the origin, predict the next year
- MASE per series, scale from each origin's own training window; adoption requires at least 2 scored origins and a
  strictly lower mean MASE than naive (a stop check re-verifies this on every build)
- Band coverage measured on the same origins and reported as a build warning: 73.2% vs the nominal 80%
  (bands are honest but narrow; treat the p10/p90 as "likely", not "certain")
- First build: challenger kept for 1,083 of 2,609 series (41.5%)

## Statewide corridor (`mart.d_challenger_total`)
Per-series p10/p90 are not additive — every series does not hit its own tail in the same year — so the statewide
corridor is simulated: each series is drawn log-normally within its kept band (median p50, log sigma from the band
width, draws clamped to the band edges — the same convention as the savings calculator) and the draws are summed path
by path (4,000 paths, seeded).
One row per build: fiscal_year, p10/p50/p90, n_series, n_adopted. A stop check verifies the band is ordered, covers
every series, and sits within 0.5x-2x of the last actual controllable total.

## Limits
- One-year-ahead only; nine actual years is a short history for a global model
- No macro regressors yet (CPI is loaded; BLS employment and BEA GDP are the planned additions)
- Revenue is forecast separately (`reference/gf_revenue_history.csv`); this model covers spending only
