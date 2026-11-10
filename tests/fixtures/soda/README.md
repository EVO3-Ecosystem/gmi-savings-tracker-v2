# Recorded SODA responses (offline test doubles)

Tiny, synthetic-but-schema-faithful recordings of the Maryland open data portal
(`opendata.maryland.gov`, SODA API) used by `src/pipeline/extract.py`. Column names and value
shapes were checked against the live portal on 2026-11-09 (`$limit=1` per dataset); the rows
themselves are synthesized so the fixtures stay a few KB and never need the network.

Layout, keyed by portal dataset id (see `config/datasets.yaml`):

- `metadata/<dataset_id>.json` — served for `GET /api/views/<dataset_id>.json`
  (`Socrata.get_metadata`; only `rowsUpdatedAt` and `name` are read by the extract).
- `rows/<dataset_id>.json` — the dataset's full row set as SODA JSON (all values strings).
  Served for `GET /resource/<dataset_id>.json`:
  - plain paged downloads (`$limit` / `$offset`) slice this array;
  - `select=count(*) as n` answers its length;
  - the per-year totals query (`select=<year> as fiscal_year, sum(<col>) as total, count(*) as rows`)
    is computed from the same rows, so portal totals and downloads always agree.

The wiring lives in `tests/conftest.py` (`soda_portal` fixture), which monkeypatches
`requests.Session.get` — the only HTTP call sodapy makes — and fails any URL outside the
recorded routes, so a test that accidentally reaches for the network fails instead of hanging.

Per-dataset numbers (kept consistent by construction; update both files together if edited):

- `yu65-jmmv` budget: FY2024-26, agencies D01/D02; yearly totals 1500 / 1650 / 1800.
- `gy87-e27x` fund: same years; per-year sums match budget exactly (a Phase 2 check ties them).
- `x8qy-486w` fte: FY2024-26, three rows.
- `7syw-q4cy` payments: FY2024-26 (FY2026 is the partial year), vendors ACME TESTING LLC /
  BETA ANALYTICS INC, `category` carries the budget agency code (as coded rows do on the portal).
- `absk-avps` grants: FY2024 grant + FY2025 loan.
- `4mca-332u` highered: FY2024-26, agency R30 (public higher education).
