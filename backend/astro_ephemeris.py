"""Local planetary-position calculator for the admin Astro Research tool.

No network, no API keys, no rate limits: positions are computed on the server with the `ephem` library (VSOP87/ELP
analytic theories). Every value is tropical, geocentric ecliptic longitude of date, in degrees, except the Moon, which is
reported topocentric for the chart location (that is how the reference chart supplied for acceptance testing was cast).

Acceptance test: tests/test_astro_ephemeris.py reproduces the reference chart for 2026-10-13 02:30:01 UTC at
47°38'37"N 122°07'51"W, 111 m, to within the tolerances listed there.

Not covered yet: Chiron, Quaoar and Sedna (they need small-body orbital elements that are not available offline).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import ephem

SIGNS = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqr", "Pis"]
PLANETS = [("Sun", ephem.Sun), ("Moon", ephem.Moon), ("Mercury", ephem.Mercury), ("Venus", ephem.Venus),
           ("Mars", ephem.Mars), ("Jupiter", ephem.Jupiter), ("Saturn", ephem.Saturn), ("Uranus", ephem.Uranus),
           ("Neptune", ephem.Neptune), ("Pluto", ephem.Pluto)]
ASPECTS = {"conjunction": 0.0, "sextile": 60.0, "square": 90.0, "trine": 120.0, "opposition": 180.0}
DEFAULT_ORBS = {"conjunction": 6.0, "sextile": 3.0, "square": 5.0, "trine": 5.0, "opposition": 6.0}
GALACTIC_CENTER = ("17:45:40.04", "-29:00:28.1")   # J2000 RA/Dec of Sgr A*
_AU = 1.495978707e11
_MU_EARTH_MOON = (3.986004418e14 + 4.9028695e12) / _AU ** 3 * 86400 ** 2   # AU^3/day^2


def _dms(deg: float) -> str:
    sign = "-" if deg < 0 else ""
    a = abs(deg)
    d = int(a)
    m = int((a - d) * 60)
    s = round(((a - d) * 60 - m) * 60)
    if s == 60:
        s, m = 0, m + 1
    if m == 60:
        m, d = 0, d + 1
    return f"{sign}{d}°{m:02d}'{s:02d}\""


def sign_position(lon: float) -> str:
    """359.2 -> '29 Pis 12'' (sign, whole degrees, minutes)."""
    lon %= 360
    s, rem = int(lon // 30), lon % 30
    d = int(rem)
    m = int((rem - d) * 60)
    return f"{d:02d} {SIGNS[s]} {m:02d}'"


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _edate(dt: datetime) -> ephem.Date:
    dt = _utc(dt)
    return ephem.Date(dt.replace(tzinfo=None))


def _ecl_lon_lat(body: Any, d: ephem.Date, topocentric: bool = False) -> Tuple[float, float]:
    if topocentric:
        ec = ephem.Ecliptic(ephem.Equatorial(body.ra, body.dec, epoch=d))
    else:
        ec = ephem.Ecliptic(body, epoch=d)
    return math.degrees(ec.lon) % 360, math.degrees(ec.lat)


def _observer(lat: float, lon: float, elev_m: float, d: ephem.Date) -> ephem.Observer:
    o = ephem.Observer()
    o.lat, o.lon, o.elevation = math.radians(lat), math.radians(lon), float(elev_m)
    o.date, o.epoch, o.pressure = d, d, 0
    return o


def _moon_vec(d: ephem.Date) -> List[float]:
    m = ephem.Moon()
    m.compute(d, epoch=d)
    ec = ephem.Ecliptic(ephem.Equatorial(m.g_ra, m.g_dec, epoch=d))
    r, lo, la = m.earth_distance, ec.lon, ec.lat
    return [r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)]


def true_node(dt: datetime) -> float:
    """Longitude of the Moon's true ascending node (mean node plus the principal periodic terms)."""
    jd = float(_edate(dt)) + 2415020.0
    t = (jd - 2451545.0) / 36525.0
    r = math.radians
    om = 125.0445479 - 1934.1362891 * t + 0.0020754 * t * t
    d = (297.8501921 + 445267.1114034 * t - 0.0018819 * t * t) % 360
    m = (357.5291092 + 35999.0502909 * t) % 360
    mp = (134.9633964 + 477198.8675055 * t + 0.0087414 * t * t) % 360
    f = (93.2720950 + 483202.0175233 * t - 0.0036539 * t * t) % 360
    node = (om - 1.4979 * math.sin(r(2 * (d - f))) - 0.1500 * math.sin(r(m)) - 0.1226 * math.sin(r(2 * d))
            + 0.1176 * math.sin(r(2 * f)) - 0.0801 * math.sin(r(2 * (mp - f))))
    return node % 360


