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
import os

OWNER_DEFAULT = "greg.kosmala@gmail.com"


def owner_emails() -> set:
    """Who may use Astro Research. Default is the owner only; ASTRO_RESEARCH_EMAILS (comma separated) overrides it."""
    raw = os.getenv("ASTRO_RESEARCH_EMAILS") or OWNER_DEFAULT
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_owner(email: str) -> bool:
    return bool(email) and email.strip().lower() in owner_emails()


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
    {"symbol": 'AVGO', "name": 'Broadcom (as Avago Technologies)', "ipo_date": '2009-08-06', "address": '1320 Ridder Park Dr, San Jose, CA',
     "lat": 37.385070, "lon": -121.901317, "elev_m": 18,
     "coord_source": "Census geocoder point for 1320 Ridder Park Dr (supplied by the user from the geocoder page). User's minute value: 37°22'N 121°54'W.", "status": "address-user"},
    {"symbol": 'JPM', "name": 'JPMorgan Chase (as Chemical Bank, a predecessor)', "ipo_date": '1978-10-06', "address": '277 Park Ave, New York, NY',
     "lat": 40.755535, "lon": -73.975096, "elev_m": 16,
     "coord_source": "Census geocoder point (ZIP 10172; the ZIP supplied, 10017, did not match). The predecessor-bank date is the user's choice. User's minute value: 40°45'N 73°58'W.", "status": "address-user"},
    {"symbol": 'BRK.B', "name": 'Berkshire Hathaway (Class B launch)', "ipo_date": '1996-05-09', "address": '1440 Kiewit Plaza, Omaha, NE',
     "lat": 41.25, "lon": -95.95, "elev_m": 329, "coord_source": 'Supplied by the user at minute precision (about 1.5 km); not geocoded; geocoder found no match', "status": 'minute-only'},
    {"symbol": 'LLY', "name": 'Eli Lilly', "ipo_date": '1952-04-22', "address": '740 S Alabama St, Indianapolis, IN',
     "lat": 39.75944444444445, "lon": -86.15277777777779, "elev_m": 218,
     "coord_source": "Supplied by the user from another source as degrees, minutes and seconds (39°45'34\"N, 86°09'10\"W); the source is not named. User's earlier minute value: 39°45'N 86°09'W.", "status": "address-user"},
    {"symbol": 'XOM', "name": 'Exxon Mobil (merger date)', "ipo_date": '1999-11-30', "address": '5959 Las Colinas Blvd, Irving, TX',
     "lat": 32.88333333333333, "lon": -96.93333333333334, "elev_m": 149, "coord_source": 'Supplied by the user at minute precision (about 1.5 km); not geocoded; geocoder found no match. Merger date, not an IPO.', "status": 'minute-only'},
    {"symbol": 'WMT', "name": 'Walmart (as Wal-Mart Stores)', "ipo_date": '1970-10-01', "address": '702 SW 8th St, Bentonville, AR',
     "lat": 36.364326, "lon": -94.216644, "elev_m": 395,
     "coord_source": "Census geocoder point (matched ZIP 72712; the ZIP supplied was 72716). User's minute value: 36°21'N 94°12'W.", "status": "address-user"},
    {"symbol": 'ABBV', "name": 'AbbVie (Abbott spin-off)', "ipo_date": '2013-01-02', "address": '1 N Waukegan Rd, North Chicago, IL',
     "lat": 42.302166666666665, "lon": -87.89166666666667, "elev_m": 199,
     "coord_source": "Supplied by the user from another source as degrees and decimal minutes (42°18.13'N, 87°53.50'W); the source is not named and the point is about 5 km from the earlier minute value (42°19'N, 87°50'W), so it is unreconciled with the street address.", "status": "unreconciled"},
    {"symbol": 'COST', "name": 'Costco Wholesale', "ipo_date": '1985-12-05', "address": '10833 NE 8th St, Bellevue, WA',
     "lat": 47.617345, "lon": -122.195849, "elev_m": 43,
     "coord_source": "Census geocoder point; the 1985 address is the user's, unverified. User's minute value: 47°37'N 122°11'W.", "status": "address-user"},
    {"symbol": 'PLTR', "name": 'Palantir (direct listing)', "ipo_date": '2020-09-30', "address": '1200 17th St, Denver, CO',
     "lat": 39.749459, "lon": -104.995438, "elev_m": 1588,
     "coord_source": "Census geocoder point. User's minute value: 39°44'N 104°59'W.", "status": "address-user"},
    {"symbol": 'BAC', "name": 'Bank of America (as NCNB Corp, a predecessor)', "ipo_date": '1980-03-17', "address": '100 N Tryon St, Charlotte, NC',
     "lat": 35.227193, "lon": -80.842983, "elev_m": 229,
     "coord_source": "Census geocoder point; the predecessor date is the user's choice and the same date was earlier listed for JPM. User's minute value: 35°13'N 80°50'W.", "status": "address-user"},
    {"symbol": 'INTC', "name": 'Intel', "ipo_date": '1971-10-13', "address": '365 Middlefield Rd, Mountain View, CA',
     "lat": 37.38333333333333, "lon": -122.08333333333333, "elev_m": 32, "coord_source": 'Supplied by the user at minute precision (about 1.5 km); not geocoded; the geocoder matched 365 E Middlefield Rd about 2.5 km away, so the location is unreconciled', "status": 'unreconciled'},
    {"symbol": 'MDB', "name": 'MongoDB', "ipo_date": '2017-10-19', "address": '229 W 43rd St, New York, NY 10036 (the former New York Times building)',
     "lat": 40.75, "lon": -73.98333333333333, "elev_m": 16,
     "coord_source": "Supplied and confirmed by the user at minute precision (40°45'N 73°59'W, about 1.5 km); not geocoded.",
     "status": 'minute-only'},
    {"symbol": 'HPE', "name": 'Hewlett Packard Enterprise', "ipo_date": '2015-10-19', "address": '3000 Hanover St, Palo Alto, CA 94304',
     "lat": 37.4, "lon": -122.13333333333334, "elev_m": 85,
     "coord_source": "Supplied and confirmed by the user at minute precision (37°24'N 122°08'W, about 1.5 km); not geocoded.",
     "status": 'minute-only'},
    {"symbol": 'WDAY', "name": 'Workday', "ipo_date": '2012-10-12', "address": '6230 Stoneridge Mall Rd, Pleasanton, CA 94588',
     "lat": 37.68333333333333, "lon": -121.91666666666667, "elev_m": 104,
     "coord_source": "Supplied and confirmed by the user at minute precision (37°41'N 121°55'W, about 1.5 km); not geocoded.",
     "status": 'minute-only'},
]
for _r in SYMBOLS:
    _r.update({"first_trade_et": "09:30", "elev_status": "user-supplied, approximate",
               "ipo_status": "user-confirmed",
               "time_note": "9:30 a.m. ET is the default you set. Listings before 1985 opened later on the NYSE (to my knowledge 10:00 a.m.); "
                            "the real first print is not known to this tool."})
