"""Regression checks for session-specific OHLCV and DST boundaries."""

import unittest

from backend.chart_sessions import aggregate_session_bars, fetch_session_candles, session_bucket


def bar(stamp, price, volume):
    return {"t": stamp, "o": price, "h": price + 1, "l": price - 1,
            "c": price + .5, "v": volume}


class ChartSessionTests(unittest.TestCase):
    def test_seven_minute_bars_are_anchored_to_new_york_open(self):
        raw = [bar("2026-09-24T13:29:00Z", 8, 100),
               bar("2026-09-24T13:30:00Z", 10, 2),
               bar("2026-09-24T13:36:00Z", 12, 3),
               bar("2026-09-24T13:37:00Z", 11, 5),
               bar("2026-09-24T20:00:00Z", 20, 100)]
        result = aggregate_session_bars(raw, "7Min", "regular")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"t": "2026-09-24T13:30:00Z", "o": 10,
                                     "h": 13, "l": 9, "c": 12.5, "v": 5})
        self.assertEqual(result[1]["t"], "2026-09-24T13:37:00Z")

    def test_open_moves_with_daylight_saving(self):
        self.assertEqual(session_bucket("2026-01-05T14:30:00Z", "3Hour", "regular").isoformat(),
                         "2026-01-05T14:30:00+00:00")
        self.assertEqual(session_bucket("2026-07-06T13:30:00Z", "3Hour", "regular").isoformat(),
                         "2026-07-06T13:30:00+00:00")
        self.assertIsNone(session_bucket("2026-07-06T08:00:00Z", "3Hour", "regular"))
        self.assertIsNotNone(session_bucket("2026-07-06T08:00:00Z", "3Hour", "extended"))

    def test_premarket_candles_exclude_regular_session_and_follow_dst(self):
        self.assertEqual(session_bucket("2026-01-05T09:00:00Z", "1Hour", "premarket").isoformat(),
                         "2026-01-05T09:00:00+00:00")
        self.assertEqual(session_bucket("2026-07-06T08:00:00Z", "1Hour", "premarket").isoformat(),
                         "2026-07-06T08:00:00+00:00")
        raw = [bar("2026-09-24T07:59:00Z", 1, 100),
               bar("2026-09-24T08:00:00Z", 10, 2),
               bar("2026-09-24T13:29:00Z", 12, 3),
               bar("2026-09-24T13:30:00Z", 20, 100)]
        result = aggregate_session_bars(raw, "1Hour", "premarket")
        self.assertEqual(result[0], {"t": "2026-09-24T08:00:00Z", "o": 10,
                                     "h": 11, "l": 9, "c": 10.5, "v": 2})
        self.assertEqual(result[-1]["t"], "2026-09-24T13:00:00Z")
        self.assertEqual(result[-1]["v"], 3)
        self.assertEqual(len(result), 2)

    def test_fetch_paginates_back_to_requested_session_bars(self):
        pages = [
            {"bars": [bar("2026-09-24T13:44:00Z", 14, 2),
                      bar("2026-09-24T13:37:00Z", 11, 3)], "next_page_token": "older"},
            {"bars": [bar("2026-09-24T13:30:00Z", 10, 5),
                      bar("2026-09-24T08:00:00Z", 1, 99)]},
        ]

        class Source:
            def __init__(self):
                self.calls = 0

            def get(self, _url, **kwargs):
                page = pages[self.calls]
                self.calls += 1
                self.assert_token = kwargs["params"].get("page_token")
                return type("Response", (), {"ok": True, "json": lambda self: page})()

        source = Source()
        result = fetch_session_candles("AAPL", "7Min", "regular", 2, source,
                                       "https://example.invalid", {})
        self.assertEqual(source.calls, 2)
        self.assertEqual(source.assert_token, "older")
        self.assertEqual([b["t"] for b in result],
                         ["2026-09-24T13:37:00Z", "2026-09-24T13:44:00Z"])


if __name__ == "__main__":
    unittest.main()
