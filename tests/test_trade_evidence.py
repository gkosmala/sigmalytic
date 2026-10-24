import math
from datetime import date, timedelta

import pytest

from backend import trade_evidence as te


def _days(n, start=date(2026, 1, 2)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(closes, rng):
    """[[date, o, h, l, c, v]] with a given high-low range per bar."""
    ds = _days(len(closes))
    return [[ds[i], c, c + rng[i] / 2, c - rng[i] / 2, c, 1_000_000] for i, c in enumerate(closes)]


def test_squeeze_detects_tight_range_after_wide_one():
    n = 200
    closes = [100 + (8 * math.sin(i / 3) if i < n - 25 else 0.2 * math.sin(i)) for i in range(n)]
    rng = [6.0 if i < n - 25 else 3.0 for i in range(n)]       # ATR stays wide-ish while closes go flat
    ev = te.squeeze_evidence(_bars(closes, rng), {"gamma_flip": 105.0, "call_wall": 110, "put_wall": 95})
    assert ev["assessed"] and ev["supported"]
    assert ev["bands_inside_keltner"] and ev["band_width_percentile_120d"] <= 10
    assert ev["below_gamma_flip"] is True


def test_squeeze_not_supported_when_volatility_expands():
    n = 200
    closes = [100 + (0.3 * math.sin(i) if i < n - 25 else 10 * math.sin(i / 2)) for i in range(n)]
    ev = te.squeeze_evidence(_bars(closes, [2.0] * n), {})
    assert ev["assessed"] and not ev["supported"] and ev["below_gamma_flip"] is None


def test_squeeze_needs_history():
    assert not te.squeeze_evidence(_bars([100.0] * 50, [1.0] * 50), {})["assessed"]


def test_selling_rule():
    intraday = [{"o": 10, "c": 9, "v": 700}, {"o": 9, "c": 9.5, "v": 300}]          # 70% on down bars
    weak = [["d", 10, 11, 9, 9.2, 100]] * 5                                         # closes near the lows
    ev = te.selling_evidence(intraday, weak)
    assert ev["supported"] and ev["down_volume_share"] == 0.7 and ev["close_location_5d"] == -0.8
    strong = [["d", 10, 11, 9, 10.8, 100]] * 5
    assert not te.selling_evidence(intraday, strong)["supported"]
    assert not te.selling_evidence([], weak)["assessed"]


def test_tape_stats_tick_rule_large_prints_and_off_exchange():
    st = te.TapeStats()
    last = st.add([
        {"p": 100.00, "s": 100, "x": "Q"},                       # first trade: no side
        {"p": 100.05, "s": 20000, "x": "D"},                     # uptick, large, off-exchange -> buy
        {"p": 100.01, "s": 15000, "x": "D", "c": ["W"]},         # average-price print: large, no side, no tick update
        {"p": 100.02, "s": 12000, "x": "N"},                     # down from 100.05 -> sell
        {"p": 0, "s": 5, "x": "Q"},                              # bad row ignored
    ], None)
    assert last == 100.02 and st.trades == 4 and st.volume == 47100
    assert st.off_volume == 35000 and st.large_trades == 3 and st.large_volume == 47000
    assert st.large_buy == 20000 and st.large_sell == 12000
    # Tick state carries across pages.
    st.add([{"p": 100.10, "s": 10000, "x": "Q"}], last)
    assert st.large_buy == 30000


def test_institutional_verdict():
    st = te.TapeStats()
    st.add([{"p": 50, "s": 100, "x": "Q"}] + [{"p": 50 + i * 0.01, "s": 10000, "x": "D"} for i in range(1, 6)]
           + [{"p": 50.06, "s": 100, "x": "Q"}] * 100, None)
    ev = te.institutional_evidence(st, {"vs_sma50_pct": 2.0}, "2026-10-22", True)
    assert ev["supported"] and ev["large_print_net_buying"] == 1.0 and ev["large_print_volume_share"] > 0.03
    assert not te.institutional_evidence(st, {"vs_sma50_pct": -1.0}, "2026-10-22", True)["supported"]
    assert not te.institutional_evidence(None, {}, "", False)["assessed"]


def test_last_complete_sessions_skips_live_bar():
    bars = [["2026-10-21"], ["2026-10-22"], ["2026-10-23"]]
    assert te.last_complete_sessions(bars, {"session": {"live": True}}, 2) == ["2026-10-21", "2026-10-22"]
    assert te.last_complete_sessions(bars, {"session": {"live": False}}, 2) == ["2026-10-22", "2026-10-23"]


class _Resp:
    def __init__(self, body, code=200):
        self._b, self.status_code, self.text, self.headers = body, code, str(body), {}

    def json(self):
        return self._b


def test_fetch_tape_pages_windows_and_reports_partial(monkeypatch):
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params.get("page_token"))
        page = int(params.get("page_token") or 0)
        nxt = str(page + 1) if page < 2 else None                 # every window has 3 pages
        return _Resp({"trades": [{"p": 10 + page * 0.01, "s": 100, "x": "D"}], "next_page_token": nxt})

    monkeypatch.setattr(te.requests, "get", fake_get)
    stats, complete = te.fetch_tape("X", "2026-10-22", max_pages=te.TAPE_WINDOWS * 3)
    assert complete and stats.trades == te.TAPE_WINDOWS * 3 and stats.off_volume == stats.volume
    stats, complete = te.fetch_tape("X", "2026-10-22", max_pages=te.TAPE_WINDOWS * 2)   # cap below need
    assert not complete and stats.trades == te.TAPE_WINDOWS * 2


