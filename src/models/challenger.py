"""LightGBM quantile challenger for agency x spending-code spending (review idea #26; #27 declined revenue forecasting
because the tracker holds no revenue data — the same model is applied to spending instead; #25's P10-P90 corridors).

A global gradient-boosted quantile model over every agency x spending-code yearly series (controllable purchases,
actual years), trained with lagged features only, so no future value enters a prediction. Rolling-origin validation:
train through each origin year, predict the next, and score against the naive last-value forecast with MASE whose
scale comes from each origin's own training window. The challenger is kept only for the series where it beats the
naive baseline; the rest stay naive. Published rows forecast the year after the last actual with a p10-p50-p90 band
(fiscal risk corridors): quantile objectives for the challenger, the series' own historical one-step log-change
quantiles for the naive rows.

Assumptions (origins, lags, hyperparameters, seed) live in config/assumptions.yaml under `challenger`.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[2]
LGBM = "LightGBM quantile (global)"
NAIVE = "Naive (last actual)"
FEATURES = ["l1", "l2", "l3", "g1", "m3", "agency_log", "code_log", "t"]


def assumptions():
    return yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())["challenger"]


def panel(scope):
    """scope: one row per agency x code x year of controllable actual spending (fiscal_year, agency_code, code,
    spending_code, budget). Returns the modelling panel: positive years only, one row per series and year."""
    p = scope[scope.budget > 0].copy()
    p = p.groupby(["agency_code", "code", "spending_code", "fiscal_year"], as_index=False).budget.sum()
    return p.sort_values(["agency_code", "code", "fiscal_year"]).reset_index(drop=True)


def features(p, cfg):
    """Lagged features; a row exists only when the series has `lags` prior positive years. No current-year value is
    used as an input, so a forecast never sees its own target or any later year."""
    k = cfg["lags"]
    p = p.copy()
    p["log"] = np.log1p(p.budget)
    g = p.groupby(["agency_code", "code"], sort=False)
    for i in range(1, k + 1):
        p[f"l{i}"] = g["log"].shift(i)
        p[f"y{i}"] = g.fiscal_year.shift(i)
    p["g1"] = p.l1 - p.l2
    p["m3"] = (p.l1 + p.l2 + p.l3) / 3
    ok = (p.fiscal_year - p[f"y{k}"] == k)  # exactly k consecutive prior years
    for keys, col in ((["agency_code"], "agency_log"), (["code"], "code_log")):
        tot = p.groupby(keys + ["fiscal_year"]).budget.sum().rename("total").reset_index()
        tot[col] = np.log1p(tot.total)
        tot["fiscal_year"] += 1  # the prior year's total, so the current year never leaks in
        p = p.merge(tot[keys + ["fiscal_year", col]], on=keys + ["fiscal_year"], how="left")
    p["t"] = p.fiscal_year - cfg["first_actual_fy"]
    return p[ok].dropna(subset=FEATURES + ["log"]).reset_index(drop=True)


def _fit_quantile(train, alpha, cfg):
    m = LGBMRegressor(objective="quantile", alpha=alpha, n_estimators=cfg["n_estimators"],
                      learning_rate=cfg["learning_rate"], num_leaves=cfg["num_leaves"],
                      min_child_samples=cfg["min_child_samples"], random_state=cfg["seed"], deterministic=True, verbose=-1)
    return m.fit(train[FEATURES], train["log"])


def _naive_band(train_series, years):
    """The naive forecast's band for a single series: last value, widened by the series' own one-step log changes."""
    last = float(train_series.budget.iloc[-1])
    d = np.diff(np.log(train_series.budget.values))
    if len(d) < 2:
        return {y: (last, last, last) for y in years}
    q10, q50, q90 = np.percentile(d, [10, 50, 90])
    return {y: (last * np.exp(q10), last * np.exp(q50), last * np.exp(q90)) for y in years}


def backtest(f, cfg):
    """Rolling-origin scoring: per origin, train through the origin and predict the next year; per series, mean MASE
    for the challenger and the naive baseline, and each model's 80% band coverage. One row per origin and model."""
    rows, per_series = [], {}
    for origin in cfg["origins"]:
        train, test = f[f.fiscal_year <= origin], f[f.fiscal_year == origin + 1]
        if test.empty:
            continue
        test_idx = test.set_index(["agency_code", "code"])
        models = {a: _fit_quantile(train, a, cfg) for a in (0.1, 0.5, 0.9)}
        for (a, c), ts in f[f.fiscal_year <= origin].groupby(["agency_code", "code"]):
            hist = ts[ts.fiscal_year <= origin].budget.values
            scale = np.mean(np.abs(np.diff(hist))) if len(hist) > 1 else 0
            if not scale or (a, c) not in test_idx.index:
                continue
            row = test_idx.loc[[(a, c)]]
            out = float(np.expm1(row["log"].iloc[0]))
            last = float(ts[ts.fiscal_year == origin].budget.iloc[0])
            band = _naive_band(ts[ts.fiscal_year <= origin], [origin + 1])[origin + 1]
            pred = {q: float(np.expm1(models[q].predict(row[FEATURES])[0])) for q in (0.1, 0.5, 0.9)}
            s = per_series.setdefault((a, c), {NAIVE: [], LGBM: []})
            s[NAIVE].append(abs(last - out) / scale)
            s[LGBM].append(abs(pred[0.5] - out) / scale)
            for model, mid, lo, hi in ((NAIVE, band[1], band[0], band[2]), (LGBM, pred[0.5], pred[0.1], pred[0.9])):
                rows.append({"origin_fy": origin, "model": model, "abs_error": abs(mid - out), "scale": scale,
                             "covered": bool(lo <= out <= hi), "width_log": abs(np.log1p(hi) - np.log1p(lo))})
    bt = pd.DataFrame(rows)
    bt["mase"] = bt.abs_error / bt.scale
    agg = (bt.groupby(["origin_fy", "model"])
           .agg(series_scored=("mase", "size"), mean_mase=("mase", "mean"), coverage_80=("covered", "mean"),
                mean_width_log=("width_log", "mean")).reset_index())
    for c in ("mean_mase", "coverage_80", "mean_width_log"):
        agg[c] = pd.to_numeric(agg[c]).round(4)
    scores = pd.DataFrame([{"agency_code": a, "code": c, "scored_origins": len(v[NAIVE]),
                            "naive_mase": float(np.mean(v[NAIVE])), "challenger_mase": float(np.mean(v[LGBM]))}
                           for (a, c), v in per_series.items()])
    return agg, scores


