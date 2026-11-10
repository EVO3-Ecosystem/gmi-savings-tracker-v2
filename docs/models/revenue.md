# Model card — General Fund revenue forecast (`src/models/revenue.py`)

## What it does
Forecasts total Maryland General Fund revenue for the budget year being decided (FY2027) with a p10-p50-p90 band,
from the sourced history in `reference/gf_revenue_history.csv` (FY2017-FY2026, budgetary basis, one-time items
included). Review idea #27 — declined while the tracker held no revenue data, reinstated once the closeout/BRE
history was compiled with a source per row.

## Candidates and selection
Four candidates — naive (last actual), drift (average yearly growth), log-linear trend, trend + CPI (the only macro
regressor the pipeline already loads, `core.cpi_fy`) — scored in a rolling-origin backtest (origins FY2021-FY2025,
train through the origin, predict the next year). The kept model has the lowest mean MASE; a tie goes to the simpler
model. MASE scales come from each origin's own training window, so no future value enters a score.

## Bands
Seeded residual bootstrap (4,000 paths), refit per path with a random walk of resampled one-step log changes, so the
range widens with the horizon. CPI beyond its last complete fiscal year is extended at its trailing five-year growth
rate, and only used if the trend + CPI model is the one kept.

## Known limits (read before quoting the FY2027 number)
- **Ten annual points.** This is a disciplined baseline, not an econometric forecast; the band is the honest part.
- One-time items stay in the series: FY2021 extraordinary receipts (~$359M FEMA/TEDCO), the FY2023 $800M Blueprint
  distribution (a reported-revenue reduction), the FY2024 $150M LITRF transfer, FY2026 $405M extraordinary revenues.
  The model forecasts total GF revenue as reported, not ongoing revenue.
- Coverage is measured on five origins only; treat the p10/p90 as "likely", not "certain". The build reports measured
  coverage as a warning so a badly miscalibrated band cannot pass silently.
- BLS employment and BEA regional GDP regressors are the planned additions (review idea #27's original design);
  CPI is the only macro series the extract step already carries.

## Build-time checks (`phase5_revenue`)
Actuals tie to the reference CSV to the dollar; bands ordered and non-negative; the kept model matches or beats the
naive baseline (warning otherwise); FY2027 midpoint implies a plausible one-year growth rate (-10% to +15%).
