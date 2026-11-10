"""Grant-text clustering into program families (decision register #33).

Every grant with a description in core.fact_grant gets a stable id (a hash of the row as published) and is clustered
on the TF-IDF vector of its description with K-Means, so grants that fund the same kind of program across agencies
("nonpoint source pollution reduction", "arts council grants") sit in one family. k follows a simple heuristic,
sqrt(n/2) clamped to [K_MIN, K_MAX], fixed seed so a rebuild reproduces the same families; each family is named by the
highest-weight terms of its centroid, and those top terms are published on every row so the label is auditable.

Tables:
  mart.grant_clusters   one row per described grant: grant id -> family, with the family's top terms
  mart.grant_families   one row per family: size, dollars and year span (the summary the dashboard reads)

Constants are here, not in config/assumptions.yaml: this model has no tuned behaviour beyond the documented
heuristic, its seed, and the vectorizer's shape.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

K_MIN, K_MAX = 5, 40   # k heuristic: sqrt(n/2) clamped into this range
SEED = 11              # fixed so a rebuild reproduces the same families
MAX_FEATURES = 2000
TOP_TERMS = 5
# boilerplate words in nearly every grant description; without these the largest family is just "program / maryland"
STOP_EXTRA = ["grant", "grants", "program", "funding", "funds", "fund", "maryland", "state", "assistance",
              "services", "provide", "used", "support", "including"]

ID_COLS = ["fiscal_year", "grantor", "grantee", "description", "amount", "zipcode"]


def with_ids(grants):
    """grants: core.fact_grant rows. Adds grant_id, stable across rebuilds for a row that is republished unchanged.
    The portal lists a few exact duplicate rows; they are indistinguishable, so they share the hash and get a
    deterministic occurrence suffix (sorted by the key, then numbered from the second copy on)."""
    key = grants[ID_COLS].fillna("").astype(str).agg("|".join, axis=1)
    h = pd.util.hash_pandas_object(key, index=False).map(lambda v: f"g{v:016x}")
    order = key.sort_values(kind="stable").index
    occ = pd.Series(0, index=grants.index, dtype=int)
    occ.loc[order] = h.loc[order].groupby(h.loc[order]).cumcount().to_numpy()
    out = grants.copy()
    out["grant_id"] = h.where(occ == 0, h + "-" + occ.astype(str))
    return out


def choose_k(n):
    """k by heuristic: about sqrt(n/2) families, clamped to [K_MIN, K_MAX], and never more than one family per
    five documents (tiny inputs degenerate otherwise)."""
    return int(min(K_MAX, max(K_MIN, round(np.sqrt(n / 2))), max(2, n // 5)))


def build(grants, k=None):
    """(grant_clusters, grant_families) from described grants (fiscal_year, grantor, grantee, description, category,
    nonprofit, zipcode, amount). Deterministic for the same input."""
    g = with_ids(grants[grants.description.notna() & (grants.description.str.strip() != "")]).reset_index(drop=True)
    k = k or choose_k(len(g))
    vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=3, max_df=0.6,
                          max_features=MAX_FEATURES, stop_words=list(ENGLISH_STOP_WORDS) + STOP_EXTRA,
                          sublinear_tf=True)
    x = vec.fit_transform(g.description)
    g["cluster"] = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit_predict(x)
    g["k_chosen"] = k
    # family name: the centroid's highest-weight terms
    terms = np.array(vec.get_feature_names_out())
    cent = np.zeros((k, len(terms)))
    for c in range(k):
        cent[c] = np.asarray(x[g.cluster.to_numpy() == c].mean(axis=0)).ravel()
    top = {c: terms[np.argsort(cent[c])[::-1][:TOP_TERMS]] for c in range(k)}
    g["top_terms"] = g.cluster.map({c: ", ".join(t) for c, t in top.items()})
    g["family"] = g.cluster.map({c: " / ".join(t[:2]) for c, t in top.items()})
    fam = (g.groupby(["cluster", "family", "top_terms"], as_index=False)
           .agg(grants=("grant_id", "size"), grantees=("grantee", "nunique"), total_amount=("amount", "sum"),
                first_fy=("fiscal_year", "min"), last_fy=("fiscal_year", "max")))
    fam["total_amount"] = pd.to_numeric(fam.total_amount).round(0)
    cols = ["grant_id", "fiscal_year", "grantor", "grantee", "description", "category", "nonprofit", "zipcode",
            "amount", "cluster", "family", "top_terms", "k_chosen"]
    return (g[cols].sort_values(["cluster", "amount"], ascending=[True, False]).reset_index(drop=True),
            fam.sort_values("total_amount", ascending=False).reset_index(drop=True))


def write(con):
    grants = con.execute("SELECT fiscal_year, grantor, grantee, description, category, nonprofit, zipcode, amount FROM core.fact_grant").df()
    g, fam = build(grants)
    for name, df in (("grant_clusters", g), ("grant_families", fam)):
        con.execute("SELECT 1").fetchall()  # complete pending fetchone() results before register() (duckdb result-in-use)
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE mart.{name} AS SELECT * FROM _df")
        con.unregister("_df")
    return {"grant_clusters": len(g), "grant_families": len(fam), "k": int(g.k_chosen.iloc[0])}
