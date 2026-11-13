"""Grant-text clustering on constructed descriptions (no data/ needed)."""
import pandas as pd

from src.models import grant_clusters as GC


def _grants(n_per_topic=25):
    """Three clear topics: stormwater, arts councils, and school health."""
    topics = {
        "stormwater": ["Grant for stormwater management and stream restoration best practices",
                       "Nonpoint source pollution reduction including wetland creation and tree planting",
                       "Chesapeake Bay watershed restoration and stormwater retrofit project"],
        "arts": ["Grant funding for the support of the County Arts Councils",
                 "Arts council operating support grant for community arts programs",
                 "Folk arts and cultural heritage program grant"],
        "health": ["School-based health center nursing and mental health services grant",
                   "School health services program supporting nurses and health aides",
                   "Behavioral health services for students in public schools"],
    }
    rows = []
    for i in range(n_per_topic):
        for topic, texts in topics.items():
            rows.append({"fiscal_year": 2024, "grantor": f"Agency {topic}", "grantee": f"Grantee {topic} {i}",
                         "description": texts[i % 3], "category": "Grant", "nonprofit": "Y",
                         "zipcode": "21401", "amount": 10_000 + 100 * i})
    return pd.DataFrame(rows)


def test_topics_cluster_apart():
    g, fam = GC.build(_grants())
    purity = g.assign(topic=g.grantee.str[8:-2].str.strip()).groupby("cluster").topic.nunique()
    assert (purity == 1).all()  # no family mixes the constructed topics
    assert len(fam) == g.cluster.nunique()


def test_every_described_grant_assigned_once():
    grants = _grants()
    grants.loc[0, "description"] = None  # undescribed grants are not clustered
    g, fam = GC.build(grants)
    assert len(g) == grants.description.notna().sum() and g.grant_id.is_unique
    assert fam.grants.sum() == len(g)
    assert g.family.str.len().gt(0).all() and g.top_terms.str.contains(",").all()


def test_k_heuristic_bounds():
    assert GC.choose_k(20) == 4  # tiny input: one family per five documents caps sqrt(n/2)
    assert GC.K_MIN <= GC.choose_k(200) <= GC.K_MAX
    assert GC.choose_k(1_000_000) == GC.K_MAX


def test_deterministic_across_runs():
    grants = _grants()
    a, _ = GC.build(grants)
    b, _ = GC.build(grants)
    assert a[["grant_id", "cluster", "family"]].equals(b[["grant_id", "cluster", "family"]])


def test_grant_id_stable_and_sensitive():
    grants = _grants()
    a = GC.with_ids(grants).grant_id
    b = GC.with_ids(grants.copy()).grant_id
    assert a.equals(b)
    changed = grants.copy()
    changed.loc[0, "amount"] += 1
    assert GC.with_ids(changed).grant_id.iloc[0] != a.iloc[0]
    assert GC.with_ids(changed).grant_id.iloc[1] == a.iloc[1]


def test_exact_duplicate_rows_get_distinct_ids():
    grants = _grants()
    dup = pd.concat([grants, grants.iloc[[0]], grants.iloc[[0]]], ignore_index=True)  # the portal lists exact duplicate rows
    ids = GC.with_ids(dup).grant_id
    assert ids.is_unique and ids.iloc[0] == GC.with_ids(grants).grant_id.iloc[0]
    assert ids.iloc[-1].endswith("-2")
