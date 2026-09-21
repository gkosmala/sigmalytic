"""Regression coverage for the persistent Weis Radar configuration."""

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.weis_radar_scan import (
    RADAR_LOOKBACK_LIMITS,
    WEIS_RADAR_SCAN_CHUNK_SIZE,
    _configured_signal_key,
    _dispatch_configured_alerts,
    _load_radar_config,
    _normalize_signal_hits,
    run_weis_radar_scan,
)


class _FakeRedis:
    def __init__(self, payload):
        self.payload = payload

    def get(self, key):
        return json.dumps(self.payload)


def test_config_is_sanitized_before_a_scan_uses_it():
    config = _load_radar_config(_FakeRedis({
        "display_signals": ["spring", "breakout", "not_real"],
        "alert_signals": ["breakout", "upthrust"],
        "timeframe": "15Min",
        "lookback": 900,
        "sms_enabled": True,
    }))

    assert config == {
        "display_signals": ["spring", "breakout"],
        "timeframe": "15Min",
        "lookback": 500,
        "alert_signals": ["breakout"],
        "sms_enabled": True,
        "email_enabled": False,
    }


def test_long_lookbacks_use_timeframe_specific_limits():
    daily = _load_radar_config(_FakeRedis({"timeframe": "1Day", "lookback": 900}))
    daily_too_large = _load_radar_config(_FakeRedis({"timeframe": "1Day", "lookback": 9999}))
    weekly_too_large = _load_radar_config(_FakeRedis({"timeframe": "1Week", "lookback": 9999}))

    assert daily["lookback"] == 900
    assert daily_too_large["lookback"] == RADAR_LOOKBACK_LIMITS["1Day"] == 2520
    assert weekly_too_large["lookback"] == RADAR_LOOKBACK_LIMITS["1Week"] == 1040

    expected_hourly_limits = {"1Hour": 5292, "2Hour": 3024, "4Hour": 1512}
    for timeframe, expected_limit in expected_hourly_limits.items():
        config = _load_radar_config(_FakeRedis({
            "timeframe": timeframe,
            "lookback": 99999,
        }))
        assert config["timeframe"] == timeframe
        assert config["lookback"] == expected_limit


def test_engine_labels_map_back_to_saved_signal_keys():
    assert _configured_signal_key("3BAR_BULLISH") == "3bar"
    assert _configured_signal_key("CLIMAX_BUY") == "climaxup"
    assert _configured_signal_key("NO_SUPPLY (absorption)") == "absorption"
    assert _configured_signal_key("SIGN_OF_WEAKNESS") == "sign_of_weakness"


def test_shared_signal_results_are_normalized_for_the_frontend():
    hits = _normalize_signal_hits([
        {"signal": "SPRING", "score": 18},
        {"signal": "BREAKOUT", "detail": {"level": 100, "held": True}},
        {"signal": "WYCKOFF_ENGINE_ERROR", "error": "ignored"},
    ], 105.5)

    assert hits == [
        {"type": "SPRING", "price": 105.5, "score": 18.0},
        {"type": "BREAKOUT", "price": 105.5, "level": 100, "held": True},
    ]


def test_production_scan_loads_config_and_uses_shared_signal_engine():
    source = inspect.getsource(run_weis_radar_scan)
    assert "_load_radar_config" in source
    assert "compute_symbol_signals" in source
    assert 'timeframe=config["timeframe"]' in source
    assert "_dispatch_configured_alerts" in source


def test_production_scan_fetches_the_universe_in_bounded_chunks():
    symbols = [f"S{i:03d}" for i in range((WEIS_RADAR_SCAN_CHUNK_SIZE * 2) + 3)]
    fetch_calls = []

    def fake_fetch(symbol_chunk, **kwargs):
        fetch_calls.append((list(symbol_chunk), kwargs))
        return {
            symbol: [{"c": 100.0, "t": "2026-09-21T20:00:00Z"}]
            for symbol in symbol_chunk
        }

    fake_radar_service = SimpleNamespace(
        _redis_client=None,
        compute_symbol_signals=lambda *args, **kwargs: [],
        fetch_bars_batch=fake_fetch,
        load_russell1000=lambda: symbols,
        min_bars_required_for=lambda requested: 1,
        trim_incomplete_bar=lambda bars, timeframe: bars,
    )
    fake_engine_module = SimpleNamespace(WyckoffVerdictEngine=lambda: object())

    with patch.dict(sys.modules, {
        "backend.radar_service": fake_radar_service,
        "backend.research_engine.wyckoff_verdict_engine": fake_engine_module,
    }):
        result = run_weis_radar_scan()

    assert [len(call[0]) for call in fetch_calls] == [
        WEIS_RADAR_SCAN_CHUNK_SIZE,
        WEIS_RADAR_SCAN_CHUNK_SIZE,
        3,
    ]
    assert all(call[1]["limit"] == 253 for call in fetch_calls)
    assert result["scanned"] == len(symbols)
    assert result["errors"] == 0


def test_operator_alerts_are_deduplicated_per_symbol_signal_and_bar():
    calls = []

    class AlertRedis:
        def __init__(self):
            self.keys = set()

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return False
            self.keys.add(key)
            return True

    fake_email = SimpleNamespace(
        send_admin_alert_sync=lambda *args, **kwargs: calls.append(("email", args, kwargs)) or True
    )
    fake_sms = SimpleNamespace(
        send_signal_sms=lambda *args, **kwargs: calls.append(("sms", args, kwargs)) or True
    )
    results = [{
        "symbol": "TEST",
        "last_bar_time": "2026-09-21T16:00:00Z",
        "hits": [{"type": "SPRING", "price": 123.45, "score": 18}],
    }]
    config = {
        "alert_signals": ["spring"],
        "email_enabled": True,
        "sms_enabled": True,
        "timeframe": "1Day",
    }
    redis = AlertRedis()

    with patch.dict(sys.modules, {
        "backend.email_service": fake_email,
        "backend.sms_alerts": fake_sms,
    }):
        assert _dispatch_configured_alerts(results, config, redis) == 1
        assert _dispatch_configured_alerts(results, config, redis) == 0

    assert [call[0] for call in calls] == ["email", "sms"]


def test_worker_schedule_uses_the_saved_timeframe_cadence():
    source = Path("tools/render_radar_scanner_worker.py").read_text(encoding="utf-8")
    assert "_load_radar_config" in source
    assert '"5Min": 5 * 60' in source
    assert '"1Hour": 60 * 60' in source
    assert '"2Hour": 2 * 60 * 60' in source
    assert '"4Hour": 4 * 60 * 60' in source
    assert "_weis_radar_interval_seconds()" in source


def test_hourly_fetch_windows_and_ui_include_two_and_four_hour_bars():
    service_source = Path("backend/radar_service.py").read_text(encoding="utf-8")
    frontend_source = Path("frontend/app.py").read_text(encoding="utf-8")

    assert '"1Hour": 7, "2Hour": 4, "4Hour": 2' in service_source
    assert '"1Hour": 1300, "2Hour": 1300, "4Hour": 1300' in service_source
    assert '("2 Hours", "2Hour")' in frontend_source
    assert '("4 Hours", "4Hour")' in frontend_source
