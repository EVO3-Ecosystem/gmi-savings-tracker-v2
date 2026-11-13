"""Shared test fixtures: a recorded, offline stand-in for the Maryland open data portal (SODA).

extract.py reaches the portal through sodapy, whose only HTTP call is `requests.Session.get`.
The `soda_portal` fixture replaces that one method with a router serving `tests/fixtures/soda/**`:
metadata by dataset id, row pages sliced by $limit/$offset, and count(*) / per-year sum() totals
computed from the same recorded rows, so the portal and the downloads always agree. Any URL
outside the recorded routes fails the test instead of touching the network.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "soda"
DOMAIN = "opendata.maryland.gov"


class _Response:
    """Just enough of requests.Response for sodapy.Socrata._perform_request."""

    def __init__(self, payload, status=200):
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(payload)
        self.reason = "OK" if status == 200 else "Error"
        self._payload = payload

    def json(self):
        return self._payload


class RecordedSODA:
    """Routes requests.Session.get calls to the recorded fixtures. Also records every call."""

    def __init__(self, monkeypatch):
        self.calls = []  # every request the code made, "url k=v k=v" (params sorted)
        self._failures = []  # [substring, remaining times, exception]: injected transient errors
        monkeypatch.setattr(requests.Session, "get", self._get)
        from src.pipeline import extract
        monkeypatch.setitem(extract.CFG, "backoff_seconds", 0)  # retries stay fast in tests

    def rows(self, fid):
        return json.loads((FIXTURES / "rows" / f"{fid}.json").read_text())

    def meta(self, fid):
        return json.loads((FIXTURES / "metadata" / f"{fid}.json").read_text())

    def fail_next(self, substring, times=1):
        """Make the next `times` matching calls raise a connection error (drives extract.call's retry)."""
        self._failures.append([substring, times, requests.exceptions.ConnectionError("recorded transient failure")])

    def count_calls(self, substring):
        return sum(substring in c for c in self.calls)

    def _get(self, url, **kwargs):  # class attribute -> plain function; no `self` session binding
        params = dict(kwargs.get("params") or {})
        key = url + " " + " ".join(f"{k}={v}" for k, v in sorted(params.items()))
        self.calls.append(key)
        for f in self._failures:
            if f[0] in key and f[1] > 0:
                f[1] -= 1
                raise f[2]
        if DOMAIN not in url:
            raise AssertionError(f"test tried to reach a non-recorded URL: {url}")
        path = urlparse(url).path
        m = re.fullmatch(r"/api/views/([a-z0-9-]+)\.json", path)
        if m:
            return _Response(self.meta(m.group(1)))
        m = re.fullmatch(r"/resource/([a-z0-9-]+)\.json", path)
        if not m:
            raise AssertionError(f"no recorded route for {url}")
        rows = self.rows(m.group(1))
        select = params.get("$select", "")
        if "sum(" in select:  # per-year totals, computed from the same rows so portal and download agree
            year_col = re.search(r"(\w+) as fiscal_year", select).group(1)
            sum_col = re.search(r"sum\((\w+)\)", select).group(1)
            totals = {}
            for r in rows:
                if r.get(year_col) is None:
                    continue
                t = totals.setdefault(r[year_col], [0.0, 0])
                t[0] += float(r.get(sum_col) or 0)
                t[1] += 1
            out = [{"fiscal_year": y, "total": str(t[0]), "rows": str(t[1])}
                   for y, t in sorted(totals.items(), key=lambda kv: int(float(kv[0])))]
            return _Response(out)
        if "count(*)" in select:
            return _Response([{"n": str(len(rows))}])
        limit = int(params.get("$limit", 1000))
        offset = int(params.get("$offset", 0))
        return _Response(rows[offset:offset + limit])


@pytest.fixture
def soda_portal(monkeypatch):
    """The recorded SODA portal; extract code runs against it fully offline."""
    return RecordedSODA(monkeypatch)


@pytest.fixture
def extract_dirs(tmp_path, monkeypatch):
    """Redirect extract.py's data/raw and runs.csv into tmp_path and stub the non-portal context sources
    (enrich.py pulls BLS/Census/USAspending over the network; it is not part of the SODA extract under test)."""
    from src.pipeline import enrich, extract
    data = tmp_path / "data"
    monkeypatch.setattr(extract, "RAW", data / "raw")
    monkeypatch.setattr(extract, "RUNS", data / "runs.csv")
    monkeypatch.setattr(enrich, "run_all", lambda out, prev, log: [])
    return data
