"""K-Means clusters of agencies by their spending mix (review idea #32: peer groups for the treemap and, later,
peer-gap comparison).

Each agency's latest-actual-year controllable spending is split across the tracked focus areas plus an "other"
remainder, expressed as shares of the agency's controllable total (so big and small agencies compare by mix, not by
size). Shares are z-scored per area and clustered with K-Means; k is chosen from a configured range by silhouette
score (deterministic seed, n_init fixed), and the choice is recorded in the table. Clusters are named after their
two dominant areas by mean share.

Assumptions (k range, seed) live in config/assumptions.yaml under `clustering`.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
OTHER = "Other controllable purchases"


def assumptions():
    return yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())["clustering"]


def panel(area_year, rollup, fy):
    """One row per agency with controllable actual spending in fy: the share vector across areas plus 'other'."""
    a = area_year[(area_year.fiscal_year == fy) & (area_year.stage == "Actual")]
    wide = a.pivot_table(index=["agency_code", "agency"], columns="area", values="spend", aggfunc="sum").fillna(0)
    tot = rollup[(rollup.fiscal_year == fy)].set_index("agency_code").controllable
    wide["controllable"] = tot.reindex(wide.index.get_level_values("agency_code")).values
    wide = wide[wide.controllable > 0]
    wide[OTHER] = (wide.controllable - wide[[c for c in wide.columns if c != "controllable"]].sum(axis=1)).clip(lower=0)
    shares = wide[[c for c in wide.columns if c != "controllable"]].div(wide.controllable, axis=0)
    return shares.reset_index(), wide.reset_index()[["agency_code", "controllable"]]


def cluster(shares, cfg):
    """Fit K-Means for every k in the configured range; keep the k with the best silhouette, preferring k values
    whose smallest cluster holds at least two agencies (a singleton is an outlier, not a peer group). Returns the
    labels, the chosen k and every k's silhouette (for honesty about the choice)."""
    x = StandardScaler().fit_transform(shares.drop(columns=["agency_code", "agency"]))
    fits, scores = {}, {}
    for k in range(cfg["k_range"][0], cfg["k_range"][1] + 1):
        labels = KMeans(n_clusters=k, n_init=50, random_state=cfg["seed"]).fit_predict(x)
        fits[k] = labels
        scores[k] = float(silhouette_score(x, labels))
    valid = [k for k, lab in fits.items() if min(np.bincount(lab)) >= 2] or list(fits)
    best = max(valid, key=lambda k: scores[k])
    return fits[best], best, scores


def build(area_year, rollup, cfg=None):
    """mart.agency_clusters: one row per agency with its cluster, its controllable total, and the cluster's name."""
    cfg = cfg or assumptions()
    fy = cfg["fy"]
    shares, totals = panel(area_year, rollup, fy)
    labels, k, scores = cluster(shares, cfg)
    out = shares[["agency_code", "agency"]].copy()
    out["cluster"] = labels
    out = out.merge(totals, on="agency_code")
    feat = shares.drop(columns=["agency_code", "agency"])
    out["top_area"] = feat.idxmax(axis=1)
    # cluster names: the two dominant areas by mean share inside the cluster
    means = feat.groupby(labels).mean()
    names = {c: " / ".join(means.loc[c].sort_values(ascending=False).index[:2]) for c in means.index}
    out["cluster_name"] = out.cluster.map(names)
    out["fiscal_year"] = fy
    out["k_chosen"] = k
    out["silhouette"] = scores[k]
    out["controllable"] = pd.to_numeric(out.controllable).round(0)
    out["silhouette"] = pd.to_numeric(out.silhouette).round(4)
    return out.sort_values(["cluster", "controllable"], ascending=[True, False]).reset_index(drop=True), scores


def write(con, cfg=None):
    cfg = cfg or assumptions()
    area_year = con.execute("SELECT fiscal_year, stage, area, agency_code, agency, spend FROM mart.area_agency_year").df()
    rollup = con.execute("SELECT fiscal_year, agency_code, controllable FROM mart.agency_rollup").df()
    last_actual = con.execute("SELECT max(fiscal_year) FROM ref.dim_stage WHERE stage = 'Actual'").fetchone()[0]
    cfg = {**cfg, "fy": last_actual}
    out, scores = build(area_year, rollup, cfg)
    con.execute("SELECT 1").fetchall()  # complete pending fetchone() results before register() (duckdb result-in-use)
    con.register("_df", out)
    con.execute("CREATE OR REPLACE TABLE mart.agency_clusters AS SELECT * FROM _df")
    con.unregister("_df")
    return {"agency_clusters": len(out), "k": int(out.k_chosen.iloc[0])}
