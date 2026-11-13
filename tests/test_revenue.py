"""Revenue forecast on small constructed histories (no data/ needed)."""
import numpy as np
import pandas as pd

from src.models import revenue as R

CFG = {**R.assumptions(), "first_fy": 2017, "last_actual_fy": 2026, "horizon_fy": 2027,
       "origins": [2022, 2023, 2024, 2025], "min_train_years": 5, "bootstrap_paths": 400, "backtest_bootstrap_paths": 200}


def _hist(kind):
    """FY2017-FY2026 history in $M. 'trend': steady ~4% growth (learnable); 'walk': a seeded random walk."""
    rng = np.random.default_rng(5)
    vals, level = [], 17_000.0
    for fy in range(2017, 2027):
        if kind == "trend":
            level = 17_000.0 * (1.04 ** (fy - 2017))
        else:
            level = max(level * np.exp(rng.normal(0, 0.05)), 1000)
        vals.append(level)
    return pd.DataFrame({"fiscal_year": list(range(2017, 2027)), "gf_revenue_millions": vals,
                         "value": [v * 1e6 for v in vals], "basis": "actual", "source": "test", "source_url": "", "note": ""})


def _cpi():
    rng = np.random.default_rng(3)
    return pd.DataFrame({"fiscal_year": list(range(2017, 2027)),
                         "cpi_avg": [260 * (1.025 ** (fy - 2017)) + rng.normal(0, 0.5) for fy in range(2017, 2027)],
                         "months": [12] * 10})


def test_real_history_loads_with_sources():
    h = R.history()
    assert len(h) == 10 and (h.fiscal_year.values == np.arange(2017, 2027)).all()
    assert h.value.gt(0).all() and h.source.str.len().gt(20).all() and h.source_url.str.startswith("http").all()


def test_trend_is_kept_on_a_learnable_history():
    f, bt, meta = R.build(_hist("trend"), _cpi(), CFG)
    assert meta.method.iloc[0] in ("Log-linear trend", "Trend + CPI")  # a clean 4% trend is learnable
    assert meta.chosen_mase.iloc[0] <= meta.naive_mase.iloc[0] + 1e-9


def test_bands_are_ordered_and_forecast_year_is_next():
    f, bt, meta = R.build(_hist("walk"), _cpi(), CFG)
    fc = f[f.kind == "Forecast"]
    assert (fc.fiscal_year == [2027]).all()
    assert (fc.p10 <= fc.p50).all() and (fc.p50 <= fc.p90).all() and (fc.p10 > 0).all()
    assert len(f[f.kind == "Actual"]) == 10


def test_backtest_scores_every_method_per_origin():
    f, bt, meta = R.build(_hist("trend"), _cpi(), CFG)
    per = bt.groupby("origin_fy").method.nunique()
    assert (per == len(R.METHODS)).all() and set(bt.origin_fy) == set(CFG["origins"])
    assert (bt.abs_error >= 0).all() and bt.mase.notna().all()


def test_cpi_extension_covers_the_forecast_year():
    cpi_map, rate = R._extend_cpi(_cpi(), [2026, 2027, 2028], CFG)
    assert all(cpi_map[fy] and cpi_map[fy] > 0 for fy in (2026, 2027, 2028))
    assert 0 < rate < 0.2
