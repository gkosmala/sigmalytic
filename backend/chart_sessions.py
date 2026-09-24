"""Session-correct equity candles for the interactive chart.

Alpaca does not offer a session parameter on its stock-bar endpoint. For a
selected regular or extended session, aggregate SIP minute/five-minute bars
after filtering in New York time so OHLC and volume use the selected hours.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
_TIMEFRAME = re.compile(r"^([1-9][0-9]?)(Min|Hour)$")
SESSION_WINDOWS = {"regular": (9 * 60 + 30, 16 * 60),
                   "extended": (4 * 60, 20 * 60)}


def session_bucket(timestamp: str, timeframe: str, session: str):
    """Return a New York-session-aligned UTC start, or None outside hours."""
    match = _TIMEFRAME.fullmatch(timeframe)
    if not match or session not in SESSION_WINDOWS:
        raise ValueError("Session bars require a minute/hour interval and a valid session")
    amount, unit = int(match[1]), match[2]
    if amount > (59 if unit == "Min" else 23):
        raise ValueError("Unsupported chart interval")
    duration = amount if unit == "Min" else amount * 60
    instant = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local = instant.astimezone(ET)
    opening, closing = SESSION_WINDOWS[session]
    minute = local.hour * 60 + local.minute
    if local.weekday() >= 5 or not opening <= minute < closing:
        return None
    bucket_minute = opening + ((minute - opening) // duration) * duration
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=bucket_minute)
    return start.astimezone(timezone.utc)


def aggregate_session_bars(raw_bars: list[dict], timeframe: str, session: str) -> list[dict]:
    groups = {}
    for source in sorted(raw_bars, key=lambda b: b["t"]):
        bucket = session_bucket(source["t"], timeframe, session)
        if bucket is None:
            continue
        stamp = bucket.isoformat().replace("+00:00", "Z")
        if stamp not in groups:
            groups[stamp] = {"t": stamp, "o": source["o"], "h": source["h"],
                             "l": source["l"], "c": source["c"], "v": source["v"]}
        else:
            bar = groups[stamp]
            bar["h"] = max(bar["h"], source["h"])
            bar["l"] = min(bar["l"], source["l"])
            bar["c"] = source["c"]
            bar["v"] += source["v"]
    return list(groups.values())


def fetch_session_candles(symbol, timeframe, session, limit, requests_module,
                          base_url, headers):
    """Fetch enough SIP source bars, keeping pagination bounded and explicit."""
    match = _TIMEFRAME.fullmatch(timeframe)
    if not match or session not in SESSION_WINDOWS:
        raise ValueError("Unsupported interval or session")
    amount, unit = int(match[1]), match[2]
    if amount > (59 if unit == "Min" else 23):
        raise ValueError("Minute intervals must be 1–59; hour intervals 1–23")
    duration = amount if unit == "Min" else amount * 60
    # Five-minute source bars are exact for any interval divisible by
    # five; odd intervals need 1-minute bars at the actual session edge.
    source_minutes = 5 if duration % 5 == 0 else 1
    source_tf = f"{source_minutes}Min"
    per_session = SESSION_WINDOWS[session][1] - SESSION_WINDOWS[session][0]
    needed = (limit + 2) * min(duration, per_session) // source_minutes
    if needed > 12000:
        raise ValueError("This session/interval needs more than 12,000 source bars; choose fewer chart bars")

    end = datetime.now(timezone.utc) + timedelta(days=1)
    days = max(10, int((limit + 4) * duration / per_session * 2.3) + 14)
    start = end - timedelta(days=days)
    params = {"timeframe": source_tf, "feed": "sip", "adjustment": "raw",
              "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "sort": "desc", "limit": 1000}
    raw = []
    for _ in range(13):
        response = requests_module.get(f"{base_url}/v2/stocks/{symbol}/bars",
                                       headers=headers, params=params, timeout=15)
        if not response.ok:
            raise ValueError(f"Alpaca bars HTTP {response.status_code}: {response.text[:150]}")
        payload = response.json() or {}
        page = payload.get("bars") or []
        raw.extend(page)
        bars = aggregate_session_bars(raw, timeframe, session)
        if len(bars) > limit or not page or not payload.get("next_page_token"):
            return bars[-limit:]
        params["page_token"] = payload["next_page_token"]
    raise ValueError("Chart source reached its 12,000-bar fetch limit; choose fewer chart bars")
