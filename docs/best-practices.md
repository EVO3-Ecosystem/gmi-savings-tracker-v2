# Best practices, standards and references

How this repository maps to the recognized standards for open-source
engineering, open government data, and public-facing dashboards — with the
sources. Last reviewed: November 10, 2026.

---

## 1. Repository & community standards

| Practice | Where it lives here | Reference |
|---|---|---|
| README, license, code of conduct, contributing guide, security policy, issue & PR templates | repo root, `.github/` | [GitHub Docs — About community profiles for public repositories](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories) |
| Contributor Covenant 2.1 | [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | [contributor-covenant.org](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) |
| Changelog in Keep a Changelog 1.1 format | [CHANGELOG.md](../CHANGELOG.md) | [keepachangelog.com](https://keepachangelog.com/en/1.1.0/) |
| Semantic Versioning for releases | [GOVERNANCE.md](../GOVERNANCE.md) | [semver.org](https://semver.org/spec/v2.0.0.html) |
| Machine-readable citation metadata | [CITATION.cff](../CITATION.cff) | [Citation File Format](https://citation-file-format.github.io/) |
| Dependency update automation | `.github/dependabot.yml` | [GitHub Docs — Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates) |
| CI on every push; lint gate | `.github/workflows/ci.yml` (ruff + pytest) | [GitHub Docs — About status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks) |

## 2. Open government data principles

| Principle | How the tracker implements it | Reference |
|---|---|---|
| Complete, primary, timely, machine-readable data | Full-history pulls (no sampling) directly from the state's primary API; freshness monitored against portal timestamps | [The 8 Principles of Open Government Data (2007)](https://opengovdata.org/) |
| Data is Findable, Accessible, Interoperable, Reusable (FAIR) | Persistent dataset IDs, documented schemas (`docs/schemas/`), column dictionary, license stated, provenance per table | Wilkinson et al., *The FAIR Guiding Principles for scientific data management and stewardship*, Scientific Data 3 (2016), [doi:10.1038/sdata.2016.18](https://doi.org/10.1038/sdata.2016.18) |
| Publication with purpose; open by default | Every figure on the dashboard traces to a named public dataset | [International Open Data Charter — Principles](https://opendatacharter.net/principles/) |
| Standard metadata | Per-dataset register with IDs, years, owners, known issues | [docs/data-sources.md](data-sources.md); [W3C DCAT vocabulary](https://www.w3.org/TR/vocab-dcat-3/) (portal-side) |
| Freshness monitoring with alerting | Weekly workflow compares portal `rowsUpdatedAt` to the published snapshot and opens an issue | `.github/workflows/freshness.yml`; practice recommended by [open data portal transparency guidance](https://freedomandsafety.com/en/content/blog/how-to-measure-transparency-of-open-government-data-portals/) |
| Data quality documentation | Known source issues and assumptions are published, not hidden | [docs/data-governance.md](data-governance.md) |

## 3. Pipeline engineering

| Practice | Where | Reference |
|---|---|---|
| API-based extraction with pagination, retry, self-healing | `src/pipeline/extract.py` | [Socrata Open Data API (SODA) docs](https://dev.socrata.com/) |
| Layered raw → ref → core → ops → mart modeling | `src/pipeline/build.py`, `src/pipeline/marts.py` | Kimball dimensional modeling; dbt Labs, [How we structure our dbt projects](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview) (pattern adapted, no dbt dependency) |
| Data tests with hard gates | `src/pipeline/checks.py` (stop vs warn; non-zero exit on anomalies) | dbt [data tests](https://docs.getdbt.com/docs/build/data-tests) concept; Great Expectations [expectations](https://greatexpectations.io/expectations/) (adapted dependency-free) |
| Reproducible, versioned runs | per-run raw snapshots + manifest; DVC local store | [DVC — data versioning](https://dvc.org/doc/use-cases/versioning-data-and-model-files) |
| Offline-capable tests | recorded SODA fixtures; no network in CI | `tests/fixtures/soda/`; [pytest monkeypatching](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) |
| End-to-end integration test | `tests/test_integration.py` | [Google Testing Blog — Just Say No to More End-to-End Tests](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html) (one deliberate E2E, unit tests elsewhere) |

## 4. Analytics & modeling

| Practice | Where | Reference |
|---|---|---|
| Rolling time-series validation instead of a single split | `src/models/` backtests | Hyndman & Athanasopoulos, [*Forecasting: Principles and Practice*, §5.8 Time series cross-validation](https://otexts.com/fpp3/tscv.html) |
| Prediction intervals with measured coverage | P10–P90 corridors; coverage reported on the dashboard | Hyndman & Athanasopoulos, [§5.5 Prediction intervals](https://otexts.com/fpp3/intervals.html) |
| Baseline-first modeling | naive benchmark must be beaten before a model is adopted | Hyndman & Athanasopoulos, [§5.2 Some simple forecasting methods](https://otexts.com/fpp3/simple-methods.html) |
| Quantile gradient boosting | LightGBM challenger (`objective=quantile`) | [LightGBM documentation](https://lightgbm.readthedocs.io/) |
| Unsupervised anomaly detection | isolation forest over vendor–agency–year patterns | Liu, Ting & Zhou, [*Isolation Forest* (ICDM 2008)](https://ieeexplore.ieee.org/document/4781136); [scikit-learn docs](https://scikit-learn.org/stable/modules/outlier_detection.html#isolation-forest) |
| Vendor market concentration screening | Herfindahl–Hirschman Index with the 1,800 threshold | [U.S. DOJ & FTC Merger Guidelines (2023)](https://www.justice.gov/d9/2023-12/2023%20Merger%20Guidelines.pdf) |

## 5. Dashboard & accessibility

| Practice | Where | Reference |
|---|---|---|
| Accessible charts (labels, aria, non-color cues) | dashboard page | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) |
| No pie charts; honest axes; uncertainty drawn, not hidden | page conventions | Few, S., *Show Me the Numbers*; Cairo, A., *The Truthful Art* |
| Every figure traceable to a named public source | Sources section on the page; `docs/data-sources.md` | [Sunlight Foundation — Open Data Policy Guidelines](https://sunlightfoundation.com/opendataguidelines/) |

## 6. Primary data sources (with citations)

| Source | Used for | Link |
|---|---|---|
| Maryland Open Data Portal (Socrata) | operating budget `yu65-jmmv`, funding `gy87-e27x`, positions `x8qy-486w`, payments `7syw-q4cy`, grants `absk-avps` | [opendata.maryland.gov](https://opendata.maryland.gov/) |
| Maryland Transparency Portal | budget stage statements, website reconciliation downloads | [mtp.maryland.gov](https://mtp.maryland.gov/) |
| DBM Operating Budget | budget stage confirmation (FY2026 Working, FY2027 Legislative Appropriation) | [operatingbudget.maryland.gov](https://operatingbudget.maryland.gov/) |
| Comptroller vendor payments | payment reconciliation | [vendorpayments.maryland.gov](https://vendorpayments.maryland.gov/) |
| Office of Legislative Audits | repeat audit findings per agency (`reference/ola_findings.csv`) | [ola.maryland.gov](https://ola.maryland.gov/) |
| Maryland State Plan (2024) | agency → priority mapping (`reference/state_plan_map.csv`) | [governor.maryland.gov/priorities](https://governor.maryland.gov/priorities/Pages/default.aspx) |
| DBM Managing for Results | agency performance measures (`mart.results_trend`) | [dbm.maryland.gov](https://dbm.maryland.gov/) |
| U.S. BLS Public Data API v2 | CPI-U; Maryland total nonfarm employment | [bls.gov/developers](https://www.bls.gov/developers/) |
| U.S. BEA regional accounts | Maryland real GDP (SAGDP9 bulk file) | [apps.bea.gov/regional](https://apps.bea.gov/regional/) |
| U.S. Census Bureau | Maryland population estimates (deflator spine) | [census.gov](https://www.census.gov/programs-surveys/popest.html) |
| USAspending API | federal award context; NAICS proof-of-concept | [api.usaspending.gov](https://api.usaspending.gov/) |
| Board of Public Works agendas | contract amendment research (`docs/research/naics-and-emma.md`) | [bpw.maryland.gov](https://bpw.maryland.gov/) |
| WYPR (Jan 10, 2025) | the $50M GMI savings target and consultant-fee terms | [wypr.org](https://www.wypr.org/wypr-news/2025-01-10/gov-moore-announces-plan-to-save-50m-by-modernizing-maryland-government) |

## 7. Explicitly out of scope, and why

- **OData endpoints** — SODA covers the same data; two APIs for one source doubles the maintenance surface.
- **Seasonal models (Prophet/Orbit)** — the data is yearly; payment dates are placeholders.
- **Fiscal-stress classification** — no labeled stress events exist to train on.
- **eMMA scraping** — login-gated behind reCAPTCHA; see the research note for the
  Board of Public Works alternative: [docs/research/naics-and-emma.md](research/naics-and-emma.md).
