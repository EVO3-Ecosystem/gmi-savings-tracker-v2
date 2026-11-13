# Governance

GMI Savings Tracker v2 is an independent, volunteer-run civic data project.
It is **not** an official State of Maryland product, and no state agency
reviews or endorses its findings.

## Roles

- **Maintainer** — [@snapaiarchitect](https://github.com/snapaiarchitect)
  (Sierra Napier), EVO3 Ecosystem. Owns the roadmap, reviews and merges all
  changes, and is the final decision-maker on methodology.
- **Contributors** — anyone who opens a pull request or issue. Meaningful
  contributions are credited in [CHANGELOG.md](CHANGELOG.md).

## How decisions are made

1. **Methodology decisions** (detectors, thresholds, models, reconciliation
   rules) are made by the maintainer and **written down**: every material
   choice lives in `reference/*.csv`, `docs/models/`, or
   `docs/data-governance.md`. A decision that isn't documented doesn't count.
2. **Data corrections** beat opinions. If the state's published data
   contradicts the tracker, the tracker changes — cite the source in the
   issue and it will be verified against the portal.
3. **Objectivity rule.** Findings must be reproducible from public data by
   running the pipeline. Commentary, advocacy, and partisan framing are out
   of scope for the repo.

## Change control

- All changes land via pull request; CI (tests + lint) must be green.
- `CODEOWNERS` routes review to the maintainer.
- Pipeline changes that alter published numbers require a note in the PR
  describing the before/after and its cause, and the parity reports in
  `docs/parity/` must be regenerated.
- Releases follow [Semantic Versioning](https://semver.org): data refreshes
  are patch releases, new marts/charts are minor, breaking schema changes to
  exported files are major.

## Trademark & naming

"GMI" refers to the State of Maryland's Government Modernization Initiative;
the name is used here descriptively under nominative fair use. If the state
objects to the naming, open an issue and it will be revisited.
