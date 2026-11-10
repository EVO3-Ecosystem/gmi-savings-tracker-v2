# Support

Thanks for your interest in the GMI Savings Tracker v2. This is a small
independent project — here's how to get help and where to file what.

## Where to ask

| Need | Where |
|---|---|
| A number on the dashboard looks wrong | [Open a **data issue**](../../issues/new?template=data_issue.yml) — tell us the tab, the figure, and what you expected |
| Something is broken (build, tests, page) | [Open a **bug report**](../../issues/new?template=bug_report.yml) with the command you ran and the error |
| Idea for a check, model, or chart | [Open a **feature request**](../../issues/new?template=feature_request.yml) |
| Security concern | **Do not open an issue** — see [SECURITY.md](SECURITY.md) |
| Question about Maryland's data itself | The state owns the source data — see [docs/data-sources.md](docs/data-sources.md) for the portal links and dataset owners |

## Response expectations

This project is maintained by one person. Issues are triaged weekly at best.
Pull requests that follow [CONTRIBUTING.md](CONTRIBUTING.md) get priority.

## Self-serve debugging

Most questions are answered by the repo itself:

- **What does this column mean?** `reference/column_dictionary.csv`
- **Where does this number come from?** `docs/data-governance.md` (sources, schemas, known source issues, assumptions)
- **Is the pipeline healthy?** `docs/checks.md` and the latest CI run
- **Why was a modeling choice made?** `docs/models/` (one model card per model)
- **What's planned?** `docs/roadmap.md`
