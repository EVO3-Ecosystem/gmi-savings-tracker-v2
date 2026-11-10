"""Agency clustering on a constructed spending-mix panel (no data/ needed)."""
import numpy as np
import pandas as pd

from src.models import clustering as CL

CFG = {"k_range": [2, 3], "seed": 11, "fy": 2025}


def _panel(n_per_group=8):
    """Two distinct mixes: 'IT-heavy' agencies and 'fleet-heavy' agencies."""
    rng = np.random.default_rng(9)
    rows = []
    for g, heavy in ((0, "IT hardware, software & services"), (1, "Vehicles & fleet")):
        for i in range(n_per_group):
            code = f"G{g}A{i:02d}"
            for area in ("IT hardware, software & services", "Vehicles & fleet", "Office supplies"):
                base = 8_000_000 if area == heavy else 500_000
                rows.append({"fiscal_year": 2025, "stage": "Actual", "area": area, "agency_code": code,
                             "agency": f"Agency {code}", "spend": base * (1 + rng.normal(0, 0.02))})
    ay = pd.DataFrame(rows)
    roll = ay.groupby(["fiscal_year", "agency_code"]).spend.sum().reset_index().rename(columns={"spend": "controllable"})
    return ay, roll


def test_distinct_mixes_cluster_apart():
    ay, roll = _panel()
    out, scores = CL.build(ay, roll, CFG)
    purity = out.assign(group=out.agency_code.str[:2]).groupby("cluster").group.nunique()
    assert (purity == 1).all()  # no cluster mixes the two constructed spending mixes
    assert CFG["k_range"][0] <= out.k_chosen.iloc[0] <= CFG["k_range"][1]


def test_every_agency_assigned_once_and_named():
    ay, roll = _panel()
    out, scores = CL.build(ay, roll, CFG)
    assert len(out) == 16 and out.agency_code.is_unique
    assert out.cluster_name.str.len().gt(0).all() and out.top_area.notna().all()
    assert (out.fiscal_year == 2025).all()


def test_deterministic_across_runs():
    ay, roll = _panel()
    a, _ = CL.build(ay, roll, CFG)
    b, _ = CL.build(ay, roll, CFG)
    assert a[["agency_code", "cluster"]].equals(b[["agency_code", "cluster"]])
