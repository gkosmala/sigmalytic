"""Astro Research (admin only): symbol table, hourly astro view, pivots from Alpaca bars, event backtest, plan draft.

Research tool. Drafts only; nothing is traded or posted. Planetary positions come from backend/astro_ephemeris.py.
Every symbol-table field carries a source and status so nothing is shown as more certain than it is.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import ephem

from backend import astro_ephemeris as ae

ET = ZoneInfo("America/New_York")
NOTE_GEOCODER = "Census geocoder point for the street address"
NOTE_USER = "Supplied by the user; not independently verified"

# elev_status: every elevation is user-supplied and approximate (no elevation service is reachable from the server).
SYMBOLS: List[Dict[str, Any]] = [
    {"symbol": "MSFT", "name": "Microsoft", "ipo_date": "1986-03-13", "address": "Redmond, WA campus (user's reference location)",
     "lat": 47 + 38 / 60 + 37 / 3600, "lon": -(122 + 7 / 60 + 51 / 3600), "elev_m": 111, "coord_source": "User's reference chart",
     "status": "reference"},
    {"symbol": "AAPL", "name": "Apple", "ipo_date": "1980-12-12", "address": "10260 Bandley Dr, Cupertino, CA",
     "lat": 37.326639, "lon": -122.034273, "elev_m": 72, "coord_source": NOTE_GEOCODER, "status": "address-sourced"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "ipo_date": "1972-09-27", "address": "901 Thompson Pl, Sunnyvale, CA",
     "lat": 37.382430, "lon": -122.007425, "elev_m": 21, "coord_source": NOTE_GEOCODER + " (matched ZIP 94085)", "status": "address-user"},
    {"symbol": "NVDA", "name": "NVIDIA", "ipo_date": "1999-01-22", "address": "3535 Monroe St, Santa Clara, CA",
     "lat": 37.366947, "lon": -121.993888, "elev_m": 17, "coord_source": NOTE_GEOCODER, "status": "address-sourced"},
    {"symbol": "MU", "name": "Micron Technology", "ipo_date": "1984-06-01", "address": "2805 E Columbia Rd, Boise, ID",
     "lat": 43.5171, "lon": -116.1465, "elev_m": 852, "coord_source": NOTE_USER + "; ~1.7 km from the geocoder point (unreconciled)",
     "status": "unreconciled"},
    {"symbol": "AMZN", "name": "Amazon", "ipo_date": "1997-05-15", "address": "1516 Second Ave, Seattle, WA",
     "lat": 47.609508, "lon": -122.339012, "elev_m": 44, "coord_source": NOTE_GEOCODER, "status": "address-sourced"},
    {"symbol": "GOOGL", "name": "Alphabet (Google)", "ipo_date": "2004-08-19", "address": "1600 Amphitheatre Pkwy, Mountain View, CA",
     "lat": 37.423124, "lon": -122.083521, "elev_m": 11, "coord_source": NOTE_GEOCODER, "status": "address-sourced"},
    {"symbol": "META", "name": "Meta (Facebook)", "ipo_date": "2012-05-18", "address": "1601 Willow Rd, Menlo Park, CA",
     "lat": 37.4817, "lon": -122.1489, "elev_m": 4, "coord_source": NOTE_USER + "; geocoder found no match", "status": "address-user"},
    {"symbol": "ORCL", "name": "Oracle", "ipo_date": "1986-03-12", "address": "20 Davis Dr, Belmont, CA",
     "lat": 37.5109, "lon": -122.3066, "elev_m": 5, "coord_source": NOTE_USER + "; ~0.3 km from the geocoder point", "status": "address-user"},
    {"symbol": "IBM", "name": "IBM (as Computing-Tabulating-Recording Co.)", "ipo_date": "1915-11-11", "address": "50 Broad St, New York, NY",
     "lat": 40.705574, "lon": -74.011536, "elev_m": 8, "coord_source": NOTE_GEOCODER, "status": "address-user"},
    {"symbol": "TSLA", "name": "Tesla", "ipo_date": "2010-06-29", "address": "3500 Deer Creek Rd, Palo Alto, CA",
     "lat": 37.395269, "lon": -122.149717, "elev_m": 104, "coord_source": NOTE_GEOCODER + "; elevation disputed (96 vs 104 m)",
     "status": "address-sourced"},
    {"symbol": "CSCO", "name": "Cisco", "ipo_date": "1990-02-16", "address": "1525 O'Brien Dr, Menlo Park, CA",
     "lat": 37.476647, "lon": -122.141317, "elev_m": 3, "coord_source": NOTE_GEOCODER, "status": "address-user"},
    {"symbol": "DELL", "name": "Dell (as Dell Computer Corp.)", "ipo_date": "1988-06-22", "address": "9505 Arboretum Blvd, Austin, TX",
     "lat": 30.393840, "lon": -97.749626, "elev_m": 241, "coord_source": NOTE_GEOCODER, "status": "address-user"},
]
for _r in SYMBOLS:
    _r.update({"first_trade_et": "09:30", "elev_status": "user-supplied, approximate",
               "ipo_status": "user-confirmed",
               "time_note": "9:30 a.m. ET is the default you set. Listings before 1985 opened later on the NYSE (to my knowledge 10:00 a.m.); "
                            "the real first print is not known to this tool."})
BY_SYMBOL = {r["symbol"]: r for r in SYMBOLS}

# The pivot table supplied for MSFT, kept only to cross-check the computed pivots.
PASTED_PIVOTS = {
    "MSFT": {"Absolute Cycle Low": (137.35, "2020-03"), "Intermediate High": (349.67, "2021-11"),
             "Major Higher Low": (213.43, "2022-11"), "Breakout Pivot": (467.56, "2024-07"),
             "Absolute Cycle High": (553.72, None)},
}


def ipo_moment_utc(row: Dict[str, Any]) -> datetime:
    y, m, d = (int(x) for x in row["ipo_date"].split("-"))
    hh, mm = (int(x) for x in row.get("first_trade_et", "09:30").split(":"))
    return datetime(y, m, d, hh, mm, tzinfo=ET).astimezone(timezone.utc)


def open_utc(day: str) -> datetime:
    y, m, d = (int(x) for x in day[:10].split("-"))
    return datetime(y, m, d, 9, 30, tzinfo=ET).astimezone(timezone.utc)


def table() -> List[Dict[str, Any]]:
    out = []
    for r in SYMBOLS:
        t = ipo_moment_utc(r)
        out.append({**r, "ipo_utc": t.strftime("%Y-%m-%d %H:%M UTC")})
    return out


# ── fast single-body longitudes (event study and windows) ──
_CLS = dict(ae.PLANETS)


def _lon(name: str, dt: datetime) -> float:
    d = ae._edate(dt)
    b = _CLS[name]()
    b.compute(d, epoch=d)
    return ae._ecl_lon_lat(b, d)[0]


def _sep(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def ipo_chart(symbol: str) -> Dict[str, Dict[str, Any]]:
    r = BY_SYMBOL[symbol]
    return ae.positions(ipo_moment_utc(r), r["lat"], r["lon"], r["elev_m"])


# ── pivots ──
def compute_pivots(bars: List[Dict[str, Any]], since: str = "2020-01-01") -> Dict[str, Any]:
    """Pivots from split-adjusted daily bars, by these fixed rules (intraday highs and lows):
    Absolute Cycle Low = lowest low since `since`; Absolute Cycle High = highest high after that low;
    Intermediate High / Major Higher Low = peak and trough of the largest peak-to-trough drop between the cycle low and
    cycle high (trough must stay above the cycle low); Breakout Pivot = peak of the largest drop between that trough and
    the cycle high."""
    rows = [b for b in bars if str(b.get("t", ""))[:10] >= since and b.get("h") and b.get("l")]
    if len(rows) < 60:
        return {"error": "Not enough daily bars for pivots."}
    hi = [float(b["h"]) for b in rows]
    lo = [float(b["l"]) for b in rows]
    day = [str(b["t"])[:10] for b in rows]
    il = min(range(len(rows)), key=lambda i: lo[i])
    ih = max(range(il, len(rows)), key=lambda i: hi[i])

    def biggest_drop(a: int, b: int):
        best = None
        peak = a
        for i in range(a + 1, b + 1):
            dd = (lo[i] - hi[peak]) / hi[peak]
            if best is None or dd < best[0]:
                best = (dd, peak, i)
            if hi[i] > hi[peak]:
                peak = i
        return best

    out = {"Absolute Cycle Low": {"price": lo[il], "date": day[il]}, "Absolute Cycle High": {"price": hi[ih], "date": day[ih]}}
    d1 = biggest_drop(il, ih)
    if d1 and lo[d1[2]] > lo[il]:
        out["Intermediate High"] = {"price": hi[d1[1]], "date": day[d1[1]]}
        out["Major Higher Low"] = {"price": lo[d1[2]], "date": day[d1[2]]}
        d2 = biggest_drop(d1[2], ih)
        if d2:
            out["Breakout Pivot"] = {"price": hi[d2[1]], "date": day[d2[1]]}
    order = ["Absolute Cycle Low", "Intermediate High", "Major Higher Low", "Breakout Pivot", "Absolute Cycle High"]
    return {"since": since, "pivots": [{"name": k, **out[k]} for k in order if k in out]}


def check_pivots(symbol: str, computed: Dict[str, Any]) -> List[Dict[str, Any]]:
    ref = PASTED_PIVOTS.get(symbol)
    if not ref:
        return []
    got = {p["name"]: p for p in computed.get("pivots", [])}
    rows = []
    for name, (price, ym) in ref.items():
        g = got.get(name)
        if not g:
            rows.append({"name": name, "pasted": price, "computed": None, "diff_pct": None, "date_match": None})
            continue
        rows.append({"name": name, "pasted": price, "computed": round(g["price"], 2), "computed_date": g["date"],
                     "diff_pct": round((g["price"] / price - 1) * 100, 2),
                     "date_match": None if ym is None else g["date"][:7] == ym})
    return rows


def fetch_bars(symbol: str, years: int = 8) -> List[Dict[str, Any]]:
    from backend import broker_market_data as bmd
    end = datetime.now(timezone.utc)
    return bmd.fetch_daily_bars([symbol], end - timedelta(days=int(365.25 * years) + 5), end).get(symbol) or []


# ── event study ──
HORIZONS = (1, 5, 10, 20)


def _event_days(bars: List[Dict[str, Any]], event: Dict[str, Any], symbol: str) -> List[int]:
    kind = event.get("kind")
    opens = [open_utc(str(b["t"])) for b in bars]
    idx: List[int] = []
    if kind == "moon_phase":
        want = event.get("phase", "new")
        ph = [ae.moon_phase(t) for t in opens]
        for i in range(1, len(ph)):
            if want == "new" and ph[i - 1] > 0.8 and ph[i] < 0.2:
                idx.append(i)
            if want == "full" and ph[i - 1] < 0.5 <= ph[i]:
                idx.append(i)
    elif kind == "station":
        body, to = event["body"], event.get("to", "retrograde")
        lon = [_lon(body, t) for t in opens]
        prev = [_lon(body, t - timedelta(hours=24)) for t in opens]
        rx = [((lon[i] - prev[i] + 180) % 360 - 180) < 0 for i in range(len(opens))]
        for i in range(1, len(rx)):
            if rx[i] != rx[i - 1] and rx[i] == (to == "retrograde"):
                idx.append(i)
    elif kind == "ipo_aspect":
        body, natal, asp = event["body"], event["natal"], event.get("aspect", "conjunction")
        orb = float(event.get("orb", 1.0))
        nat = ipo_chart(symbol)[natal]["lon"]
        ang = ae.ASPECTS[asp]
        inside = [abs(_sep(_lon(body, t), nat) - ang) <= orb for t in opens]
        for i in range(1, len(inside)):
            if inside[i] and not inside[i - 1]:
                idx.append(i)
    else:
        raise ValueError("Unknown event kind.")
    return idx


def backtest(bars: List[Dict[str, Any]], event: Dict[str, Any], symbol: str, draws: int = 2000, seed: int = 7) -> Dict[str, Any]:
    """Event study. Entry = open of the event day (9:30 a.m. ET, after the event is known); exit = close H-1 trading days
    later (H=1 is the same day). Compared with every trading day, and with a seeded random-day permutation test."""
    bars = [b for b in bars if b.get("o") and b.get("c")]
    if len(bars) < 250:
        return {"error": "Not enough daily bars for a backtest."}
    ev = _event_days(bars, event, symbol)
    o = [float(b["o"]) for b in bars]
    c = [float(b["c"]) for b in bars]
    out = []
    for H in HORIZONS:
        valid = [i for i in range(len(bars)) if i + H - 1 < len(bars)]
        ret = {i: (c[i + H - 1] / o[i] - 1) * 100 for i in valid}
        hits = [ret[i] for i in ev if i in ret]
        if not hits:
            out.append({"horizon": H, "n": 0})
            continue
        base = sum(ret.values()) / len(ret)
        mean = sum(hits) / len(hits)
        rng = random.Random(seed)
        pop = list(ret.values())
        extreme = sum(1 for _ in range(draws) if abs(sum(rng.sample(pop, len(hits))) / len(hits) - base) >= abs(mean - base))
        out.append({"horizon": H, "n": len(hits), "mean_pct": round(mean, 3), "hit_rate_pct": round(100 * sum(1 for x in hits if x > 0) / len(hits), 1),
                    "baseline_mean_pct": round(base, 3), "baseline_hit_rate_pct": round(100 * sum(1 for x in pop if x > 0) / len(pop), 1),
                    "p_value": round((extreme + 1) / (draws + 1), 3)})
    return {"event": event, "events_found": len(ev), "first_bar": str(bars[0]["t"])[:10], "last_bar": str(bars[-1]["t"])[:10],
            "results": out,
            "caveat": "Small samples and many possible events make chance results likely; a low p-value on one of many tests is not evidence."}


# ── windows and hourly view ──
def transit_windows(symbol: str, start: datetime, hours: int, orb: float = 1.0) -> List[Dict[str, Any]]:
    """Spans where a transiting planet is within `orb` degrees of an exact aspect to a planet in the IPO chart."""
    nat = ipo_chart(symbol)
    natal_names = [n for n, _ in ae.PLANETS]
    t0 = ae._utc(start).replace(minute=0, second=0, microsecond=0)
    state: Dict[Any, Dict[str, Any]] = {}
    done: List[Dict[str, Any]] = []
    for h in range(hours + 1):
        t = t0 + timedelta(hours=h)
        seen = set()
        for tb, _ in ae.PLANETS:
            lon = _lon(tb, t)
            for nb in natal_names:
                s = _sep(lon, nat[nb]["lon"])
                for asp, ang in ae.ASPECTS.items():
                    o = abs(s - ang)
                    if o <= orb:
                        k = (tb, asp, nb)
                        seen.add(k)
                        cur = state.setdefault(k, {"transit": tb, "aspect": asp, "natal": nb, "from": t, "tightest": o, "tightest_at": t})
                        cur["to"] = t
                        if o < cur["tightest"]:
                            cur["tightest"], cur["tightest_at"] = o, t
        for k in list(state):
            if k not in seen:
                done.append(state.pop(k))
    done.extend(state.values())
    f = lambda t: t.astimezone(ET).strftime("%a %b %d %I:%M %p ET").replace(" 0", " ")
    return [{"transit": w["transit"], "aspect": w["aspect"], "natal": w["natal"], "from": f(w["from"]), "to": f(w["to"]),
             "tightest_orb": round(w["tightest"], 2), "tightest_at": f(w["tightest_at"])}
            for w in sorted(done, key=lambda x: x["from"])]


def hourly_table(symbol: str, start: datetime, hours: int) -> List[Dict[str, Any]]:
    r = BY_SYMBOL[symbol]
    rows = ae.hourly(start, hours, r["lat"], r["lon"], r["elev_m"], bodies=[n for n, _ in ae.PLANETS])
    out = []
    for row in rows:
        t = datetime.fromisoformat(row["time"])
        out.append({"time_et": t.astimezone(ET).strftime("%a %b %d %I:%M %p"), "time_utc": t.strftime("%Y-%m-%d %H:%M"),
                    "moon_phase": row["moon_phase"],
                    "bodies": {k: v["position"] + (" R" if v["retrograde"] else "") for k, v in row["bodies"].items()}})
    return out


def plan_draft(symbol: str, start: datetime, hours: int, windows: List[Dict[str, Any]], pivots: Optional[Dict[str, Any]],
               bt: Optional[Dict[str, Any]] = None) -> str:
    r = BY_SYMBOL[symbol]
    L = [f"ASTRO RESEARCH DRAFT: {symbol} ({r['name']})",
         f"Window: {ae._utc(start).astimezone(ET).strftime('%a %b %d, %Y %I:%M %p ET')} for {hours} hours",
         f"Natal chart: {r['ipo_date']} at {r['first_trade_et']} ET, {r['address']} ({r['lat']:.4f}, {r['lon']:.4f}, {r['elev_m']} m)",
         ""]
    L.append("Transit aspects to the IPO chart within 1 degree:")
    if windows:
        for w in windows[:40]:
            L.append(f"- {w['transit']} {w['aspect']} natal {w['natal']}: {w['from']} to {w['to']}, tightest {w['tightest_orb']} deg at {w['tightest_at']}")
    else:
        L.append("- none in this window")
    L.append("")
    if pivots and pivots.get("pivots"):
        L.append(f"Price pivots from Alpaca daily bars (split-adjusted, since {pivots['since']}):")
        for p in pivots["pivots"]:
            L.append(f"- {p['name']}: ${p['price']:.2f} ({p['date']})")
        L.append("")
    if bt and bt.get("results"):
        L.append(f"Backtest of {bt['event']}: {bt['events_found']} events, {bt['first_bar']} to {bt['last_bar']}")
        for x in bt["results"]:
            if x.get("n"):
                L.append(f"- {x['horizon']} day(s): mean {x['mean_pct']}% vs {x['baseline_mean_pct']}% all days, "
                         f"hit rate {x['hit_rate_pct']}% vs {x['baseline_hit_rate_pct']}%, p={x['p_value']} (n={x['n']})")
        L.append(bt["caveat"])
        L.append("")
    L.append("Research draft only. Not a signal and not investment advice. Entry times assume 9:30 a.m. ET opens; first-trade time for older listings is unverified.")
    return "\n".join(L)


def run(symbol: str, start: datetime, hours: int = 48, pivots_since: str = "2020-01-01") -> Dict[str, Any]:
    if symbol not in BY_SYMBOL:
        raise ValueError("Symbol is not in the Astro Research table.")
    hours = max(1, min(int(hours), 168))
    r = BY_SYMBOL[symbol]
    nat = ipo_chart(symbol)
    now = ae.positions(start, r["lat"], r["lon"], r["elev_m"])
    windows = transit_windows(symbol, start, hours)
    piv: Dict[str, Any] = {}
    check: List[Dict[str, Any]] = []
    try:
        piv = compute_pivots(fetch_bars(symbol), pivots_since)
        check = check_pivots(symbol, piv)
    except Exception as exc:
        piv = {"error": f"Could not load Alpaca bars: {str(exc)[:160]}"}
    return {"row": {**r, "ipo_utc": ipo_moment_utc(r).strftime("%Y-%m-%d %H:%M UTC")},
            "ipo_chart": {k: v["position"] + (" R" if v["retrograde"] else "") for k, v in nat.items()},
            "start_chart": {k: v["position"] + (" R" if v["retrograde"] else "") for k, v in now.items()},
            "start_aspects": ae.aspects(now, bodies=[n for n, _ in ae.PLANETS])[:20],
            "hourly": hourly_table(symbol, start, min(hours, 72)), "windows": windows, "pivots": piv, "pivot_check": check,
            "draft": plan_draft(symbol, start, hours, windows, piv)}
