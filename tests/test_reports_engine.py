"""
tests/test_reports_engine.py
-------------------------------
Regression coverage for backend/reports_engine.py's "What Happened in
the Market Today" section, and the report's core structure.

WHY THIS EXISTS: on 2026-08-02, an attempt to make this section
reflect true per-date historical data (instead of the live market
snapshot at generation time) introduced a real, serious bug -- reading
directly from the in-process RADAR_CACHE dict, which is always empty
on this specific backend service (the actual scanning that populates
it runs in a separate worker service, sigmalytic-radar-scanner). That
fix, and several subsequent attempts to fix problems it caused (a
request timeout, then persistent caching confusion), never fully
resolved cleanly, and the working, simpler original approach
(get_radar_scores(), the properly Redis-bridged live cache) was
restored by explicit user decision rather than keep debugging further.

These tests exist specifically to prevent that exact regression class
from being reintroduced silently in the future: they pin down that
_fetch_market_movers() uses the correct, working data source and
function signature, and that the report's core formatting fixes
(SPARK label, centered headers, readable text) stay intact.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect
from unittest.mock import patch

from backend.reports_engine import (
    _fetch_market_movers,
    _movers_table,
    _state_label,
    _readable_label,
    _cohort_label,
    _readable_missing_components,
    build_report_html,
)


def test_fetch_market_movers_uses_get_radar_scores_not_raw_cache():
    """
    Regression guard for the exact 2026-08-02 bug: this must import and
    call get_radar_scores() (the properly Redis-bridged function),
    never the raw RADAR_CACHE dict directly -- reading RADAR_CACHE
    directly is always empty on this backend service, since the actual
    radar scanning runs in a separate worker service entirely.
    """
    source = inspect.getsource(_fetch_market_movers)
    assert "get_radar_scores" in source, (
        "_fetch_market_movers must use get_radar_scores() (Redis-bridged), "
        "not read RADAR_CACHE directly -- reading it directly is always "
        "empty on this service and was the exact root cause of the "
        "'Market movers data unavailable' bug."
    )
    assert "RADAR_CACHE" not in source, (
        "_fetch_market_movers must not import or reference the raw "
        "RADAR_CACHE dict directly -- see get_radar_scores_not_raw_cache "
        "above for why."
    )


def test_fetch_market_movers_signature_is_the_simple_working_version():
    """
    Regression guard against re-introducing the overly complex,
    ultimately-reverted per-date historical version. The working
    version takes only `limit`, not a report_date_str -- if this
    signature changes to require a date parameter again, that's a sign
    the more complex (and less reliable) historical-fetch approach is
    being reintroduced.
    """
    sig = inspect.signature(_fetch_market_movers)
    params = list(sig.parameters.keys())
    assert params == ["limit"], (
        f"_fetch_market_movers signature is {params}, expected just "
        f"['limit'] -- the simple, working live-cache version. If this "
        f"needs to change, make sure it's a deliberate decision, not a "
        f"silent reintroduction of the reverted historical-bars approach."
    )


def test_movers_table_signature_is_the_simple_working_version():
    """Same regression guard, for the table renderer's signature."""
    sig = inspect.signature(_movers_table)
    params = list(sig.parameters.keys())
    assert params == ["movers"], (
        f"_movers_table signature is {params}, expected just ['movers'] "
        f"-- the reverted version added a 'reason' parameter for "
        f"diagnostic text that should not be shown to real subscribers."
    )


def test_fetch_market_movers_returns_plain_list_not_tuple():
    """
    The reverted-to version returns a plain list. The overly-complex
    version returned (movers, reason) tuples -- if this function starts
    returning a tuple again, calling code elsewhere will silently break
    (e.g. unpacking a plain list into two variables raises immediately,
    which is at least loud -- but any code that doesn't unpack it would
    misbehave silently instead).
    """
    fake_radar_payload = {"symbols": [
        {"symbol": "TEST", "change_pct": 5.0, "price": 100.0, "rel_volume": 1.5, "volume": 1000},
    ]}
    with patch("backend.radar_service.get_radar_scores", return_value=fake_radar_payload):
        result = _fetch_market_movers(limit=15)
    assert isinstance(result, list), (
        f"_fetch_market_movers returned {type(result)}, expected a plain list."
    )


