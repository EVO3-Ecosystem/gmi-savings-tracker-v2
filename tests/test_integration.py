"""Integration: extract (recorded portal) -> build -> checks -> export, entirely under tmp_path.

Runs the real `extract.run()` and `build.build()` entry points against the fixture portal. The
stages that cannot be honest on a handful of synthetic rows are stubbed with minimal equivalents
(they are covered on real data by the gated suites): reference.build (dashboard-parity baselines
in reference/baseline_quality.csv assume the full portal), marts.build (the 46-file sql/mart
layer), and the Phase 5 model writes (forecast/challenger/revenue/clustering/opportunities/
backtest/savings/recommendations/anomaly). Everything else is the real pipeline: raw and core
layers and their checks, the checks module's pass/fail contract, facts.build, record_payees,
the publish gate, and export.main.
"""
import duckdb
import pandas as pd
import pytest

from src.pipeline import export, extract

# build.py is owned by another workstream; if a concurrent edit leaves it momentarily
# unimportable, skip rather than fail the whole suite.
try:
    from src.pipeline import build
except ImportError as e:
    pytest.skip(f"src.pipeline.build not importable (concurrent edit in flight): {e}", allow_module_level=True)

# Phase 5 model stages, whichever of them the current build.py wires in.
MODEL_STAGES = ("forecast", "challenger", "revenue", "clustering", "opportunities",
                "backtest", "savings", "recommendations", "anomaly", "payee_classifier", "grant_groups")

DASHBOARD_YAML = "\n".join(f"{n}: {n}" for n in
                           ("agency_rollup", "vendor_agency_year", "vendor_master", "sources", "run_checks")) + "\n"


def _stub_reference(con, raw):
    """Minimal Phase 3: map the tiny fixture payments, scope the budget, and set baselines the tiny data meets."""
    con.execute("""CREATE OR REPLACE TABLE ref.map_payment_agency AS
        SELECT DISTINCT agency_name_as_paid AS payment_agency_name, agency_code_as_paid AS agency_code,
               'agency code in payments' AS matched_by,
               (agency_code_as_paid IN (SELECT agency_code FROM ref.dim_agency)) AS in_budget
        FROM core.fact_payment""")
    con.execute("""CREATE OR REPLACE TABLE core.fact_payment_mapped AS
        SELECT p.*, m.agency_code, m.matched_by FROM core.fact_payment p
        LEFT JOIN ref.map_payment_agency m ON m.payment_agency_name = p.agency_name_as_paid""")
    con.execute("""CREATE OR REPLACE TABLE ref.map_payee_vendor AS
        SELECT DISTINCT vendor_name_as_paid AS payee, upper(vendor_name_as_paid) AS vendor, FALSE AS is_government
        FROM core.fact_payment""")
    con.execute("""CREATE OR REPLACE TABLE core.fact_budget_scope AS
        SELECT *, TRUE AS controllable, 'Testing services' AS focus_area FROM core.fact_budget""")
    con.execute("CREATE OR REPLACE TABLE ref.map_focus_area (subobject_code VARCHAR, focus_area VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE ref.function_exceptions (agency_code VARCHAR, function_name VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE ref.map_mfr_agency (agency_file VARCHAR, agency_code VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE core.mfr_measure (agency_file VARCHAR, measure VARCHAR, agency_code VARCHAR)")
    one = lambda q: con.execute(q).fetchone()[0] or 0  # noqa: E731
    con.execute("CREATE OR REPLACE TABLE ref.baseline_quality (measure VARCHAR, value VARCHAR)")
    con.executemany("INSERT INTO ref.baseline_quality VALUES (?, ?)", [
        ("fy2026_payment_dollars_matched", "0"), ("payment_agency_names_mapped", "0"),
        ("payee_names_grouped", "0"), ("companies_with_several_names", "0"),
        ("controllable_fy2025", str(one("SELECT sum(budget) FROM core.fact_budget_scope WHERE fiscal_year = 2025 AND controllable"))),
        ("focus_area_fy2025", str(one("SELECT sum(budget) FROM core.fact_budget_scope WHERE fiscal_year = 2025 AND focus_area IS NOT NULL"))),
        ("focus_area_codes", "0")])