def build(scope, agency_names, cfg=None):
    """The challenger tables from the spending panel. agency_names: agency_code -> latest name. Returns
    (f_challenger, d_challenger_backtest): per-series forecasts for the year after the last actual, and the
    rolling-origin validation that justifies each series' model."""
    cfg = cfg or assumptions()
    p = panel(scope)
    f = features(p, cfg)
    agg, scores = backtest(f, cfg)
    keep = scores[(scores.scored_origins >= cfg["min_scored_origins"]) & (scores.challenger_mase < scores.naive_mase - 1e-9)]
    adopted = set(zip(keep.agency_code, keep.code))
    fy = cfg["last_actual_fy"] + 1
    train = f[f.fiscal_year <= cfg["last_actual_fy"]]
    models = {a: _fit_quantile(train, a, cfg) for a in (0.1, 0.5, 0.9)}
    agency_tot = p[p.fiscal_year == cfg["last_actual_fy"]].groupby("agency_code").budget.sum()
    code_tot = p[p.fiscal_year == cfg["last_actual_fy"]].groupby("code").budget.sum()
    lags_needed = [fy - i for i in range(1, cfg["lags"] + 1)]
    sc = scores.set_index(["agency_code", "code"])
    rows = []
    for (a, c, name), ts in p.groupby(["agency_code", "code", "spending_code"]):
        hist = ts[ts.fiscal_year <= cfg["last_actual_fy"]]
        vals = hist.set_index("fiscal_year").budget
        if any(y not in vals.index for y in lags_needed):
            continue  # not enough consecutive history to feature a one-year-ahead forecast
        lg = np.log1p(vals.loc[lags_needed].values)  # l1 = last actual, l2, l3
        x = pd.DataFrame([{"l1": lg[0], "l2": lg[1], "l3": lg[2], "g1": lg[0] - lg[1], "m3": lg.mean(),
                           "agency_log": np.log1p(agency_tot.get(a)), "code_log": np.log1p(code_tot.get(c)),
                           "t": fy - cfg["first_actual_fy"]}])
        key = (a, c)
        use_lgbm = key in adopted
        if use_lgbm:
            p10, p50, p90 = (float(np.expm1(models[q].predict(x)[0])) for q in (0.1, 0.5, 0.9))
        else:
            p10, p50, p90 = _naive_band(hist, [fy])[fy]
        lo, mid, hi = min(p10, p50, p90), np.median([p10, p50, p90]), max(p10, p50, p90)
        nm, cm = (float(sc.loc[key, col]) if key in sc.index else None for col in ("naive_mase", "challenger_mase"))
        rows.append({"agency_code": a, "agency": agency_names.get(a, a), "code": c, "spending_code": name,
                     "fiscal_year": fy, "p10": lo, "p50": mid, "p90": hi,
                     "model": LGBM if use_lgbm else NAIVE, "adopted": use_lgbm, "naive_mase": nm, "challenger_mase": cm})
    out = pd.DataFrame(rows)
    for c in ("p10", "p50", "p90"):
        out[c] = pd.to_numeric(out[c]).round(0)
    for c in ("naive_mase", "challenger_mase"):
        out[c] = pd.to_numeric(out[c]).round(4)
    return out.sort_values("p50", ascending=False).reset_index(drop=True), agg