def test_fetch_tape_fails_soft(monkeypatch):
    monkeypatch.setattr(te.requests, "get", lambda *a, **k: _Resp({"message": "forbidden"}, 403))
    assert te.fetch_tape("X", "2026-10-22", max_pages=13) == (None, False)


def test_private_block_text_and_selection():
    ev = {"institutional": {"assessed": False, "reason": "tape unavailable"},
          "selling": {"assessed": True, "supported": True, "down_volume_share": 0.66, "close_location_5d": -0.4},
          "squeeze": {"assessed": True, "supported": True, "bands_inside_keltner": True, "band_width_pct": 3.1,
                      "band_width_percentile_120d": 4.0, "atr14_vs_atr60": 0.7, "below_gamma_flip": True}}
    p = te.private_from_evidence(ev)
    assert not p["A"]["supported"] and "Not assessed: tape unavailable" in p["A"]["reasoning"]
    assert p["B"]["supported"] and "66.0%" in p["B"]["reasoning"]
    assert p["C"]["supported"] and "below the gamma flip" in p["C"]["reasoning"]
    assert p["selected"] == "multiple: B, C" and "fixed rules" in p["data_limits"]
    assert te.private_from_evidence({})["selected"] == "none"


def test_build_never_raises(monkeypatch):
    monkeypatch.setattr(te, "fetch_intraday", lambda s, d: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(te, "fetch_tape", lambda s, d: (None, False))
    ev = te.build("X", _bars([100.0] * 30, [1.0] * 30), {})
    assert not ev["squeeze"]["assessed"] and not ev["selling"]["assessed"] and not ev["institutional"]["assessed"]


def test_content_hub_package_uses_measured_evidence(monkeypatch):
    from backend import content_hub as ch
    import tests.test_content_hub as T
    facts = ch.facts_from_chart_data("TEST", T._chart())
    facts["_chart_bars"] = [["2026-08-01", 1, 2, 0.5, 1.5, 100]]
    monkeypatch.setattr(te, "build", lambda s, bars, f: {
        "squeeze": {"assessed": True, "supported": True, "bands_inside_keltner": True, "band_width_pct": 2.0,
                    "band_width_percentile_120d": 3.0, "atr14_vs_atr60": 0.6, "below_gamma_flip": False},
        "selling": {"assessed": False, "reason": "x"}, "institutional": {"assessed": False, "reason": "y"}})
    pkg = ch.build_package("TEST", use_ai=False, facts=facts)
    assert pkg["evidence"]["squeeze"]["supported"]
    assert pkg["blog"]["private"]["C"]["supported"] and not pkg["blog"]["private"]["A"]["supported"]
