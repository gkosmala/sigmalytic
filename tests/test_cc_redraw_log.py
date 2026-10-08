"""The chart document carries the on-screen full-redraw log (diagnostic) and its script parses."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


def _chart_html():
    bars = [{"date": f"2026-10-{d:02d}T04:00:00Z", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}
            for d in range(1, 20)]
    return app._build_weis_radar_chart_html(
        {"symbol": "AAPL", "timeframe": "1D", "bars": bars, "hits": [],
         "call_wall": 101.0, "put_wall": 99.0, "gamma_flip": 100.0}, ma_period=20)


def test_redraw_log_is_in_the_chart_document():
    doc = _chart_html()
    assert "redrawLog" in doc and "full redraws:" in doc


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chart_script_parses():
    doc = _chart_html()
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", doc, flags=re.S)
    assert scripts
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "chart.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(scripts))
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
