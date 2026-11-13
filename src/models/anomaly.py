"""Isolation-forest anomaly flags and the review queue (review idea #31, adapted; #30's robust scaling; #39's queue).

Payments are yearly totals per vendor and agency, not invoices, so duplicate invoices and off-cycle payments cannot
exist in this data. Instead the forest runs on the two grains the pipeline actually has:

  * vendor x agency x year payments (mart.vendor_agency_year): one vendor paid much more than its own history, or
    suddenly taking most of an agency's payments, or concentrating a vendor's statewide business
  * agency x spending code x year budgets (controllable actuals): a line that jumps against its own history, its
    agency's mix, or the code's statewide mix

Features are robustly scaled (median and interquartile range) so skewed spending does not dominate. Each flag carries
a plain-language `why` (its two most extreme features), and `rule_detector_overlap` says whether a rule detector
already covers it (the opportunity detectors or the bid list), so the queue adds review value instead of repeating
them. Flags land in mart.review_queue with status 'Under review' ('Approved variance' and 'Refer to OLA' are the
dashboard's workflow states) and are exported as review_queue.csv; a per-run count history is kept for passing builds.

The isolation forest is a screening tool: a flag means "worth a look", never "wrong". Assumptions (contamination,
thresholds, seed) live in config/assumptions.yaml under `anomaly`.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[2]
STATUSES = ("Under review", "Approved variance", "Refer to OLA")
WHY = {
    "log_value": "unusually large for its own history",
    "yoy": "a jump of {yoy:+.0%} on the prior year",
    "share_group": "{share:.0%} of the {group}'s total that year",
    "share_whole": "{share:.0%} of the {whole} statewide that year",
    "vendor_agencies": "paid by {n:.0f} agencies that year",
}


def assumptions():
    return yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text())["anomaly"]


def _robust(df, cols):
    """Median/IQR scaling per feature (IQR of 0 falls back to the standard deviation, then to 1)."""
    x = df[cols].astype(float).copy()
    for c in cols:
        med = x[c].median()
        iqr = x[c].quantile(0.75) - x[c].quantile(0.25)
        scale = iqr if iqr > 0 else (x[c].std() or 1.0)
        x[c] = (x[c] - med) / scale
    return x.fillna(0.0)


def _flag(df, cols, cfg):
    """Run the forest; return the flagged rows with score and the scaled features (for the 'why')."""
    x = _robust(df, cols)
    forest = IsolationForest(n_estimators=cfg["n_estimators"], contamination=cfg["contamination"],
                             random_state=cfg["seed"])
    flag = forest.fit_predict(x) == -1
    if not flag.any():  # near-identical rows tie at the threshold; an empty flag set is a valid result
        return df.iloc[0:0].assign(score=[], why=[]), x.iloc[0:0]
    out = df[flag].copy()
    out["score"] = -forest.score_samples(x[flag])
    return out, x[flag]


def _why(row_scaled, row_raw, group, whole):
    """The two most extreme features, phrased."""
    order = row_scaled.abs().sort_values(ascending=False).index[:2]
    parts = []
    for f in order:
        if f == "yoy" and pd.notna(row_raw.get("yoy")):
            parts.append(WHY["yoy"].format(yoy=row_raw["yoy"]))
        elif f == "share_group":
            parts.append(WHY["share_group"].format(share=row_raw["share_group"], group=group))
        elif f == "share_whole":
            parts.append(WHY["share_whole"].format(share=row_raw["share_whole"], whole=whole))
        elif f == "vendor_agencies":
            parts.append(WHY["vendor_agencies"].format(n=row_raw["vendor_agencies"]))
        else:
            parts.append(WHY["log_value"])
    return "; ".join(parts[:2])


def vendor_agency_flags(vay, cfg):
    """Flags on vendor x agency x year payments. vay: vendor, agency_code, fiscal_year, paid (full years only)."""
    p = vay[vay.agency_code.notna() & (vay.paid > 0)].copy()
    p = p.sort_values(["vendor", "agency_code", "fiscal_year"])
    g = p.groupby(["vendor", "agency_code"], sort=False)
    p["log_value"] = np.log1p(p.paid)
    p["yoy"] = g.paid.pct_change().where(g.fiscal_year.diff() == 1)
    p["years_seen"] = g.cumcount() + 1
    p["share_group"] = p.paid / p.groupby(["agency_code", "fiscal_year"]).paid.transform("sum")
    p["share_whole"] = p.paid / p.groupby(["vendor", "fiscal_year"]).paid.transform("sum")
    p["vendor_agencies"] = p.groupby(["vendor", "fiscal_year"]).agency_code.transform("nunique").astype(float)
    cols = ["log_value", "yoy", "share_group", "share_whole", "vendor_agencies"]
    scored = p[(p.years_seen >= cfg["min_history"]) & (p.paid >= cfg["min_amount"])].copy()
    if scored.empty:
        return scored.assign(score=[], why=[]), 0
    flagged, scaled = _flag(scored, cols, cfg)
    flagged["why"] = [_why(scaled.loc[i], flagged.loc[i], "agency", "vendor's statewide payments") for i in flagged.index]
    out = flagged.rename(columns={"paid": "amount"})
    out["source"] = "Vendor-agency payments"
    out["spending_code"] = None
    out["code"] = None
    return out[["source", "fiscal_year", "agency_code", "vendor", "spending_code", "code", "amount", "score", "why"]], len(scored)


def agency_code_flags(scope, cfg):
    """Flags on agency x spending code x year budgets. scope: fiscal_year, agency_code, code, spending_code, budget
    (controllable actuals)."""
    p = scope[scope.budget > 0].copy()
    p = p.sort_values(["agency_code", "code", "fiscal_year"])
    g = p.groupby(["agency_code", "code"], sort=False)
    p["log_value"] = np.log1p(p.budget)
    p["yoy"] = g.budget.pct_change().where(g.fiscal_year.diff() == 1)
    p["years_seen"] = g.cumcount() + 1
    p["share_group"] = p.budget / p.groupby(["agency_code", "fiscal_year"]).budget.transform("sum")
    p["share_whole"] = p.budget / p.groupby(["code", "fiscal_year"]).budget.transform("sum")
    cols = ["log_value", "yoy", "share_group", "share_whole"]
    scored = p[(p.years_seen >= cfg["min_history"]) & (p.budget >= cfg["min_amount"])].copy()
    if scored.empty:
        return scored.assign(score=[], why=[]), 0
    flagged, scaled = _flag(scored, cols, cfg)
    flagged["why"] = [_why(scaled.loc[i], flagged.loc[i], "agency's controllable budget", "spending code") for i in flagged.index]
    out = flagged.rename(columns={"budget": "amount"})
    out["source"] = "Agency spending code"
    out["vendor"] = None
    return out[["source", "fiscal_year", "agency_code", "vendor", "spending_code", "code", "amount", "score", "why"]], len(scored)


def review_queue(vf, af, opp_keys, bid_vendors, agency_names, cfg=None):
    """One queue: both grains, overlap with the rule detectors, largest score first, flag ids A001, A002, ...

    opp_keys: set of (agency_code, code) pairs the opportunity detectors already flag. bid_vendors: set of vendors
    (any case) on the bid list. agency_names: agency_code -> latest name."""
    d = pd.concat([vf, af], ignore_index=True)
    if d.empty:
        return d.assign(agency=[], rule_detector_overlap=[], status=[], flag_id=[])
    keys = list(zip(d.agency_code, d.code))
    d["rule_detector_overlap"] = [
        "Opportunity detector" if k in opp_keys else ("Bid list" if isinstance(v, str) and v.upper() in bid_vendors else "none")
        for k, v in zip(keys, d.vendor)]
    d["agency"] = d.agency_code.map(agency_names).fillna(d.agency_code)
    d["status"] = "Under review"
    d = d.sort_values("score", ascending=False).reset_index(drop=True)
    d.insert(0, "flag_id", [f"A{i:03d}" for i in range(1, len(d) + 1)])
    d["amount"] = d.amount.round(0)
    d["score"] = d.score.round(4)
    cols = ["flag_id", "source", "fiscal_year", "agency_code", "agency", "vendor", "spending_code", "code",
            "amount", "score", "why", "rule_detector_overlap", "status"]
    return d[cols]


def write(con, cfg=None):
    """Build mart.review_queue from the marts."""
    cfg = cfg or assumptions()
    vay = con.execute("SELECT vendor, agency_code, fiscal_year, paid FROM mart.vendor_agency_year "
                      "WHERE NOT partial_year").df()
    from . import challenger  # the agency x code panel query is shared with the challenger
    scope = con.execute(challenger.SCOPE_SQL).df()
    vf, n_v = vendor_agency_flags(vay, cfg)
    af, n_a = agency_code_flags(scope, cfg)
    opps = con.execute("SELECT agency_code, spending_code FROM mart.d_opps WHERE agency_code IS NOT NULL").df()
    opp_keys = {(r.agency_code, m.group(1)) for r in opps.itertuples()
                if (m := __import__("re").search(r"\(([^()]*)\)$", r.spending_code or ""))}
    bids = {v.upper() for v in con.execute("SELECT vendor FROM mart.d_bid_list").df().vendor}
    names = con.execute("SELECT agency_code, agency, fiscal_year FROM mart.agency_year").df()
    names = names.sort_values("fiscal_year", ascending=False).drop_duplicates("agency_code").set_index("agency_code").agency.to_dict()
    q = review_queue(vf, af, opp_keys, bids, names, cfg)
    con.register("_df", q)
    con.execute("CREATE OR REPLACE TABLE mart.review_queue AS SELECT * FROM _df")
    con.unregister("_df")
    con.execute("CREATE OR REPLACE TABLE mart.review_queue_scored (source TEXT, scored BIGINT)")
    con.execute("INSERT INTO mart.review_queue_scored VALUES ('Vendor-agency payments', ?), ('Agency spending code', ?)", [n_v, n_a])
    return {"review_queue": len(q)}


def record(con, run_id, data):
    """Per-run flag counts, appended only for a build that passed its checks (the feedback loop for triage)."""
    hist = Path(data) / "review_queue_history.csv"
    rows = con.execute("SELECT source, count(*) AS flags, sum(amount) AS dollars FROM mart.review_queue GROUP BY 1").fetchall()
    new = pd.DataFrame([{"run_id": run_id, "source": s, "flags": f, "dollars": round(d or 0, 0)} for s, f, d in rows])
    old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
    pd.concat([old[old.get("run_id", pd.Series(dtype=str)) != run_id] if len(old) else old, new], ignore_index=True).to_csv(hist, index=False)
