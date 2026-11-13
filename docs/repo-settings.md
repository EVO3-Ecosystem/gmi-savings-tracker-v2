# Repository settings (admin checklist)

Settings an admin applies by hand; they cannot be committed. Decided Nov 13, 2026 (decision record D5–D7). Apply the same
settings to both repositories: gmi-savings-tracker (flagship, v1) and gmi-savings-tracker-v2 (testing ground).

| Setting | Where | Value | Why |
|---|---|---|---|
| Branch ruleset on `main` | Settings → Rules → Rulesets → New ruleset → Import a ruleset: `.github/rulesets/main.json` | Require a pull request; require the `test` status check (CI), up to date with `main`; block force pushes; restrict deletions | [Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) |
| Dependabot alerts and security updates | Settings → Code security | Dependency graph on; Dependabot alerts on; Dependabot security updates on | [About Dependabot alerts](https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts) |
| Automatically delete head branches | Settings → General → Pull Requests | On | Merged branches are removed after each pull request |
| Socrata app token | data.maryland.gov → sign in → Developer settings → Create new app token; then Settings → Secrets and variables → Actions → `MD_SODA_APP_TOKEN` (and the local `.env`) | One token for the pipeline | Tokenless requests share a throttled IP pool ([Application Tokens](https://dev.socrata.com/docs/app-tokens)); `make extract-scheduled` and the CI extract stop without it |
| Pages deploy | Settings → Pages → Source: GitHub Actions | Only `.github/workflows/pages.yml` deploys | v2's `static.yml` uploaded the whole repository and shared the `pages` deploy group with `pages.yml`; delete it in v2 |
