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
    assert "redrawLog" in doc and "chart log:" in doc


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


def test_walls_move_in_place_instead_of_a_full_redraw():
    doc = _chart_html()
    assert "function applyWallsInPlace" in doc
    # the in-place path must come before the full-redraw diagnostic/render path
    assert doc.index("applyWallsInPlace(msg)") < doc.index("FULL redraw: ")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_apply_walls_in_place_behaviour():
    """Run the real function against a stub Plotly/DOM: it moves only the changed wall's
    line + label, and refuses (so the caller does a full redraw) when the line isn't drawn."""
    doc = _chart_html()
    start = doc.index("function applyWallsInPlace")
    end = doc.index("window.addEventListener('message'", start)
    fn = doc[start:end]
    harness = "function noteLog() {}\n" + fn + r"""
const inputs = {callWall: {value: '101'}, putWall: {value: '99'}, gammaFlip: {value: '100'}};
const calls = [];
global.Plotly = {relayout: (p, u) => calls.push(u)};
function mk(shapes, anns) {
  global.document = {getElementById: (id) => id === 'chart'
    ? {layout: {shapes, annotations: anns}} : inputs[id]};
}
const S = (c) => ({line: {color: c, width: 1.5}});
const A = (t) => ({text: t});
mk([S('#aaaaaa'), S('#4da3ff'), S('#b06dff')], [A('x'), A('Call Wall'), A('Gamma Flip')]);
// gamma flip moved 100 -> 100.40, call wall unchanged within 0.05
let ok = applyWallsInPlace({callWall: 101.02, putWall: 99, gammaFlip: 100.4});
if (!ok) throw new Error('should have moved in place');
const u = calls[0];
if (u['shapes[2].y0'] !== 100.4 || u['shapes[2].y1'] !== 100.4 || u['annotations[2].y'] !== 100.4) throw new Error('wrong update ' + JSON.stringify(u));
if (Object.keys(u).some(k => k.indexOf('shapes[1]') === 0)) throw new Error('moved an unchanged wall');
if (inputs.gammaFlip.value !== 100.4) throw new Error('input not updated');
// put wall moved but no put-wall line is drawn -> must refuse
calls.length = 0;
ok = applyWallsInPlace({putWall: 97});
if (ok || calls.length) throw new Error('should have fallen back');
// nothing changed -> false
if (applyWallsInPlace({callWall: 101, putWall: 99, gammaFlip: 100.4})) throw new Error('no-op must be false');
console.log('ok');
"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(harness)
        r = subprocess.run(["node", path], capture_output=True, text=True)
        assert r.returncode == 0 and "ok" in r.stdout, r.stderr + r.stdout


def test_chart_reports_its_log_lines_to_the_server():
    doc = _chart_html()
    assert "/cc-client-log" in doc
    assert 'window.__ccSym = "AAPL"' in doc
    assert "chart document loaded" in doc
    assert "BLANK: no chart data on screen" in doc


def test_client_log_route_prints_and_is_rate_limited(capsys):
    client = app.server.test_client()
    app._CC_CLIENT_LOG_WINDOW.update({"minute": 0, "count": 0})
    r = client.post("/cc-client-log", data="AAPL 2:05:01 PM FULL redraw: new-bar", content_type="text/plain")
    assert r.status_code == 204
    assert "[CC_BROWSER] AAPL 2:05:01 PM FULL redraw: new-bar" in capsys.readouterr().out
    # flood: only the first 120 per minute are printed
    app._CC_CLIENT_LOG_WINDOW.update({"minute": int(__import__("time").time() // 60), "count": 0})
    for i in range(130):
        client.post("/cc-client-log", data=f"x{i}", content_type="text/plain")
    printed = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[CC_BROWSER] x")]
    assert len(printed) == 120


def test_client_log_text_is_capped_and_single_line(capsys):
    client = app.server.test_client()
    app._CC_CLIENT_LOG_WINDOW.update({"minute": 0, "count": 0})
    client.post("/cc-client-log", data="a\nb\r" + "z" * 1000, content_type="text/plain")
    line = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[CC_BROWSER]")][0]
    assert len(line) < 330 and "\n" not in line and "\r" not in line
