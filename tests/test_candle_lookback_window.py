"""
tests/test_candle_lookback_window.py
--------------------------------------
Regression coverage for the _calendar_days_per_bar sizing used in
backend/main.py's get_candles() to build the Alpaca bars request window.

WHY THIS EXISTS: for intraday timeframes, this used "~1 calendar day
per bar requested" -- correct for daily/weekly/monthly bars (where each
bar genuinely spans that much calendar time), but wildly wrong for
intraday bars, where many bars fit inside a single trading day (about
78 five-minute bars per 6.5-hour session). A 200-bar 5Min request
produced a ~210 calendar-day window; if Alpaca returns bars oldest-
first within that window and caps at the limit, the result is
genuinely old data (whatever the price was months ago), not recent
data -- which is exactly the sustained, reboot-proof candle/live-price
mismatch reported and confirmed on 2026-07-30. These tests pin the
corrected values down so intraday windows can't silently balloon back
out to multi-month spans.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import CANDLE_CALENDAR_DAYS_PER_BAR as _CALENDAR_DAYS_PER_BAR


def _lookback_days(timeframe: str, limit: int = 200) -> int:
    days_per_bar = _CALENDAR_DAYS_PER_BAR.get(timeframe, 1)
    return max(5, int(limit * days_per_bar) + 10)


def test_intraday_windows_stay_within_a_few_weeks():
    """
    The core regression guard: no intraday timeframe should ever request
    more than ~6 weeks of lookback for a 200-bar request. Before the
    fix, 5Min alone came out to 210 days (30 weeks) -- an order of
    magnitude over any reasonable bound.
    """
    for tf in ("1Min", "5Min", "15Min", "1Hour"):
        days = _lookback_days(tf, limit=200)
        assert days <= 42, (
            f"{tf} lookback window is {days} days -- intraday requests "
            f"should never need more than ~6 weeks for 200 bars."
        )


def test_5min_window_did_not_regress_to_seven_months():
    # The exact bug that was reported: 200 5-minute bars should need
    # roughly a week and a half, not 210 days.
    days = _lookback_days("5Min", limit=200)
    assert days < 30
    assert days != 210, "5Min window regressed back to the old, broken ~210-day value."


def test_1hour_window_did_not_regress_to_610_days():
    days = _lookback_days("1Hour", limit=200)
    assert days < 60
    assert days != 610, "1Hour window regressed back to the old, broken ~610-day value."


def test_daily_weekly_monthly_windows_unchanged():
    """
    These were already correct before the fix (each bar genuinely spans
    that much calendar time) -- confirming the fix didn't touch them.
    """
    assert _lookback_days("1Day", limit=200) == max(5, int(200 * 1.6) + 10)
    assert _lookback_days("1Week", limit=200) == max(5, int(200 * 8) + 10)
    assert _lookback_days("1Month", limit=200) == max(5, int(200 * 35) + 10)


def test_minimum_window_floor_still_applies():
    # Even a tiny bar request should still get a sane minimum window.
    days = _lookback_days("5Min", limit=1)
    assert days >= 5