def test_fetch_market_movers_sorts_by_absolute_change_both_directions():
    """
    Confirms real, working behavior: both gains and losses are
    included and correctly sorted by magnitude -- confirmed directly
    against the actual live report output on 2026-08-02 (a healthy mix
    of positive and negative movers, correctly ordered).
    """
    fake_radar_payload = {"symbols": [
        {"symbol": "SMALL_GAIN", "change_pct": 1.0, "price": 10.0, "rel_volume": 1.0, "volume": 100},
        {"symbol": "BIG_LOSS", "change_pct": -8.0, "price": 20.0, "rel_volume": 1.0, "volume": 100},
        {"symbol": "BIG_GAIN", "change_pct": 6.0, "price": 30.0, "rel_volume": 1.0, "volume": 100},
        {"symbol": "MISSING_CHANGE", "price": 40.0, "rel_volume": 1.0, "volume": 100},
    ]}
    with patch("backend.radar_service.get_radar_scores", return_value=fake_radar_payload):
        movers = _fetch_market_movers(limit=15)

    symbols_in_order = [m["symbol"] for m in movers]
    assert symbols_in_order == ["BIG_LOSS", "BIG_GAIN", "SMALL_GAIN"], (
        f"Expected sorted by |change_pct| descending with both directions "
        f"included, got {symbols_in_order}"
    )
    assert "MISSING_CHANGE" not in symbols_in_order, (
        "Symbols with no change_pct data should be excluded, not crash or "
        "show as a fabricated zero."
    )


def test_movers_table_shows_clean_unavailable_message_not_internal_diagnostics():
    """
    Regression guard: the unavailable-state message must stay clean and
    professional. An earlier version exposed internal diagnostic text
    (e.g. 'reason: RADAR_CACHE is empty...') directly to subscribers,
    which was correctly flagged as looking like a bug/leftover debug
    output rather than production content.
    """
    html_out = _movers_table([])
    assert "unavailable for this report." in html_out
    assert "reason:" not in html_out
    assert "RADAR_CACHE" not in html_out
    assert "MOVERS_BUILD_MARKER" not in html_out


def test_report_state_label_maps_birth_to_spark():
    """
    Regression guard for the SPARK/BIRTH formatting fix -- the app's
    own UI already relabels the backend's raw 'BIRTH' lifecycle state
    as 'SPARK' everywhere; the report must match that convention.
    """
    assert _state_label("BIRTH") == "SPARK"
    assert _state_label("SURVIVING") == "SURVIVING"


def test_report_readable_label_formatting():
    assert _readable_label("PENDING_INCOMPLETE_7YR_EVIDENCE") == "Pending Incomplete 7yr Evidence"
    assert _readable_label(None) == "—"


def test_report_cohort_label_strips_redundant_prefix():
    assert _cohort_label("COHORT_READY") == "Ready"
    assert _cohort_label("COHORT_INSUFFICIENT_HISTORY") == "Insufficient History"


def test_report_missing_components_shows_zero_or_readable_list():
    assert _readable_missing_components({}) == "0"
    assert _readable_missing_components({
        "ods_missing_components": ["supply_exhaustion", "demand_support_validation"]
    }) == "Supply Exhaustion, Demand Support Validation"


def test_build_report_html_contains_core_branding_and_no_leftover_debug_artifacts():
    """
    End-to-end smoke test: the full report document must contain the
    real branding treatment, and must never contain any leftover
    diagnostic markers or internal debug text from past investigations.
    """
    fake_campaign_payload = {"rows": [], "market_data_status": {}}
    fake_radar_payload = {"symbols": [
        {"symbol": "AAPL", "change_pct": -7.2, "price": 300.68, "rel_volume": 2.33, "volume": 132490000},
    ]}
    with patch("backend.campaign_full_enrichment_api.full_universe_enriched_campaign_table", return_value=fake_campaign_payload), \
         patch("backend.radar_service.get_radar_scores", return_value=fake_radar_payload):
        html_doc = build_report_html("2026-07-31")

    assert '<span class="sigma">' in html_doc, "Real Sigma-symbol branding must be present"
    assert "table-layout: fixed" in html_doc, "Table overflow-containment CSS must be present"
    assert "-7.20%" in html_doc, "Real movers data must populate correctly"
    assert "MOVERS_BUILD_MARKER" not in html_doc, "No leftover diagnostic marker"
    assert "reason:" not in html_doc, "No leftover internal diagnostic text"