def osculating_apogee(dt: datetime) -> float:
    """Longitude of the Moon's osculating (instantaneous) lunar apogee."""
    d0 = _edate(dt)
    h = 1.0 / 1440.0
    rp, rm, r = _moon_vec(ephem.Date(d0 + h)), _moon_vec(ephem.Date(d0 - h)), _moon_vec(d0)
    v = [(a - b) / (2 * h) for a, b in zip(rp, rm)]
    hv = [r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0]]
    vxh = [v[1] * hv[2] - v[2] * hv[1], v[2] * hv[0] - v[0] * hv[2], v[0] * hv[1] - v[1] * hv[0]]
    rn = math.sqrt(sum(c * c for c in r))
    e = [vxh[i] / _MU_EARTH_MOON - r[i] / rn for i in range(3)]
    return math.degrees(math.atan2(-e[1], -e[0])) % 360


def galactic_center(dt: datetime) -> Dict[str, float]:
    d = _edate(dt)
    eqd = ephem.Equatorial(ephem.Equatorial(GALACTIC_CENTER[0], GALACTIC_CENTER[1], epoch="2000"), epoch=d)
    ec = ephem.Ecliptic(eqd, epoch=d)
    return {"lon": math.degrees(ec.lon) % 360, "lat": math.degrees(ec.lat)}


def positions(dt: datetime, lat: float, lon: float, elev_m: float = 0.0) -> Dict[str, Dict[str, Any]]:
    """All bodies for one moment. `lon` is east-positive degrees (Redmond is about -122.13)."""
    d = _edate(dt)
    obs = _observer(lat, lon, elev_m, d)
    prev, nxt = ephem.Date(d - 1 / 24.0), ephem.Date(d + 1 / 24.0)
    out: Dict[str, Dict[str, Any]] = {}
    for name, cls in PLANETS:
        b = cls()
        if name == "Moon":
            b.compute(obs)
            lo, la = _ecl_lon_lat(b, d, topocentric=True)
        else:
            b.compute(d, epoch=d)
            lo, la = _ecl_lon_lat(b, d)
        b1, b2 = cls(), cls()
        b1.compute(prev, epoch=prev)
        b2.compute(nxt, epoch=nxt)
        l1, l2 = _ecl_lon_lat(b1, prev)[0], _ecl_lon_lat(b2, nxt)[0]
        speed = ((l2 - l1 + 180) % 360 - 180) / 2.0          # degrees per hour
        out[name] = {"lon": lo, "lat": la, "retrograde": speed < 0 and name not in ("Sun", "Moon"),
                     "speed_per_hour": speed, "position": sign_position(lo)}
    node = true_node(dt)
    out["Moon's Node"] = {"lon": node, "lat": 0.0, "retrograde": True, "position": sign_position(node)}
    apo = osculating_apogee(dt)
    out["Apogee"] = {"lon": apo, "lat": None, "retrograde": False, "position": sign_position(apo)}
    gc = galactic_center(dt)
    out["Galactic Center"] = {"lon": gc["lon"], "lat": gc["lat"], "retrograde": False, "position": sign_position(gc["lon"])}
    return out


def moon_phase(dt: datetime) -> float:
    """0.0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter (elongation of the Moon from the Sun)."""
    d = _edate(dt)
    s, m = ephem.Sun(), ephem.Moon()
    s.compute(d, epoch=d)
    m.compute(d, epoch=d)
    return ((_ecl_lon_lat(m, d)[0] - _ecl_lon_lat(s, d)[0]) % 360) / 360.0


def aspects(pos: Dict[str, Dict[str, Any]], orbs: Optional[Dict[str, float]] = None,
            bodies: Optional[List[str]] = None, other: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Major aspects within orb. With `other` (for example an IPO chart) aspects run from `pos` to `other`."""
    orbs = {**DEFAULT_ORBS, **(orbs or {})}
    names = [n for n in (bodies or [n for n, _ in PLANETS]) if n in pos]
    out = []
    pairs = ([(a, b) for a in names for b in (bodies or [n for n, _ in PLANETS]) if b in (other or {})]
             if other is not None else [(a, b) for i, a in enumerate(names) for b in names[i + 1:]])
    for a, b in pairs:
        la = pos[a]["lon"]
        lb = (other or pos)[b]["lon"]
        sep = abs((la - lb + 180) % 360 - 180)
        for asp, ang in ASPECTS.items():
            orb = abs(sep - ang)
            if orb <= orbs[asp]:
                out.append({"a": a, "b": b, "aspect": asp, "orb": round(orb, 3), "separation": round(sep, 3)})
    return sorted(out, key=lambda x: x["orb"])


def hourly(start: datetime, hours: int, lat: float, lon: float, elev_m: float = 0.0,
           bodies: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """One row per whole hour from `start` (UTC): longitudes plus moon phase."""
    rows = []
    t0 = _utc(start).replace(minute=0, second=0, microsecond=0)
    for h in range(hours):
        t = t0 + timedelta(hours=h)
        p = positions(t, lat, lon, elev_m)
        keep = {k: v for k, v in p.items() if not bodies or k in bodies}
        rows.append({"time": t.isoformat(), "moon_phase": round(moon_phase(t), 4), "bodies": keep})
    return rows