for _r in SYMBOLS:
    if _r["symbol"] == "WDAY":
        _r.update({"first_trade_et": "10:17", "ipo_status": "user-confirmed",
                   "time_note": "10:17 a.m. ET first-trade time supplied and confirmed by the user (the NYSE opening bell was at 9:30 a.m.)."})
    if _r["symbol"] == "HPE":
        _r.update({"first_trade_et": "09:30", "ipo_status": "user-confirmed",
                   "time_note": "HPE listed by spin-off. 2015-10-19 is the when-issued debut date and 9:30 a.m. ET the time, both supplied and confirmed by the user."})
    if _r["symbol"] == "MDB":
        _r.update({"first_trade_et": "10:53", "ipo_status": "user-confirmed",
                   "time_note": "10:53 a.m. ET first-trade time supplied and confirmed by the user (the Nasdaq opening bell was at 9:30 a.m.)."})
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


# ── Gann tools (from the attached material) ──
GANN_DAY_NUMBERS = (30, 45, 60, 90, 120, 135, 144, 180, 225, 360)
GANN_WEEK_NUMBERS = (13, 26, 39, 52)
OUTER = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
COE_BODIES = OUTER + ("Sun", "Mercury", "Venus")
LINE_BODIES = [n for n, _ in ae.PLANETS] + ["Moon's Node"]
FAMILY_LABEL = {"transit": "Planet line", "natal": "Natal planet line", "mean": "Mean of Five / Cycle of Eight",
                "sq9": "Square of 9", "pivot": "Pivot"}
