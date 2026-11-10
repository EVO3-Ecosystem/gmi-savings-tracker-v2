# Model card — Agency spending-mix clusters (`src/models/clustering.py`)

## What it does
Groups agencies into peer clusters by the *mix* of their controllable spending in the latest actual year (FY2025):
each agency's spending across the tracked focus areas plus an "other controllable" remainder, as shares of the
agency's controllable total. Review idea #32 (K-Means peer groups; the treemap colors agencies by cluster, and the
clusters are the peer set for later peer-gap comparison).

## Method
- Shares, not dollars: big and small agencies compare by mix.
- Shares z-scored per area; K-Means (scikit-learn, `n_init=50`, fixed seed) fit for every k in the configured range
  (3-6); among the k values whose smallest cluster holds at least two agencies (a singleton is an outlier, not a
  peer group), the one with the best silhouette score is kept, and the score is published on every row so the choice
  is auditable.
- Clusters are named after their two dominant areas by mean share.

## Honest limits
- Mix only: a cluster says "these agencies buy similar things", not "these agencies are similar".
- Eight tracked areas plus a remainder is a coarse fingerprint; comptroller subobject detail is the planned upgrade.
- One year (the latest actual); mixes drift, so clusters are rebuilt every run.

## Build-time checks (`phase5_clustering`)
Every agency with controllable actual spending is assigned exactly once; k inside the configured range with a
positive silhouette; a warning when any cluster is a singleton or holds most agencies.
