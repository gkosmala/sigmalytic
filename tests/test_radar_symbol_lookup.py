"""
tests/test_radar_symbol_lookup.py
------------------------------------
Regression coverage for backend/main.py's /api/radar/symbol/{symbol}
endpoint -- the real-data source powering Command Center's live
volume-expansion check and, by extension, the Behavioral Analysis
narrative built on top of it.

WHY THIS EXISTS: the first version of this endpoint had a real,
confirmed bug -- it called get_radar_scores(limit=1500), not knowing
that function silently hard-caps its limit to 250 internally (a
deliberate performance safeguard for its own paginated view). A real,
tracked symbol (confirmed: AAPL, out of a genuine 915-symbol universe)
could come back "not found" simply because it wasn't in whatever
250-symbol slice happened to be active at that moment. The fix was a
direct dictionary lookup against the raw cache instead. This test
locks in that specific approach so it can't silently regress back to
the capped-list-search pattern.
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import radar_symbol_lookup


def test_finds_symbol_in_a_large_cache_regardless_of_position():
    """
    The exact regression class this endpoint was fixed for: a symbol
    that would NOT be in an arbitrary top-250 slice of a large cache
    must still be found, since this must be a direct key lookup, not
    a capped/sorted list search.
    """
    fake_cache = {f"SYM{i}": {"symbol": f"SYM{i}", "rel_volume": 1.0} for i in range(900)}
    fake_cache["AAPL"] = {"symbol": "AAPL", "rel_volume": 2.35, "price": 302.16}

    with patch("backend.radar_service.RADAR_CACHE", fake_cache):
        result = radar_symbol_lookup("AAPL")

    assert result["ok"] is True
    assert result["symbol"] == "AAPL"
    assert result["data"]["rel_volume"] == 2.35


def test_does_not_use_get_radar_scores():
    """
    Locks in the actual fix, not just its observable behavior: this
    function's real code (not its docstring, which legitimately
    explains the bug history) must not call get_radar_scores(), since
    that function's internal 250-item cap is exactly what caused the
    original bug. A future edit that reintroduces that call, even if
    it happens to pass the tests above with small test fixtures, would
    reintroduce the real, production-scale bug.
    """
    import inspect
    source = inspect.getsource(radar_symbol_lookup)
    # Strip the docstring (everything between the first pair of triple
    # quotes) before checking -- it legitimately mentions
    # get_radar_scores() as historical documentation of the bug, which
    # would otherwise cause a false failure on a simple substring check.
    if '"""' in source:
        first = source.index('"""')
        second = source.index('"""', first + 3)
        source = source[:first] + source[second + 3:]

    assert "get_radar_scores(" not in source, (
        "radar_symbol_lookup's real code (outside its docstring) must not call "
        "get_radar_scores() -- that function hard-caps its limit to 250 internally, "
        "which was the exact root cause of a real symbol (AAPL) incorrectly coming "
        "back as 'not found'."
    )


def test_symbol_not_in_cache_returns_honest_error():
    fake_cache = {"AAPL": {"symbol": "AAPL", "rel_volume": 2.35}}
    with patch("backend.radar_service.RADAR_CACHE", fake_cache), \
         patch("backend.radar_service._redis_client", None):
        result = radar_symbol_lookup("ZZZZ")

    assert result["ok"] is False
    assert result["error"] == "symbol_not_in_radar_universe"


def test_missing_symbol_param_handled():
    result = radar_symbol_lookup("")
    assert result["ok"] is False
    assert result["error"] == "missing_symbol"


def test_symbol_is_case_and_whitespace_normalized():
    fake_cache = {"AAPL": {"symbol": "AAPL", "rel_volume": 2.35}}
    with patch("backend.radar_service.RADAR_CACHE", fake_cache):
        result = radar_symbol_lookup("  aapl  ")

    assert result["ok"] is True
    assert result["symbol"] == "AAPL"
