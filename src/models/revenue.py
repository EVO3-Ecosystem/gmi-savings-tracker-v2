"""General Fund revenue history and forecast (review idea #27, reinstated by the project owner after the tracker
gained a sourced revenue history).

History lives in reference/gf_revenue_history.csv: total General Fund revenues (budgetary basis, $M), FY2017-FY2026,
each row carrying its source (Comptroller closeout reports, BRE board reports, DLS Spending Affordability reports).
Four candidate models, each compared with the naive baseline in a rolling-origin backtest scored with MASE whose
scale is recomputed from each origin's own training window (no future value enters it):
  * naive (last actual)
  * drift (last actual growing at the average yearly log rate)
  * log-linear trend (OLS on log revenue)
  * trend + CPI (log revenue on year and log CPI; the only macro regressor the pipeline already carries)
The kept model is the lowest mean MASE over the origins (a tie goes to the simpler model). The published FY2027
range comes from a seeded residual bootstrap and widens with the horizon. CPI beyond its last complete fiscal year
is extended at its trailing average growth and used only if the CPI model is the one kept.

Known one-time items stay in the series (FY2021 extraordinary FEMA/TEDCO receipts, the FY2023 $800M Blueprint
distribution, the FY2024 $150M LITRF transfer, FY2026 $405M extraordinary revenues): the model learns total GF
revenue as reported, and the model card says so. With ten annual points this is a disciplined baseline, not an
econometric forecast; BLS employment and BEA GDP regressors are noted as future work in the model card.

Assumptions (years, origins, seed) live in config/assumptions.yaml under `revenue`.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
TREND, NAIVE, DRIFT, TREND_CPI = "Log-linear trend", "Naive (last actual)", "Drift (average yearly growth)", "Trend + CPI"
METHODS = (NAIVE, TREND, DRIFT, TREND_CPI)  # tie-break order: simpler first


def assumptions():
    return yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())["revenue"]


def history(path=None):
    """The sourced revenue history, dollars (not $M), one row per fiscal year."""
    h = pd.read_csv(path or ROOT / "reference" / "gf_revenue_history.csv")
    h["value"] = h.gf_revenue_millions * 1e6
    return h[["fiscal_year", "gf_revenue_millions", "value", "basis", "source", "source_url", "note"]].sort_values("fiscal_year").reset_index(drop=True)


def _design(x, cpi, method):
    """Design matrix for the regression candidates: intercept, year, and log CPI when the method asks for it."""
    cols = [np.ones(len(x)), np.asarray(x, dtype=float)]
    if method == TREND_CPI:
        cols.append(np.log(np.asarray(cpi, dtype=float)))
    return np.column_stack(cols)


def predict(method, x_train, y_train, cpi_train, x_new, cpi_new):
    """Point forecast of revenue at the years x_new from a training window (log scale)."""
    x_new = np.asarray(x_new, dtype=float)
    if method == NAIVE:
        return np.full(len(x_new), float(y_train[-1]))
    if method == DRIFT:
        drift = np.diff(np.log(y_train)).mean()
        return y_train[-1] * np.exp(drift * (x_new - x_train[-1]))
    beta, *_ = np.linalg.lstsq(_design(x_train, cpi_train, method), np.log(y_train), rcond=None)
    return np.exp(_design(x_new, cpi_new, method) @ beta)


def _extend_cpi(cpi, years, cfg):
    """CPI for the forecast years: the last complete fiscal year's average grown at the trailing mean rate."""
    cpi = cpi.sort_values("fiscal_year")
    full = cpi[cpi.months >= 11]
    last_fy, last_avg = int(full.fiscal_year.iloc[-1]), float(full.cpi_avg.iloc[-1])
    tail = full.tail(cfg["cpi_extension_years"])
    rate = float((tail.cpi_avg.iloc[-1] / tail.cpi_avg.iloc[0]) ** (1 / (len(tail) - 1)) - 1) if len(tail) > 1 else 0.0
    ext = {fy: last_avg * (1 + rate) ** (fy - last_fy) for fy in years if fy > last_fy}
    known = dict(zip(cpi.fiscal_year, cpi.cpi_avg))
    return {fy: known.get(fy, ext.get(fy)) for fy in years}, rate


def simulate(method, x, y, cpi, fy, cpi_new, n_paths, rng):
    """Residual bootstrap paths (n_paths x len(fy)): refit on resampled residuals, then a random walk of resampled
    one-step log changes, so ranges widen with the horizon."""
    fy = np.asarray(fy)
    dl = np.diff(np.log(y))
    drift = dl.mean()
    shocks = dl - drift
    beta, *_ = np.linalg.lstsq(_design(x, cpi, method if method in (TREND, TREND_CPI) else TREND), np.log(y), rcond=None)
    res = np.log(y) - _design(x, cpi, method if method in (TREND, TREND_CPI) else TREND) @ beta
    sims = np.empty((n_paths, len(fy)))
    for i in range(n_paths):
        if method == NAIVE:
            level = np.log(y[-1]) + np.cumsum(rng.choice(shocks, len(fy)))
        elif method == DRIFT:
            level = np.log(y[-1]) + np.cumsum(drift + rng.choice(shocks, len(fy)))
        else:
            yb = np.log(y) + rng.choice(res, len(y))
            bb, *_ = np.linalg.lstsq(_design(x, cpi, method), yb, rcond=None)
            level = _design(fy, cpi_new, method) @ bb + rng.choice(res, len(fy)) * np.sqrt(np.arange(1, len(fy) + 1)) / np.sqrt(2)
        sims[i] = np.exp(level)
    return sims


