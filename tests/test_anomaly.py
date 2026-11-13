"""Isolation-forest anomaly flags and the review queue on small constructed cases (no data/ needed)."""
import pandas as pd

from src.models import anomaly as A

CFG = {**A.assumptions(), "contamination": 0.08, "min_amount": 10_000, "min_history": 4, "n_estimators": 100}


def _vay(spike=True):
    """60 vendor-agency pairs, five years with slight deterministic jitter; one pair spikes 40x in the last year."""
    rows = []
    for i in range(60):
        for fy in range(2021, 2026):
            amt = 100_000.0 * (1 + (i % 5) * 0.03) * (1 + 0.01 * ((i * 7 + fy) % 5))
            rows.append({"vendor": f"V{i:02d}", "agency_code": f"D{(i % 6) + 1:02d}", "fiscal_year": fy, "paid": amt})
    if spike:
        rows.append({"vendor": "V00", "agency_code": "D01", "fiscal_year": 2026, "paid": 0})  # ignored: <= 0
        rows = [r for r in rows if not (r["vendor"] == "V00" and r["fiscal_year"] == 2025)]
        rows.append({"vendor": "V00", "agency_code": "D01", "fiscal_year": 2025, "paid": 4_000_000.0})
    return pd.DataFrame(rows)


def _scope(spike=True):
    """40 agency-code lines, six smooth years; one line jumps 30x in the last year."""
    rows = []
    for i in range(40):
        for fy in range(2020, 2026):
            amt = 200_000.0 * (1 + (i % 4) * 0.02)
            rows.append({"agency_code": f"D{(i % 5) + 1:02d}", "code": f"{8000 + i}", "spending_code": f"Code {8000 + i}",
                         "fiscal_year": fy, "budget": amt})
    if spike:
        rows = [r for r in rows if not (r["code"] == "8001" and r["fiscal_year"] == 2025)]
        rows.append({"agency_code": "D02", "code": "8001", "spending_code": "Code 8001", "fiscal_year": 2025, "budget": 6_000_000.0})
    return pd.DataFrame(rows)


def test_vendor_spike_is_flagged_with_reason_and_status_flows_to_queue():
    flagged, scored = A.vendor_agency_flags(_vay(), CFG)
    assert scored == 120
    hit = flagged[(flagged.vendor == "V00") & (flagged.fiscal_year == 2025)]
    assert len(hit) == 1 and hit.amount.iloc[0] == 4_000_000.0
    assert "prior year" in hit.why.iloc[0] or "unusually large" in hit.why.iloc[0]


def test_no_spike_means_only_background_share_flagged():
    flagged, _ = A.vendor_agency_flags(_vay(spike=False), CFG)
    assert len(flagged) <= 0.15 * 120  # around the 8% contamination, never a flood


def test_flags_are_deterministic_with_the_seed():
    a, _ = A.vendor_agency_flags(_vay(), CFG)
    b, _ = A.vendor_agency_flags(_vay(), CFG)
    pd.testing.assert_frame_equal(a, b)


def test_budget_line_spike_is_flagged():
    flagged, scored = A.agency_code_flags(_scope(), CFG)
    assert scored == 120  # 40 lines x years_seen 4-6
    hit = flagged[(flagged.code == "8001") & (flagged.fiscal_year == 2025)]
    assert len(hit) == 1


def test_review_queue_ids_overlap_and_defaults():
    vf, _ = A.vendor_agency_flags(_vay(), CFG)
    af, _ = A.agency_code_flags(_scope(), CFG)
    opp_keys = {("D02", "8001")}
    q = A.review_queue(vf, af, opp_keys, {"V00"}, {"D01": "Agency D01", "D02": "Agency D02"}, CFG)
    assert q.flag_id.is_unique and (q.status == "Under review").all()
    assert q.loc[q.code == "8001", "rule_detector_overlap"].iloc[0] == "Opportunity detector"
    assert q.loc[q.vendor == "V00", "rule_detector_overlap"].iloc[0] == "Bid list"
    assert set(q.rule_detector_overlap) <= {"Opportunity detector", "Bid list", "none"}


def test_empty_inputs_give_an_empty_queue():
    empty_v = pd.DataFrame(columns=["vendor", "agency_code", "fiscal_year", "paid"])
    empty_s = pd.DataFrame(columns=["agency_code", "code", "spending_code", "fiscal_year", "budget"])
    vf, _ = A.vendor_agency_flags(empty_v, CFG)
    af, _ = A.agency_code_flags(empty_s, CFG)
    assert A.review_queue(vf, af, set(), set(), {}, CFG).empty