SESSION_BLOCKS = [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30), (14, 30), (15, 30)]
PHASE = {(9, 30): "Opening drive; false-move risk", (10, 30): "True direction usually shows", (11, 30): "True direction usually shows (to 12:00)",
         (12, 30): "Midday", (13, 30): "Secondary move; trap risk", (14, 30): "Between rule windows",
         (15, 30): "Expansion or unwind (from 3:00 p.m.)"}


def price_unit(price: float) -> float:
    """Price per degree for planetary lines: 10 for index-size prices, 1 for ordinary stocks, 0.1 for low-priced ones."""
    return 10.0 if price >= 2000 else (1.0 if price >= 10 else 0.1)


def planet_lines(lons: Dict[str, float], ref: float, unit: float, band: float, family: str, tag: str = "") -> List[Dict[str, Any]]:
    """Planetary longitude to price: (longitude + 360 k) x unit, kept when within `band` (fraction) of the reference price."""
    out = []
    for name, lon in lons.items():
        k0 = round((ref / unit - lon) / 360.0)
        for k in (k0 - 1, k0, k0 + 1):
            price = (lon + 360.0 * k) * unit
            if price > 0 and abs(price / ref - 1) <= band:
                out.append({"price": price, "family": family, "label": f"{tag}{name} {lon:.2f} deg" + (f" (+{360 * k} deg)" if k else "")})
    return out


OCTAGON = tuple(range(0, 360, 45))


def octagon_levels(lons: Dict[str, float], ref: float, unit: float, band: float, source: str) -> List[Dict[str, Any]]:
    """Mean of Five and Cycle of Eight at every 45-degree octagon offset (and every 360-degree cycle) that lands within `band` of the price."""
    out = []
    for body in ("Mean of Five", "Cycle of Eight"):
        lon = lons[body]
        for off in OCTAGON:
            k0 = round((ref / unit - lon - off) / 360.0)
            for k in range(k0 - 1, k0 + 2):
                price = (lon + off + 360.0 * k) * unit
                if price > 0 and abs(price / ref - 1) <= band:
                    out.append({"price": price, "body": body, "source": source, "offset": off, "cycle": k,
                                "label": f"{source} {body} {lon:.2f} deg + {off} deg" + (f" (+{360 * k} deg)" if k else "")})
    return out


