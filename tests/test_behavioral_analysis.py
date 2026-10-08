"""
tests/test_behavioral_analysis.py
------------------------------------
Behavioral Analysis panel: a plain reading of the Weis setup state (the Radar
Status engine) for the loaded symbol. The older Bias / Status - Grade / Mode /
Engine Score / Score Tier reading is gone. Layout is covered in
test_command_center_layout.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


def _live(state="Watching", direction="long", **ws_over):
    ws = {"state": state, "direction": direction, "reason": "broke support, not closed back",
          "stop": 40.1, "target": 52.5, "bar_count": 289, "source": "radar scan"}
    ws.update(ws_over)
    return {"symbol": "GXO", "price": 45.99, "rel_volume": 1.2, "weis_state": ws,
            "decision": {"bias": "Neutral", "status": "C PROBE", "grade": "C", "score": 51}}


def test_armed_is_actionable_and_has_no_gates():
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(_live("Armed"))
    assert symbol == "GXO" and price == 45.99
    assert "Armed long (spring)" in verdict and "$40.10" in verdict and "$52.50" in verdict
    assert gates is None
    assert bullets[0].startswith("Weis setup state: ARMED")


def test_each_non_armed_state_gets_gates_on_both_sides():
    for st in ("Setting Up", "Watching", "Avoid", "No setup"):
        _, _, _, verdict, gates = app._build_behavioral_analysis(_live(st, None if st == "No setup" else "long"))
        assert gates is not None and gates[0] and gates[1], st
        assert verdict


def test_avoid_gives_the_reason_and_no_trade():
    _, _, _, verdict, _ = app._build_behavioral_analysis(
        _live("Avoid", reason="against the longer-term trend"))
    assert "against the longer-term trend" in verdict and "No trade" in verdict


def test_no_target_is_stated_not_invented():
    _, _, bullets, _, _ = app._build_behavioral_analysis(_live("Armed", target=None))
    assert any("none defined" in b for b in bullets)


def test_old_score_language_is_gone():
    _, _, bullets, verdict, gates = app._build_behavioral_analysis(_live("Watching"))
    text = " ".join(bullets) + verdict + " ".join(sum((list(g) for g in gates), []))
    for old in ("Score Tier", "Engine Score", "Trap Door", "Bias:", "Grade", "Decision Engine", "Confidence"):
        assert old not in text, old


def test_volume_is_a_plain_fact_or_unavailable():
    _, _, b1, _, _ = app._build_behavioral_analysis(_live("Watching"))
    assert any(b == "Volume: 1.20x the average." for b in b1)
    live = _live("Watching")
    live["rel_volume"] = None
    _, _, b2, _, _ = app._build_behavioral_analysis(live)
    assert any("unavailable" in b for b in b2)


def test_state_still_loading_does_not_crash():
    live = {"symbol": "AAPL", "price": 300.0, "rel_volume": None}
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(live)
    assert symbol == "AAPL" and "loading" in verdict.lower() and gates is None


# ── Panel rendering ───────────────────────────────────────────────────────
def test_render_panel_handles_no_live_data():
    result = app._render_behavioral_analysis_panel(None)
    assert "will appear once live data loads" in str(result.to_plotly_json())


def test_render_panel_produces_valid_component_with_real_data():
    result = app._render_behavioral_analysis_panel(_live("Setting Up"))
    assert hasattr(result, "to_plotly_json")


def test_update_behavioral_analysis_callback_exists_and_delegates():
    assert hasattr(app, "update_behavioral_analysis")
    assert app.update_behavioral_analysis(_live("Armed")) is not None


def test_volume_expansion_note_still_works():
    note_met = app._build_volume_expansion_note(302.16, 2.35)
    assert "Score Tier A" in note_met.children
    assert "not met" in app._build_volume_expansion_note(302.16, 0.9).children
    assert "unavailable" in app._build_volume_expansion_note(302.16, None).children.lower()
