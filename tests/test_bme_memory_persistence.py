"""
tests/test_bme_memory_persistence.py
---------------------------------------
Regression coverage for the Behavioral Memory Engine's (BME)
restart-persistence fix.

WHY THIS EXISTS: user noticed something odd -- "Deep engine confirms
radar (+0.0)" and "Strong engine agreement (100.0)" showing up
identically across every symbol in the radar scan's "Why This Trade"
evidence. Traced this to a real, confirmed bug: save_memory_to_supabase()
genuinely worked (BME's trained memory bank was correctly saved after
training), but load_memory_from_supabase() -- the function that would
restore that saved memory when the worker restarts -- was fully
implemented and correct, but never called anywhere in the entire
codebase. Every worker restart wiped the in-memory bank back to empty
regardless of what had already been learned, forcing every symbol back
through the "NO_MEMORY" neutral-default path (bme_score always exactly
50.0), which is why the "deep engine" comparison against composite_score
was always exactly 0.0 delta / 100.0 agreement for every symbol -- not a
real second opinion, just a structurally-guaranteed non-comparison.

These tests lock in that load_memory_from_supabase() is now actually
wired into start_radar_scheduler(), and that loading genuinely restores
usable memory (confirmed: a loaded symbol no longer falls into the
NO_MEMORY evaluate() path).
"""
import sys
import os
import json
import inspect
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backend.behavioral_memory as bme
from backend.radar_service import start_radar_scheduler


def test_start_radar_scheduler_calls_load_memory_from_supabase():
    """
    Regression guard for the exact bug: load_memory_from_supabase()
    existed and worked correctly but was never called anywhere. Must
    now be called from start_radar_scheduler(), before any training or
    scanning begins.
    """
    src = inspect.getsource(start_radar_scheduler)
    assert "load_memory_from_supabase" in src, (
        "start_radar_scheduler() must call load_memory_from_supabase() "
        "at startup -- without this, every worker restart wipes the BME "
        "memory bank back to empty regardless of what was already "
        "learned and saved, forcing every symbol through the NO_MEMORY "
        "neutral-default path."
    )


def test_start_radar_scheduler_loads_memory_before_historical_bar_fetch():
    """
    Order matters: memory should be restored before the (slow) historical
    bar fetch and fresh training kick off, so a restart only needs to
    train genuinely new symbols, not the whole universe from scratch.
    """
    src = inspect.getsource(start_radar_scheduler)
    load_pos = src.index("load_memory_from_supabase")
    bars_pos = src.index("_refresh_historical_bars")
    assert load_pos < bars_pos, (
        "load_memory_from_supabase() must be called BEFORE the "
        "historical bar fetch thread starts, so restored memory is "
        "available immediately rather than racing against fresh "
        "training that takes much longer to complete."
    )


def test_load_memory_from_supabase_actually_populates_the_bank():
    """
    End-to-end confirmation that loading genuinely works, not just that
    it's called: a symbol restored from a mocked Supabase response must
    actually end up usable in the in-memory bank.
    """
    fake_bank_data = {
        "AAPL": {"cluster_centers": [300.0, 310.0], "trained_at": "2026-08-01T00:00:00Z"},
    }
    fake_response = MagicMock()
    fake_response.data = {"data": json.dumps(fake_bank_data), "count": 1}
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = fake_response

    with patch.object(bme, "_get_supabase", return_value=fake_sb):
        with bme._bank_lock:
            bme._memory_bank.clear()
        count = bme.load_memory_from_supabase()

    assert count == 1
    with bme._bank_lock:
        assert "AAPL" in bme._memory_bank


def test_evaluate_no_longer_returns_no_memory_after_load():
    """
    The real, user-visible effect of the fix: a symbol with restored
    memory must not fall into the NO_MEMORY neutral-default path (the
    one that produces the always-identical bme_score=50.0, and by
    extension the always-identical "Deep engine confirms radar (+0.0)"
    / "Strong engine agreement (100.0)" evidence text downstream).
    """
    fake_bank_data = {
        "AAPL": {"cluster_centers": [300.0, 310.0], "trained_at": "2026-08-01T00:00:00Z"},
    }
    fake_response = MagicMock()
    fake_response.data = {"data": json.dumps(fake_bank_data), "count": 1}
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = fake_response

    with patch.object(bme, "_get_supabase", return_value=fake_sb):
        with bme._bank_lock:
            bme._memory_bank.clear()
        bme.load_memory_from_supabase()

    result = bme.evaluate("AAPL", current_price=305.0, bars_5m=[])
    assert result.get("bme_regime") != "NO_MEMORY", (
        "A symbol with genuinely restored memory should not fall back "
        "to the NO_MEMORY neutral default -- if this fails, the load "
        "path isn't actually making memory usable by evaluate()."
    )


def test_missing_supabase_credentials_falls_back_gracefully():
    """
    If Supabase isn't configured (e.g. a local/test environment), this
    must return 0 and must not raise -- start_radar_scheduler() wraps
    this in its own try/except too, but the function itself should also
    degrade gracefully on its own.
    """
    with patch.object(bme, "_get_supabase", return_value=None):
        count = bme.load_memory_from_supabase()
    assert count == 0
