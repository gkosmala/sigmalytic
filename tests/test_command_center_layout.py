"""
tests/test_command_center_layout.py
--------------------------------------
Regression coverage for Command Center's Plan Trade / Behavioral
Analysis layout.

WHY THIS EXISTS: getting these two tiles to visually align (same
width, matching bottom edges) took several real attempts on
2026-08-04 -- flexbox stretch alone didn't reliably work across two
separate tries, and the final, working fix was an explicit, identical
fixed height (640px) on both, plus equal flex:1 ratios for the width
split. This test locks in those exact values directly, so a future
change to either side (e.g. someone adjusting Plan Trade's height
without noticing Behavioral Analysis needs the identical change) fails
loudly here instead of silently reintroducing the misalignment.
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


def _read_app_source() -> str:
    app_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        return f.read()


def test_behavioral_analysis_card_has_fixed_height():
    """
    The card returned by _render_behavioral_analysis_panel() must have
    an explicit, fixed height -- the working fix after flexbox stretch
    proved unreliable. If this regresses to a stretch/percentage-based
    approach again without also fixing Plan Trade to match, the two
    tiles' bottoms will misalign again exactly as before.
    """
    fake_live = {
        "symbol": "AAPL", "price": 302.16, "rel_volume": 2.35,
        "decision": {"bias": "Neutral", "status": "C PROBE", "grade": "C",
                     "mode": "Caution / Digestion", "confidence": "LOW", "score": 51},
    }
    result = app._render_behavioral_analysis_panel(fake_live)
    height = result.style.get("height")
    assert height is not None, "Behavioral Analysis card must have an explicit height set"
    assert height.endswith("px"), (
        f"Behavioral Analysis card height is {height!r} -- must be a fixed pixel value, "
        f"not a percentage or flex-based value (those proved unreliable for matching "
        f"Plan Trade's bottom edge across two real attempts on 2026-08-04)."
    )


def test_plan_trade_and_behavioral_analysis_heights_match_exactly():
    """
    Locks in the actual, real values: Plan Trade's card style (hardcoded
    directly in the layout, not a separate callable function) and
    Behavioral Analysis's card height must be byte-for-byte identical.
    Reads Plan Trade's height directly from source, since it isn't
    behind its own function the way Behavioral Analysis is.
    """
    source = _read_app_source()

    # Find Plan Trade's outer card style block (identified by its
    # unique combination of properties in the layout).
    plan_trade_match = re.search(
        r'\], style=\{"flex":"1","minWidth":"0","height":"(\d+px)","overflowY":"auto",\s*'
        r'"background":NAVY_CARD',
        source,
    )
    assert plan_trade_match is not None, (
        "Could not find Plan Trade's height in the expected layout location -- "
        "if the surrounding style structure changed, update this test's search "
        "pattern to match, but don't just delete this check."
    )
    plan_trade_height = plan_trade_match.group(1)

    fake_live = {
        "symbol": "AAPL", "price": 302.16, "rel_volume": 2.35,
        "decision": {"bias": "Neutral", "status": "C PROBE", "grade": "C",
                     "mode": "Caution / Digestion", "confidence": "LOW", "score": 51},
    }
    result = app._render_behavioral_analysis_panel(fake_live)
    behavioral_height = result.style.get("height")

    assert plan_trade_height == behavioral_height, (
        f"Plan Trade height ({plan_trade_height}) and Behavioral Analysis height "
        f"({behavioral_height}) no longer match -- this is the exact regression "
        f"that caused the bottoms to misalign visually. If you're intentionally "
        f"changing one, change the other to match, and update this test's expected "
        f"value too."
    )


def test_plan_trade_and_behavioral_analysis_equal_width_flex():
    """
    Both tiles must share equal flex:1 ratios for a true 50/50 width
    split (matching Time Engine + Visual/Audio Alerts above them) --
    confirmed this can only be exact when Active Trade Panel is NOT a
    third sibling sharing the same row (see the 2026-08-04 restructuring
    that moved it to its own separate row below).
    """
    source = _read_app_source()

    assert 'id="behavioral-analysis-panel", style={"flex":"1"' in source, (
        "Behavioral Analysis panel's flex ratio changed -- must stay flex:1 "
        "to match Plan Trade for an exact 50/50 width split."
    )
    assert '], style={"flex":"1","minWidth":"0","height":' in source, (
        "Plan Trade's flex ratio changed -- must stay flex:1 to match "
        "Behavioral Analysis for an exact 50/50 width split."
    )


def test_active_trade_panel_is_not_in_the_same_row():
    """
    Active Trade Panel must stay in its own separate row, not sharing
    trade-panels-row with Plan Trade/Behavioral Analysis -- confirmed
    during the 2026-08-04 restructuring that with 3 siblings sharing
    one row, no combination of flex ratios could give Plan Trade and
    Behavioral Analysis a true 50/50 split while Active Trade Panel
    (typically empty) still took up real space.
    """
    source = _read_app_source()

    trade_panels_row_start = source.index('id="trade-panels-row"')
    # Back up to find the start of this html.Div's children list
    row_block_start = source.rfind("html.Div([", 0, trade_panels_row_start)
    row_block = source[row_block_start:trade_panels_row_start]

    assert 'id="active-trade-panel"' not in row_block, (
        "Active Trade Panel appears to be back inside trade-panels-row -- "
        "this breaks the exact 50/50 split between Plan Trade and "
        "Behavioral Analysis. It must stay in its own separate row below."
    )
