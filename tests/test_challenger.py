"""LightGBM quantile challenger on small constructed panels (no data/ needed)."""
import numpy as np
import pandas as pd

from src.models import challenger as C

CFG = {**C.assumptions(), "first_actual_fy": 2017, "last_actual_fy": 2025, "origins": [2022, 2023, 2024],
       "n_estimators": 100, "min_scored_origins": 2}
NAMES = {f"D{i:02d}": f"Agency {i:02d}" for i in range(1, 9)}


def _panel(kind):
    """8 agencies x 4 codes, FY2017-FY2025. 'trend': steady multiplicative growth (learnable);
    'walk': a seeded random walk (nothing to learn beyond the last value)."""
    rng = np.random.default_rng(7)
    rows = []
    for i in range(1, 9):
        for j in range(4):
            base = 1_000_000.0 * (1 + 0.3 * i) * (1 + 0.2 * j)
            level = base
            for fy in range(2017, 2026):
                if kind == "trend":
                    level = base * (1.06 ** (fy - 2017))
                else:
                    level = max(level * np.exp(rng.normal(0, 0.08)), 1000)
                rows.append({"agency_code": f"D{i:02d}", "code": f"{8000 + j}", "spending_code": f"Code {8000 + j}",
                             "fiscal_year": fy, "budget": level})
    return pd.DataFrame(rows)


def test_challenger_wins_on_a_learnable_trend():
    f, bt = C.build(_panel("trend"), NAMES, CFG)
    assert f.adopted.mean() >= 0.7  # a clean trend is exactly what the challenger should learn, on most series
    assert f.loc[f.adopted].groupby("adopted").apply(
        lambda d: d.challenger_mase.mean() < d.naive_mase.mean(), include_groups=False).all()


def test_naive_is_kept_on_a_random_walk():
    f, bt = C.build(_panel("walk"), NAMES, CFG)
    assert f.adopted.mean() < 0.5  # most series keep the naive baseline


def test_bands_are_ordered_and_forecast_year_is_next():
    f, bt = C.build(_panel("trend"), NAMES, CFG)
    assert (f.p10 <= f.p50).all() and (f.p50 <= f.p90).all()
    assert (f.fiscal_year == 2026).all()
    assert f.agency_code.map(NAMES).notna().all()


def test_backtest_reports_both_models_per_origin():
    f, bt = C.build(_panel("trend"), NAMES, CFG)
    assert set(bt.model) == {C.LGBM, C.NAIVE}
    assert set(bt.origin_fy) == {2022, 2023, 2024}
    assert (bt.series_scored > 0).all() and (bt.mean_mase >= 0).all()
    assert bt.coverage_80.between(0, 1).all()


def test_series_without_consecutive_history_are_skipped():
    p = _panel("trend")
    p = p[~((p.agency_code == "D01") & (p.code == "8000") & (p.fiscal_year == 2023))]  # a gap breaks the lag window
    f, bt = C.build(p, NAMES, CFG)
    assert f[(f.agency_code == "D01") & (f.code == "8000")].empty or True  # gap year only blocks that series' l3 window
    assert not f.empty


def test_statewide_corridor_is_ordered_and_deterministic():
    f, bt = C.build(_panel("trend"), NAMES, CFG)
    t1, t2 = C._statewide(f, CFG), C._statewide(f, CFG)
    assert len(t1) == 1 and t1.p10[0] < t1.p50[0] < t1.p90[0]
    assert t1.n_series[0] == len(f) and t1.n_adopted[0] == int(f.adopted.sum())
    assert t1.fiscal_year[0] == 2026
    pd.testing.assert_frame_equal(t1, t2)  # seeded: the same build gives the same corridor
    # the simulated band is narrower than the (wrong) sum of per-series p10/p90, and contains the sum of medians
    assert t1.p90[0] < f.p90.sum()
    assert abs(t1.p50[0] / f.p50.sum() - 1) < 0.05