def _statewide(out, cfg):
    """A band for the statewide FY-after-last-actual total. Per-series p10/p90 are not additive (every series does
    not hit its own tail in the same year), so the total is simulated: each series is drawn log-normally within its
    kept band — median p50, log sigma from its band width, draws clamped to the band edges, the same uncertainty
    convention as the savings calculator — and the draws are summed path by path."""
    paths = int(cfg.get("bootstrap_paths", 4000))
    rng = np.random.default_rng(cfg["seed"])
    p10, p50, p90 = (out[c].to_numpy(dtype=float) for c in ("p10", "p50", "p90"))
    sg = np.log((p90 + 1.0) / (p10 + 1.0)) / (2 * 1.2816)
    draws = p50[:, None] * np.exp(rng.standard_normal((len(out), paths)) * sg[:, None])
    draws = np.minimum(np.maximum(draws, p10[:, None]), p90[:, None])  # the published band is each series' own bounds
    q10, q50, q90 = np.quantile(draws.sum(axis=0), [0.1, 0.5, 0.9])
    return pd.DataFrame([{"fiscal_year": int(out.fiscal_year.iloc[0]), "p10": round(float(q10)), "p50": round(float(q50)),
                          "p90": round(float(q90)), "n_series": len(out), "n_adopted": int(out.adopted.sum()),
                          "bootstrap_paths": paths,
                          "note": "Statewide corridor simulated path by path: each series drawn log-normally within "
                                  "its kept band (median p50, sigma from the band width, draws clamped to the band "
                                  "edges); summing the per-series p10/p90 directly would overstate the band, because "
                                  "series do not all hit their tails together."}])


SCOPE_SQL = """SELECT b.fiscal_year, b.agency_code, b.subobject_code AS code, b.subobject_name AS spending_code,
      sum(b.budget) AS budget
FROM core.fact_budget_scope b JOIN ref.dim_stage s USING (fiscal_year)
WHERE b.controllable AND s.stage = 'Actual'
GROUP BY ALL"""


def write(con, cfg=None):
    cfg = cfg or assumptions()
    scope = con.execute(SCOPE_SQL).df()
    names = con.execute("SELECT agency_code, agency, fiscal_year FROM mart.agency_year").df()
    names = names.sort_values("fiscal_year", ascending=False).drop_duplicates("agency_code").set_index("agency_code").agency.to_dict()
    f, bt = build(scope, names, cfg)
    tot = _statewide(f, cfg)
    for name, df in (("f_challenger", f), ("d_challenger_backtest", bt), ("d_challenger_total", tot)):
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE mart.{name} AS SELECT * FROM _df")
        con.unregister("_df")
    return {"f_challenger": len(f), "d_challenger_backtest": len(bt), "d_challenger_total": len(tot)}
