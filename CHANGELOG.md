# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-11-10

First publication as **GMI Savings Tracker v2**, a standalone repository.
Supersedes the original `EVO3-Ecosystem/gmi-savings-tracker`, whose history is
preserved there.

### Added

- **Pipeline & tests**: pre-recorded SODA fixtures so the extract suite runs
  fully offline (`tests/fixtures/soda/`); end-to-end integration test
  (extract → build → checks → export) on a sample database; contract tests
  generated from `docs/schemas` and the column dictionary.
- **Data sources**: State Plan priorities map (51 agencies, cited to the
  Moore–Miller 2024 State Plan); Office of Legislative Audits repeat-findings
  register (17 agencies, per-report citations); BLS Maryland nonfarm
  employment (2007–2026); BEA Maryland real GDP (1997–2025, chained 2017
  dollars).
- **Models**: LightGBM quantile forecast corridors (P10–P90) adopted on
  1,083 of 2,609 series in rolling validation; general-fund revenue model
  (FY2027 midpoint $29.7B); isolation-forest anomaly review queue (2,459
  flags); K-Means spending-mix clusters, now used as the peer-gap detector's
  benchmark groups; TF-IDF + K-Means grant-text clustering (40 program
  families over 23,084 grants); correlation heatmap figure.
- **Dashboard**: executive forecast-range and review-queue tiles; program
  drill-down on agency pages; review-queue CSV export with persisted review
  statuses; analyst-detail toggle; Agencies scatter and per-position
  histogram; Budget function → agency → program treemap; Opportunities PCA
  map and OLA findings card; freshness indicator in the header.
- **Platform**: DVC with a local-only store; optional `make postgres` loader;
  weekly freshness-alert workflow that opens GitHub issues when the portal
  updates; read-only MCP server over the marts (`mcp_server/`); roadmap
  timeline; README "What it found" section with traced figures.
- **Community**: MIT license, Contributor Covenant 2.1 code of conduct,
  contributing guide, security policy, support guide, governance doc,
  citation file, issue templates, PR template, CODEOWNERS, Dependabot.

### Verification

114 pipeline checks (113 pass, 1 documented warning), 174 unit/integration
tests, 36 dashboard page tests, 5 published-site tests — all green.

[2.0.0]: https://github.com/EVO3-Ecosystem/gmi-savings-tracker-v2/releases/tag/v2.0.0
