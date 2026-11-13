"""Offline extract tests against the recorded SODA portal (tests/fixtures/soda, wired up in conftest.py).

These cover what tests/test_extract.py cannot in CI (it needs a real `make extract` run): metadata
and paging behavior, the retry/backoff wrapper, the freshness-reuse path, and the self-healing
re-download — all without any network access.
"""
import json
import re
import socket
import time

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.pipeline import extract

IDS = {name: spec["id"] for name, spec in extract.CFG["datasets"].items()}


def test_portal_facts_come_from_the_recordings(soda_portal):
    c = extract.client()
    for name, fid in IDS.items():
        spec = extract.CFG["datasets"][name]
        updated, n, totals, pname = extract.portal_facts(c, fid, spec)
        rows = soda_portal.rows(fid)
        assert updated == soda_portal.meta(fid)["rowsUpdatedAt"]
        assert pname == spec["portal_name"]
        assert n == len(rows)
        assert sum(t["rows"] for t in totals) == n
        assert abs(sum(t["total"] for t in totals) - sum(float(r.get(spec["sum_col"]) or 0) for r in rows)) < 0.01


def test_download_paginates_until_a_short_page(soda_portal, tmp_path, monkeypatch):
    monkeypatch.setitem(extract.CFG, "page_size", 2)  # 6 budget rows -> pages of 2, 2, 2, then a short page
    dest = tmp_path / "budget.parquet"
    n = extract.download(extract.client(), IDS["budget"], dest)
    assert n == len(soda_portal.rows(IDS["budget"])) == pq.ParquetFile(dest).metadata.num_rows
    pages = [c for c in soda_portal.calls if "/resource/" in c and "$offset=" in c]
    assert [int(re.search(r"\$offset=(\d+)", c).group(1)) for c in pages] == [0, 2, 4, 6]


def test_call_retries_a_dropped_connection_then_succeeds(soda_portal):
    soda_portal.fail_next("/api/views/", times=1)
    meta = extract.call(lambda: extract.client().get_metadata(IDS["budget"]), "budget metadata")
    assert meta["rowsUpdatedAt"] == soda_portal.meta(IDS["budget"])["rowsUpdatedAt"]
    assert soda_portal.count_calls("/api/views/") == 2  # one failure, one success


def test_call_gives_up_after_the_configured_tries(soda_portal):
    soda_portal.fail_next("/api/views/", times=99)
    with pytest.raises(RuntimeError, match="gave up on budget metadata after 3 tries"):
        extract.call(lambda: extract.client().get_metadata(IDS["budget"]), "budget metadata", tries=3)
    assert soda_portal.count_calls("/api/views/") == 3


def test_extract_run_end_to_end_without_network(soda_portal, extract_dirs, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("extract touched the network outside the recorded portal")
    monkeypatch.setattr(socket, "create_connection", no_network)  # belt and braces: prove nothing escapes the mock
    assert extract.run() == 0
    run_dir = next((extract_dirs / "raw").iterdir())
    man = json.loads((run_dir / "manifest.json").read_text())
    assert man["status"] == "passed" and len(man["datasets"]) == len(IDS)
    for e in man["datasets"]:
        assert e["match"] and e["source"] == "downloaded" and e["heal_attempts"] == 0
        assert pq.ParquetFile(run_dir / f"{e['dataset']}.parquet").metadata.num_rows == e["portal_count"]
        assert sum(t["rows"] for t in e["portal_totals"]) == e["portal_count"]
    hist = pd.read_csv(extract_dirs / "runs.csv")
    assert len(hist) == 1 and hist.status.iloc[0] == "passed" and hist.downloaded.iloc[0] == len(IDS)


def test_second_run_reuses_unchanged_portal_data(soda_portal, extract_dirs):
    assert extract.run() == 0
    time.sleep(1.05)  # run ids have one-second resolution
    assert extract.run() == 0
    run_dir = sorted((extract_dirs / "raw").iterdir())[-1]
    man = json.loads((run_dir / "manifest.json").read_text())
    assert man["status"] == "passed"
    assert all(e["source"].startswith("reused") for e in man["datasets"])
    hist = pd.read_csv(extract_dirs / "runs.csv")
    assert len(hist) == 2 and hist.reused.iloc[-1] == len(IDS) and hist.downloaded.iloc[-1] == 0


def test_fault_hook_drives_self_healing_redownload(soda_portal, extract_dirs, monkeypatch):
    monkeypatch.setattr(extract, "FAULT", "fte")  # drops half the fte rows after download; the run must repair itself
    assert extract.run() == 0
    run_dir = next((extract_dirs / "raw").iterdir())
    man = json.loads((run_dir / "manifest.json").read_text())
    fte = next(e for e in man["datasets"] if e["dataset"] == "fte")
    assert fte["heal_attempts"] == 1 and fte["source"] == "re-downloaded (1)" and fte["match"]
    assert pq.ParquetFile(run_dir / "fte.parquet").metadata.num_rows == fte["portal_count"]