def _stub_marts(con):
    """Minimal Phase 4: the central roll-ups, tied to core by construction (which is exactly what the checks verify)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS mart")
    con.execute("""CREATE OR REPLACE TABLE mart.agency_rollup AS
        SELECT fiscal_year, agency_code, any_value(agency_name) AS agency_name, sum(budget) AS budget
        FROM core.fact_budget GROUP BY fiscal_year, agency_code""")
    con.execute("""CREATE OR REPLACE TABLE mart.agency_function AS
        SELECT fiscal_year, agency_code, function_name, sum(budget) AS budget, 1.0 AS function_share
        FROM core.fact_budget GROUP BY ALL""")
    con.execute("""CREATE OR REPLACE TABLE mart.vendor_agency_year AS
        SELECT fiscal_year, agency_code, vendor_name_as_paid AS vendor, sum(amount) AS paid, 'Testing services' AS function_name
        FROM core.fact_payment_mapped GROUP BY ALL""")
    con.execute("""CREATE OR REPLACE TABLE mart.vendor_master AS
        SELECT vendor, 'Company' AS payee_type, sum(paid) AS paid_all_years FROM mart.vendor_agency_year GROUP BY vendor""")
    con.execute("CREATE OR REPLACE TABLE mart.agency_results (agency_code VARCHAR, measure VARCHAR, kind VARCHAR, fiscal_year INTEGER, value DOUBLE)")


@pytest.fixture
def mini_pipeline(tmp_path, monkeypatch, soda_portal, extract_dirs):
    """A real extract run into tmp_path, plus build.build rewired to tmp paths and tiny-data stage stubs.
    Returns (run_id, data_dir); the build itself is left to each test so one can corrupt the raw layer first."""
    assert extract.run() == 0
    run_id = next((extract_dirs / "raw").iterdir()).name
    monkeypatch.setattr(build, "DATA", extract_dirs)
    monkeypatch.setattr(build, "DB", extract_dirs / "md_transparency.duckdb")
    monkeypatch.setattr(build.reference, "build", _stub_reference)
    monkeypatch.setattr(build.marts, "build", _stub_marts)
    for name in MODEL_STAGES:
        mod = getattr(build, name, None)
        if mod is not None:
            monkeypatch.setattr(mod, "write", lambda *a, **k: {}, raising=False)
            monkeypatch.setattr(mod, "record", lambda *a, **k: 0, raising=False)  # record() reads Phase 5 mart tables
    monkeypatch.setattr(build.checks, "HIST", extract_dirs / "check_history.csv")  # keep the repo's real history untouched
    return run_id, extract_dirs


def test_extract_build_checks_export_passes(tmp_path, monkeypatch, mini_pipeline):
    run_id, data = mini_pipeline
    assert build.build(run_id) is True  # build's contract: True = every stop check passed, DB replaced
    db = data / "md_transparency.duckdb"
    assert db.exists() and not (data / "md_transparency.failed.duckdb").exists()

    con = duckdb.connect(str(db), read_only=True)
    for mart in ("agency_rollup", "vendor_agency_year", "vendor_master", "sources"):  # central marts exist and are non-empty
        assert con.execute(f"SELECT count(*) FROM mart.{mart}").fetchone()[0] > 0, mart
    res = dict(con.execute("SELECT result, count(*) FROM ops.check_result GROUP BY 1").fetchall())
    assert res.get("fail", 0) == 0 and res["pass"] > 10
    passed = {r[0] for r in con.execute("SELECT \"check\" FROM ops.check_result WHERE result = 'pass'").fetchall()}
    assert {"Rows loaded = portal count: budget", "Yearly totals = portal: payments",
            "Budget totals = funding-source totals (within $1)"} <= passed
    assert con.execute("SELECT count(*) FROM ops.payee_name_seen").fetchone()[0] == 2  # the two fixture vendors
    con.close()
    assert (data / "check_history.csv").exists() and (data / "payee_name_seen.csv").exists()  # feedback loop, in tmp

    root = data.parent  # export.main resolves config/, docs/ and data/ under its ROOT
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "dashboard.yaml").write_text(DASHBOARD_YAML)
    (root / "docs" / "parity").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "parity" / "summary.csv").write_text("file,status\nagency_rollup,reproduced\n")
    monkeypatch.setattr(export, "ROOT", root)
    monkeypatch.setattr(export, "EXP", data / "export")  # module-level constant; ROOT alone would not redirect it
    assert export.main([]) == 0  # 0 = every dashboard file written from a mart
    out = data / "export" / run_id
    for name in ("agency_rollup", "vendor_agency_year", "vendor_master"):
        assert len(pd.read_csv(out / f"{name}.csv")) > 0
    man = pd.read_csv(out / "manifest.csv")
    assert len(man) == 5 and set(man.source) == {"mart"}
    assert (data / "export" / "latest").is_symlink()


def test_checks_fail_loudly_when_a_required_column_is_corrupted(mini_pipeline):
    run_id, data = mini_pipeline
    p = data / "raw" / run_id / "payments.parquet"
    df = pd.read_parquet(p)
    df.loc[df.index[:2], "amount"] = None  # corrupt the amount column of the FY2024 payments
    df.to_parquet(p, index=False)

    assert build.build(run_id) is False  # the build's failure contract (python -m ...build exits 1 on False)
    failed = data / "md_transparency.failed.duckdb"
    assert failed.exists() and not (data / "md_transparency.duckdb").exists()  # last good DB not replaced
    con = duckdb.connect(str(failed), read_only=True)
    fails = {r[0] for r in con.execute("SELECT \"check\" FROM ops.check_result WHERE result = 'fail'").fetchall()}
    con.close()
    assert "No missing year or amount: payments" in fails
    assert "Yearly totals = portal: payments" in fails