def backtest(h, cpi_map, cfg):
    """Rolling-origin scoring: train through each origin year, predict the next. One row per method and origin with
    the outcome, absolute error, MASE (scale from that origin's own training window) and 80% band coverage."""
    rng = np.random.default_rng(cfg["seed"] + 2)  # separate stream from the published forecast
    x_all, y_all = h.fiscal_year.values.astype(float), h.value.values
    c_all = np.array([cpi_map[fy] for fy in h.fiscal_year])
    rows = []
    for origin in cfg["origins"]:
        tr = x_all <= origin
        x, y, c = x_all[tr], y_all[tr], c_all[tr]
        if len(y) < cfg["min_train_years"] or origin + 1 not in x_all:
            continue
        out = float(y_all[x_all == origin + 1][0])
        scale = float(np.mean(np.abs(np.diff(y))))
        c_new = np.array([cpi_map[origin + 1]])
        for m in METHODS:
            point = float(predict(m, x, y, c, [origin + 1], c_new)[0])
            sims = simulate(m, x, y, c, [origin + 1], c_new, cfg["backtest_bootstrap_paths"], rng)
            p10, p50, p90 = (float(v) for v in np.percentile(sims, [10, 50, 90], axis=0)[:, 0])
            rows.append({"origin_fy": int(origin), "method": m, "forecast_fy": int(origin + 1), "outcome": out,
                         "forecast": point, "abs_error": abs(point - out), "mase": abs(point - out) / scale if scale > 0 else None,
                         "p10": p10, "p50": p50, "p90": p90, "covered": bool(p10 <= out <= p90)})
    out = pd.DataFrame(rows)
    for c in ("outcome", "forecast", "abs_error", "p10", "p50", "p90"):
        out[c] = out[c].round(0)
    out["mase"] = pd.to_numeric(out.mase).round(4)
    return out


def build(hist, cpi, cfg=None):
    """The revenue tables: f_revenue (actuals plus the FY2027 forecast band), d_revenue_backtest, d_revenue_model."""
    cfg = cfg or assumptions()
    a0, a1, h1 = cfg["first_fy"], cfg["last_actual_fy"], cfg["horizon_fy"]
    h = hist[hist.fiscal_year.between(a0, a1)].reset_index(drop=True)
    fy = np.arange(a1 + 1, h1 + 1)
    cpi_map, cpi_rate = _extend_cpi(cpi, list(h.fiscal_year) + list(fy), cfg)
    bt = backtest(h, cpi_map, cfg)
    rolling = bt.groupby("method").mase.mean()
    method = min(METHODS, key=lambda m: (rolling[m], METHODS.index(m)))  # lowest mean MASE; ties go to the simpler model
    rng = np.random.default_rng(cfg["seed"])
    x, y = h.fiscal_year.values.astype(float), h.value.values
    c = np.array([cpi_map[v] for v in h.fiscal_year])
    c_new = np.array([cpi_map[v] for v in fy])
    p10, p50, p90 = np.percentile(simulate(method, x, y, c, fy, c_new, cfg["bootstrap_paths"], rng), [10, 50, 90], axis=0)
    rows = [{"fiscal_year": int(yr), "kind": "Actual", "value": v, "p10": None, "p50": None, "p90": None}
            for yr, v in zip(h.fiscal_year, h.value)]
    rows += [{"fiscal_year": int(yr), "kind": "Forecast", "value": None,
              "p10": float(p10[k]), "p50": float(p50[k]), "p90": float(p90[k])} for k, yr in enumerate(fy)]
    f = pd.DataFrame(rows)
    for col in ("value", "p10", "p50", "p90"):
        f[col] = pd.to_numeric(f[col]).round(0)
    b, a = np.polyfit(x, np.log(y), 1)
    meta = pd.DataFrame([{"method": method, "growth": float(np.exp(b) - 1), "n_actual": len(h),
                          "last_actual_fy": a1, "horizon_fy": h1, "cpi_extension_rate": cpi_rate,
                          "naive_mase": float(rolling[NAIVE]), "trend_mase": float(rolling[TREND]),
                          "drift_mase": float(rolling[DRIFT]), "trend_cpi_mase": float(rolling[TREND_CPI]),
                          "chosen_mase": float(rolling[method]), "coverage_80": float(bt[bt.method == method].covered.mean()),
                          "note": ("Total GF revenue as reported, one-time items included (FY2021 FEMA/TEDCO, FY2023 $800M "
                                   "Blueprint distribution, FY2024 $150M LITRF transfer, FY2026 $405M extraordinary).")}])
    for col in ("growth", "cpi_extension_rate", "naive_mase", "trend_mase", "drift_mase", "trend_cpi_mase", "chosen_mase", "coverage_80"):
        meta[col] = pd.to_numeric(meta[col]).round(4)
    return f, bt, meta


def write(con, cfg=None):
    """Read the reference history and core.cpi_fy, build the tables, store them in the mart schema."""
    cpi = con.execute("SELECT fiscal_year, cpi_avg, months FROM core.cpi_fy").df()
    f, bt, meta = build(history(), cpi, cfg)
    for name, df in (("f_revenue", f), ("d_revenue_backtest", bt), ("d_revenue_model", meta)):
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE mart.{name} AS SELECT * FROM _df")
        con.unregister("_df")
    return {"f_revenue": len(f), "d_revenue_backtest": len(bt), "d_revenue_model": len(meta)}
