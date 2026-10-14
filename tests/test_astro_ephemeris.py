"""Acceptance test: reproduces the reference chart for 2026-10-13 02:30:01 UTC, 47°38'37"N 122°07'51"W, 111 m."""
from datetime import datetime, timezone

from backend import astro_ephemeris as ae

T = datetime(2026, 10, 13, 2, 30, 1, tzinfo=timezone.utc)
LAT, LON, ELEV = 47 + 38 / 60 + 37 / 3600, -(122 + 7 / 60 + 51 / 3600), 111


def L(sign, d, m, s):
    return ae.SIGNS.index(sign) * 30 + d + m / 60 + s / 3600


# (reference longitude, tolerance in arcminutes). Tolerances are the largest differences measured.
REF = {
    "Sun": (L("Lib", 19, 46, 42), 1.0), "Moon": (L("Sco", 18, 5, 9), 1.0), "Mercury": (L("Sco", 14, 45, 57), 1.0),
    "Venus": (L("Sco", 6, 35, 54), 1.0), "Mars": (L("Leo", 8, 35, 15), 1.0), "Jupiter": (L("Leo", 21, 38, 52), 1.0),
    "Saturn": (L("Ari", 10, 37, 52), 1.0), "Uranus": (L("Gem", 5, 16, 7), 1.0), "Neptune": (L("Ari", 2, 32, 5), 1.0),
    "Pluto": (L("Aqr", 3, 4, 16), 1.0), "Moon's Node": (L("Aqr", 28, 31, 16), 0.5),
    "Apogee": (L("Cap", 10, 27, 5), 6.0), "Galactic Center": (L("Sag", 27, 13, 33), 0.5),
}


def test_reference_chart_longitudes():
    pos = ae.positions(T, LAT, LON, ELEV)
    for name, (ref, tol) in REF.items():
        diff = abs((pos[name]["lon"] - ref + 180) % 360 - 180) * 60
        assert diff <= tol, f"{name}: {diff:.2f} arcmin off (limit {tol})"


def test_retrograde_flags_and_moon_phase():
    pos = ae.positions(T, LAT, LON, ELEV)
    retro = {n for n, v in pos.items() if v["retrograde"]}
    assert {"Venus", "Saturn", "Uranus", "Neptune", "Pluto"} <= retro
    assert not retro & {"Sun", "Moon", "Mercury", "Mars", "Jupiter"}
    assert abs(ae.moon_phase(T) - 0.079) < 0.005


def test_aspects_and_hourly_series():
    pos = ae.positions(T, LAT, LON, ELEV)
    asp = ae.aspects(pos, bodies=["Sun", "Moon", "Mercury", "Venus"])
    assert all(a["orb"] <= ae.DEFAULT_ORBS[a["aspect"]] for a in asp)
    rows = ae.hourly(T, 3, LAT, LON, ELEV, bodies=["Sun", "Moon"])
    assert len(rows) == 3 and rows[0]["time"].startswith("2026-10-13T02:00")
    moon = [r["bodies"]["Moon"]["lon"] for r in rows]
    assert 0.3 < (moon[1] - moon[0]) % 360 < 0.9           # about half a degree per hour
