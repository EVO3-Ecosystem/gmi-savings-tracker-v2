# RETIRED (Nov 13, 2026): Grant program families (`src/models/grant_clusters.py`)

**Retired in v3 in favour of [grant groups](grant_groups.md); kept here as the record.** Decision D1 of the v3 decision record: K-Means
needs the number of clusters set in advance and assumes convex, isotropic clusters (scikit-learn user guide, 2.3 Clustering),
and this model's k was a rule of thumb with no validation (see "Honest limits" below). Grant groups use a sentence-embedding
model built for clustering (all-MiniLM-L6-v2), an agglomerative cosine threshold set before looking, sensitivity at two other
thresholds, a grantor alias map and a hand check, and they answer the question the dashboard asks (the same purpose funded by
two agencies). The families table was never drawn on the dashboard. The code, checks, export and test were removed.


## What it does
Clusters every grant with a description in the State's grants and loans data (`core.fact_grant`, FY2009-present)
into program families, so grants that fund the same kind of program across agencies sit together (decision
register #33). Publishes `mart.grant_clusters` (one row per described grant: grant id -> family, with the family's
top terms) and `mart.grant_families` (one row per family: grants, grantees, dollars, year span).

## Method
- Grant id: a stable hash of the row as published (fiscal year, grantor, grantee, description, amount, ZIP), so a
  grant republished unchanged keeps its id across rebuilds. The portal lists a few exact duplicate rows; they are
  indistinguishable, so they share the hash plus a deterministic occurrence suffix.
- TF-IDF over the description (unigrams and bigrams, `min_df=3`, `max_df=0.6`, 2,000 features, sublinear term
  frequency). Stop words: the English list plus grant boilerplate ("grant", "program", "funding", "maryland", ...);
  without them the largest family is just "program / maryland".
- K-Means (scikit-learn, `n_init=10`, fixed seed 11). k follows a documented heuristic, sqrt(n/2) clamped to [5, 40]
  and capped at one family per five documents — recorded as `k_chosen` on every row.
- Each family is named by the two highest-weight terms of its centroid; the top five are published as `top_terms`
  so the label can be audited.

## Honest limits
- Descriptions are short and free-form; a family says "these descriptions read alike", not that the programs are run
  alike. Grantor wording habits can dominate topic.
- The k heuristic is a rule of thumb, not a validated optimum (unlike `agency_clusters`, no silhouette selection is
  run over a range — the corpus is large enough that the range scan costs minutes per build).
- Undescribed grants (a handful of rows) are not clustered.

## Build-time checks (`phase5_grant_clusters`)
Every described grant assigned exactly once; k inside the heuristic range; no unnamed families; the family summary
ties to the assignments to the grant.