def mean_bands(levels: List[Dict[str, Any]], others: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bands between a Mean of Five level and the nearest Cycle of Eight level from the same source (and the reverse).
    The band's width is the measure of how tight the zone is; no tolerance is applied. `others` are the levels from the
    other methods; those inside a band are listed with it."""
    seen = {}
    for src in sorted({x["source"] for x in levels}):
        m = [x for x in levels if x["source"] == src and x["body"] == "Mean of Five"]
        c = [x for x in levels if x["source"] == src and x["body"] == "Cycle of Eight"]
        pairs = [(a, min(c, key=lambda y: abs(y["price"] - a["price"]))) for a in m if c] + \
                [(min(m, key=lambda y: abs(y["price"] - b["price"])), b) for b in c if m]
        for a, b in pairs:
            lo, hi = sorted((a["price"], b["price"]))
            key = (src, a["offset"], a["cycle"], b["offset"], b["cycle"])
            if key in seen:
                continue
            inside = [f"{o['label']} ${o['price']:.2f}" for o in others if lo <= o["price"] <= hi]
            seen[key] = {"key": list(key), "source": src, "low": round(lo, 2), "high": round(hi, 2), "width_pct": round((hi / lo - 1) * 100, 2),
                         "mean_of_five": f"{a['label']} ${a['price']:.2f}", "cycle_of_eight": f"{b['label']} ${b['price']:.2f}",
                         "inside": inside}
    return sorted(seen.values(), key=lambda z: z["width_pct"])


def mean_lons(pos: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """Mean of Five (Jupiter..Pluto) and Cycle of Eight (adds Sun, Mercury, Venus): plain averages of the longitudes."""
    return {"Mean of Five": sum(pos[b]["lon"] for b in OUTER) / 5.0, "Cycle of Eight": sum(pos[b]["lon"] for b in COE_BODIES) / 8.0}


def sq9_levels(price: float, label: str, steps: int = 8) -> List[Dict[str, Any]]:
    """(sqrt(price) +/- n x 0.25)^2; each 0.25 of the root is 45 degrees, 2.0 is a full 360-degree turn."""
    root = math.sqrt(price)
    out = []
    for n in range(1, steps + 1):
        for sign, word in ((1, "up"), (-1, "down")):
            r = root + sign * 0.25 * n
            if r > 0:
                out.append({"price": r * r, "family": "sq9", "label": f"{label} {word} {45 * n} deg"})
    return out


def time_counts(pivot_date: str, day: str) -> Dict[str, Any]:
    d = (date.fromisoformat(day) - date.fromisoformat(pivot_date[:10])).days
    nd = min(GANN_DAY_NUMBERS, key=lambda g: abs(g - d))
    nw = min(GANN_WEEK_NUMBERS, key=lambda g: abs(g - d / 7.0))
    return {"days": d, "weeks": round(d / 7.0, 2), "nearest_day_number": nd, "day_diff": d - nd,
            "nearest_week_number": nw, "week_diff": round(d / 7.0 - nw, 2),
            "flag": abs(d - nd) <= 3 or abs(d / 7.0 - nw) <= 0.5}


def confluence(levels: List[Dict[str, Any]], tol_pct: float = 0.2) -> List[Dict[str, Any]]:
    """Group levels within tol_pct of each other; keep groups that mix at least two families."""
    pts = sorted(levels, key=lambda x: x["price"])
    groups: List[List[Dict[str, Any]]] = []
    for p in pts:
        if groups and p["price"] <= groups[-1][-1]["price"] * (1 + tol_pct / 100.0):
            groups[-1].append(p)
        else:
            groups.append([p])
    out = []
    for g in groups:
        fams = {x["family"] for x in g}
        if len(fams) >= 2:
            out.append({"price": round(sum(x["price"] for x in g) / len(g), 2), "low": round(g[0]["price"], 2), "high": round(g[-1]["price"], 2),
                        "score": len(fams) * 10 + len(g), "families": sorted(FAMILY_LABEL[f] for f in fams),
                        "members": [f"{x['label']} ${x['price']:.2f}" for x in g]})
    return out


def closest_cross_family_gap(levels: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The two nearest levels that come from different methods, so an empty confluence list can say how close it was."""
    pts = sorted(levels, key=lambda x: x["price"])
    best = None
    for i, x in enumerate(pts):
        for y in pts[i + 1:]:
            gap = (y["price"] / x["price"] - 1) * 100.0
            if best is not None and gap >= best["gap_pct"]:
                break
            if x["family"] != y["family"]:
                best = {"gap_pct": round(gap, 3), "a": f"{x['label']} ${x['price']:.2f}", "b": f"{y['label']} ${y['price']:.2f}"}
                break
    return best


def weekly_bars(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    wk: Dict[Any, Dict[str, Any]] = {}
    for b in bars:
        d = date.fromisoformat(str(b["t"])[:10])
        key = d.isocalendar()[:2]
        w = wk.get(key)
        if not w:
            wk[key] = {"t": str(b["t"])[:10], "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]), "c": float(b["c"])}
        else:
            w["h"], w["l"], w["c"] = max(w["h"], float(b["h"])), min(w["l"], float(b["l"])), float(b["c"])
    return list(wk.values())


def _signed(a: float, b: float, ang: float) -> float:
    return ((a - b - ang + 180) % 360) - 180


def exact_events(natal: Dict[str, Dict[str, Any]], t0: datetime, t1: datetime, step_min: int = 5) -> List[Dict[str, Any]]:
    """Exact planet-to-planet and transit-to-IPO-chart aspects between t0 and t1 (5-minute steps, linear interpolation)."""
    names = [n for n, _ in ae.PLANETS]
    n_steps = int((t1 - t0).total_seconds() // 60 // step_min)
    times = [t0 + timedelta(minutes=step_min * i) for i in range(n_steps + 1)]
    lons = [{n: _lon(n, t) for n in names} for t in times]
    ev: List[Dict[str, Any]] = []

    def scan(fa, fb, a, b, kind):
        for asp, ang in ae.ASPECTS.items():
            for sgn in ({1} if ang in (0, 180) else {1, -1}):
                d = [_signed(fa(i), fb(i), sgn * ang) for i in range(len(times))]
                for i in range(len(d) - 1):
                    if d[i] == d[i + 1] or d[i] * d[i + 1] > 0 or abs(d[i] - d[i + 1]) > 30:
                        continue
                    frac = d[i] / (d[i] - d[i + 1])
                    ev.append({"time": times[i] + timedelta(minutes=step_min * frac), "kind": kind, "a": a, "b": b, "aspect": asp})

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            scan(lambda k, a=a: lons[k][a], lambda k, b=b: lons[k][b], a, b, "planets")
        for b in names:
            nl = natal[b]["lon"]
            scan(lambda k, a=a: lons[k][a], lambda k, nl=nl: nl, a, b, "natal")
    return sorted(ev, key=lambda e: e["time"])


def day_events(day: str) -> List[Dict[str, Any]]:
    """Sign ingresses, stations and (via exact_events) the lunar phases for the whole ET calendar day."""
    y, m, d = (int(x) for x in day.split("-"))
    t0 = datetime(y, m, d, 0, 0, tzinfo=ET).astimezone(timezone.utc)
    out = []
    for name, _ in ae.PLANETS:
        lons = [_lon(name, t0 + timedelta(hours=h)) for h in range(0, 25)]
        for h in range(24):
            if int(lons[h] // 30) != int(lons[h + 1] // 30) and abs(lons[h] - lons[h + 1]) < 20:
                out.append(f"{name} enters {ae.SIGNS[int(lons[h + 1] // 30)]} around {(t0 + timedelta(hours=h)).astimezone(ET).strftime('%I:%M %p ET').lstrip('0')}")
        sp = [((lons[h + 1] - lons[h] + 180) % 360 - 180) for h in range(24)]
        for h in range(23):
            if name not in ("Sun", "Moon") and sp[h] * sp[h + 1] < 0:
                out.append(f"{name} stations {'retrograde' if sp[h + 1] < 0 else 'direct'} around {(t0 + timedelta(hours=h + 1)).astimezone(ET).strftime('%I:%M %p ET').lstrip('0')}")
    return out


def _fmt_et(t: datetime) -> str:
    return t.astimezone(ET).strftime("%I:%M %p ET").lstrip("0")


def report(symbol: str, day: str, pivots_since: str = "2020-01-01", unit: Optional[float] = None, band: float = 0.12) -> Dict[str, Any]:
    """Ephemeris report + pivots + Gann levels + hourly tactical plan for one symbol and one date (all admin research)."""
    if symbol not in BY_SYMBOL:
        raise ValueError("Symbol is not in the Astro Research table.")
    d0 = date.fromisoformat(day)
    row = BY_SYMBOL[symbol]
    lat, lon_, elev = row["lat"], row["lon"], row["elev_m"]
    bars = fetch_bars(symbol)
    before = [b for b in bars if str(b["t"])[:10] < day]
    same = [b for b in bars if str(b["t"])[:10] == day]
    if len(before) < 120:
        raise ValueError("Not enough Alpaca daily history before that date.")
    ref = float(before[-1]["c"])
    unit = float(unit) if unit else price_unit(ref)
    notes: List[str] = []
    if d0.weekday() >= 5:
        notes.append("That date is a weekend; hours are shown for reference but the market is closed.")

    dp = compute_pivots(before, pivots_since)
    wp = compute_pivots(weekly_bars(before), pivots_since)
    check = check_pivots(symbol, dp)
    piv_rows = []
    for tag, pv in (("Daily", dp), ("Weekly", wp)):
        for p in pv.get("pivots", []):
            piv_rows.append({"frame": tag, **p, "counts": time_counts(p["date"], day)})
    uniq: List[Dict[str, Any]] = []
    for p in piv_rows:
        if not any(abs(p["price"] / q["price"] - 1) < 0.005 for q in uniq):
            uniq.append(p)

    natal = ipo_chart(symbol)
    open_t = open_utc(day)
    t_end = datetime(d0.year, d0.month, d0.day, 16, 0, tzinfo=ET).astimezone(timezone.utc)
    events = exact_events(natal, open_t, t_end)
    # keep the report readable: Moon aspects, hard aspects between planets, and hard aspects to the IPO chart
    keep = [e for e in events if e["kind"] == "natal" and e["aspect"] in ("conjunction", "square", "opposition")
            or e["kind"] == "planets" and ("Moon" in (e["a"], e["b"]) or e["aspect"] in ("conjunction", "square", "opposition"))]
    static = [dict(l) for p in uniq for l in sq9_levels(p["price"], f"{p['name']} ${p['price']:.2f}")]
    static += [{"price": p["price"], "family": "pivot", "label": p["name"]} for p in uniq]
    static = [l for l in static if abs(l["price"] / ref - 1) <= band]
    natal_lons = {n: natal[n]["lon"] for n in LINE_BODIES}
    nm = mean_lons(natal)
    static += planet_lines(natal_lons, ref, unit, band, "natal", "Natal ") + planet_lines(nm, ref, unit, band, "mean", "Natal ")

    natal_oct = octagon_levels(nm, ref, unit, band, "Natal")
    blocks = []
    bands_all: List[Dict[str, Any]] = []
    zones_all: List[Dict[str, Any]] = []
    diag_gap: Optional[Dict[str, Any]] = None
    diag_levels = 0
    for hh, mm in SESSION_BLOCKS:
        t = datetime(d0.year, d0.month, d0.day, hh, mm, tzinfo=ET).astimezone(timezone.utc)
        t_next = t + timedelta(minutes=60 if (hh, mm) != (15, 30) else 30)
        pos = ae.positions(t, lat, lon_, elev)
        dyn = planet_lines({n: pos[n]["lon"] for n in LINE_BODIES}, ref, unit, band, "transit", "Transit ")
        dyn += planet_lines(mean_lons(pos), ref, unit, band, "mean", "Transit ")
        zones = confluence(static + dyn)
        lv_all = static + dyn
        near_up = sorted([x for x in lv_all if x["price"] > ref], key=lambda x: x["price"])[:2]
        near_dn = sorted([x for x in lv_all if x["price"] <= ref], key=lambda x: -x["price"])[:2]
        others = [x for x in lv_all if x["family"] != "mean"]
        bands = mean_bands(natal_oct + octagon_levels(mean_lons(pos), ref, unit, band, "Transit"), others)
        bands.sort(key=lambda z: (0 if z["low"] <= ref <= z["high"] else 1, abs((z["low"] + z["high"]) / 2 - ref)))
        bands_all.extend(bands)
        gap = closest_cross_family_gap(lv_all)
        if gap and (diag_gap is None or gap["gap_pct"] < diag_gap["gap_pct"]):
            diag_gap = gap
        diag_levels = max(diag_levels, len(lv_all))
        above = sorted([z for z in zones if z["price"] > ref], key=lambda z: z["price"])[:2]
        below = sorted([z for z in zones if z["price"] <= ref], key=lambda z: -z["price"])[:2]
        zones_all.extend(zones)
        evs = [e for e in keep if t <= e["time"] < t_next]
        marks = []
        if t <= datetime(d0.year, d0.month, d0.day, 12, 0, tzinfo=ET).astimezone(timezone.utc) < t_next:
            marks.append("Wheel of 24: 12:00 ET = 180 degrees")
        if t <= datetime(d0.year, d0.month, d0.day, 15, 0, tzinfo=ET).astimezone(timezone.utc) < t_next:
            marks.append("Wheel of 24: 3:00 p.m. ET = 225 degrees")
        if (hh, mm) == (12, 30):
            marks.append("Octagon: 3 hours (45 degrees) after the open")
        if (hh, mm) == (15, 30):
            marks.append("Octagon: 6 hours (90 degrees) after the open")
        hard = [e for e in evs if e["aspect"] in ("conjunction", "square", "opposition")]
        label = lambda e: (f"{e['a']} {e['aspect']} {e['b']}" if e["kind"] == "planets" else f"{e['a']} {e['aspect']} IPO-chart {e['b']}") + f" at {_fmt_et(e['time'])}"
        blocks.append({"time_et": f"{t.astimezone(ET).strftime('%I:%M %p').lstrip('0')} - {_fmt_et(t_next)}", "time_utc": t.strftime("%H:%M"),
                       "phase": PHASE[(hh, mm)], "moon": pos["Moon"]["position"], "sun": pos["Sun"]["position"],
                       "events": [label(e) for e in evs], "marks": marks, "attention": "High" if hard or marks else "Normal",
                       "above": above, "below": below,
                       "mean_bands": bands[:3],
                       "near_above": [{"price": round(x["price"], 2), "label": x["label"]} for x in near_up],
                       "near_below": [{"price": round(x["price"], 2), "label": x["label"]} for x in near_dn]})
    top = sorted({(z["price"], z["score"]): z for z in zones_all}.values(), key=lambda z: -z["score"])[:12]
    top_bands = sorted({tuple(z["key"]): z for z in bands_all}.values(), key=lambda z: z["width_pct"])[:8]
    result = {"row": {**row, "ipo_utc": ipo_moment_utc(row).strftime("%Y-%m-%d %H:%M UTC")}, "day": day, "ref_price": round(ref, 2),
              "ref_date": str(before[-1]["t"])[:10], "unit": unit, "band_pct": band * 100, "notes": notes,
              "actual": ({"open": same[0]["o"], "high": same[0]["h"], "low": same[0]["l"], "close": same[0]["c"]} if same else None),
              "open_chart": {k: {"position": v["position"] + (" R" if v["retrograde"] else ""), "lon": round(v["lon"], 2)}
                             for k, v in ae.positions(open_t, lat, lon_, elev).items()},
              "ipo_chart": {k: v["position"] + (" R" if v["retrograde"] else "") for k, v in natal.items()},
              "moon_phase_open": round(ae.moon_phase(open_t), 3), "day_events": day_events(day),
              "exact_events": [{"time": _fmt_et(e["time"]), "text": (f"{e['a']} {e['aspect']} {e['b']}" if e["kind"] == "planets" else f"{e['a']} {e['aspect']} IPO-chart {e['b']}")}
                               for e in keep],
              "windows": transit_windows(symbol, open_t, 7),
              "pivots_daily": dp, "pivots_weekly": wp, "pivot_rows": piv_rows, "pivot_check": check,
              "natal_mean": {k: round(v, 2) for k, v in nm.items()}, "top_zones": top, "top_bands": top_bands, "blocks": blocks,
              "confluence_diag": {"tolerance_pct": 0.2, "levels_found": diag_levels, "closest_pair": diag_gap},
              "hourly": hourly_table(symbol, open_t, 7)}
    result["draft"] = report_text(result)
    return result


def no_confluence_note(r: Dict[str, Any]) -> str:
    """Why the confluence list is empty, in plain words."""
    d = r.get("confluence_diag") or {}
    cp = d.get("closest_pair")
    base = f"No confluence found: no two different methods landed within {d.get('tolerance_pct', 0.2)}% of each other ({d.get('levels_found', 0)} levels were in range)."
    if cp:
        base += f" The closest pair was {cp['gap_pct']}% apart ({cp['a']} and {cp['b']})."
    return base + " The nearest single-method levels are listed in the hourly plan; they are not confluence."


def report_text(r: Dict[str, Any]) -> str:
    row = r["row"]
    L = [f"ASTRO RESEARCH REPORT: {row['symbol']} ({row['name']}) for {r['day']}",
         f"Location used: {row['address']} ({row['lat']:.4f}, {row['lon']:.4f}, {row['elev_m']} m)",
         f"IPO chart: {row['ipo_utc']}. Reference price: ${r['ref_price']:.2f} (close of {r['ref_date']}). Price per degree: ${r['unit']:g}.", ""]
    L.append("1. EPHEMERIS AT THE OPEN (9:30 a.m. ET)")
    L.append("   " + "; ".join(f"{k} {v['position']}" for k, v in r["open_chart"].items()))
    L.append(f"   Moon phase at the open: {r['moon_phase_open']} (0 new, 0.5 full)")
    if r["day_events"]:
        L += ["   Today: " + "; ".join(r["day_events"])]
    L.append("   Exact aspects during the session: " + ("; ".join(f"{e['text']} at {e['time']}" for e in r["exact_events"]) or "none"))
    L.append("")
    L.append("2. MAJOR MARKET STRUCTURE AND INTERMEDIATE PIVOTS (Alpaca split-adjusted bars before the report date)")
    for p in r["pivot_rows"]:
        c = p["counts"]
        L.append(f"   {p['frame']:<6} {p['name']:<20} ${p['price']:>9.2f}  {p['date']}  {c['days']} days / {c['weeks']} weeks ago"
                 + (f"  [near Gann count {c['nearest_day_number']}d / {c['nearest_week_number']}w]" if c["flag"] else ""))
    L.append("")
    L.append("3. GANN CONFLUENCE ZONES (price levels where two or more methods agree within 0.2%)")
    for z in r["top_zones"]:
        L.append(f"   ${z['price']:.2f} (score {z['score']}): " + "; ".join(z["members"][:6]))
    if not r["top_zones"]:
        L.append("   " + no_confluence_note(r))
    L.append("")
    L.append("3b. MEAN OF FIVE / CYCLE OF EIGHT OCTAGON BANDS (price between the two means at 45-degree octagon offsets; the band width is the tightness, no tolerance applied)")
    for z in r.get("top_bands", []):
        L.append(f"   ${z['low']:.2f} to ${z['high']:.2f} (width {z['width_pct']}%, {z['source'].lower()}): {z['mean_of_five']}; {z['cycle_of_eight']}"
                 + (f"; inside the band: " + "; ".join(z["inside"][:4]) if z["inside"] else ""))
    if not r.get("top_bands"):
        L.append("   No Mean of Five / Cycle of Eight octagon levels fall within range.")
    L.append("")
    L.append("4. HOURLY TACTICAL PLAN (levels are references, not forecasts)")
    for b in r["blocks"]:
        L.append(f"   {b['time_et']}  [{b['phase']}]  Attention: {b['attention']}  Moon {b['moon']}")
        for x in b["events"] + b["marks"]:
            L.append(f"      - {x}")
        up = ", ".join(f"${z['price']:.2f}" for z in b["above"]) or "none within range"
        dn = ", ".join(f"${z['price']:.2f}" for z in b["below"]) or "none within range"
        L.append(f"      Reversal-watch zones above ${r['ref_price']:.2f}: {up}   below: {dn}")
        if b.get("mean_bands"):
            L.append("      Mean/Cycle bands: " + "; ".join(
                f"${z['low']:.2f}-${z['high']:.2f} ({z['width_pct']}% wide, {z['source'].lower()})" + (" [holds the reference price]" if z["low"] <= r["ref_price"] <= z["high"] else "")
                for z in b["mean_bands"]))
        if not b["above"] and not b["below"]:
            nu = ", ".join(f"${x['price']:.2f} ({x['label']})" for x in b.get("near_above", [])) or "none in range"
            nd = ", ".join(f"${x['price']:.2f} ({x['label']})" for x in b.get("near_below", [])) or "none in range"
            L.append(f"      Nearest single-method levels (NOT confluence): above: {nu}   below: {nd}")
    L.append("")
    L.append("   Rules from the source material: a reversal needs location (a zone above), structure and volume to agree; a candle alone does not count. "
             "Mid-range prices and conflicting signals are a no-trade area. Do not chase a move that is already extended into a zone.")
    L.append("")
    L.append("Research draft only. Not a signal and not investment advice. The first-trade time and the symbol-table elevations are unverified; see the table notes.")
    return "\n".join(L)
