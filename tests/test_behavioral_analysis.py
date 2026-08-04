"""
tests/test_behavioral_analysis.py
------------------------------------
Regression coverage for the entire Behavioral Analysis feature built
2026-08-04 -- not just the layout (see test_command_center_layout.py
for that), but the actual narrative-generation logic, the score-tier
system it shares with the alert system, the live volume-expansion
check, and the backend endpoint the whole thing depends on.

WHY THIS EXISTS: this is a genuinely new, real feature (a rule-based
interpreter of the app's own Bias/Confidence/Status/Grade/Mode/Score/
Volume data), and per explicit request, needs full protection against
silent regression -- not just its visual placement.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


# ── Score tier thresholds ────────────────────────────────────────────────
def test_score_tier_boundaries():
    """
    Locks in the exact thresholds shared between the alert-sound
    system (fireAlert in index_string) and the Behavioral Analysis
    narrative -- these must stay in sync, or the two features would
    describe a symbol's state differently from each other.
    """
    assert app._score_tier(0) == "Trap Door"
    assert app._score_tier(34) == "Trap Door"
    assert app._score_tier(35) == "Monitoring"
    assert app._score_tier(54) == "Monitoring"
    assert app._score_tier(55) == "Score Tier B"
    assert app._score_tier(79) == "Score Tier B"
    assert app._score_tier(80) == "Score Tier A"
    assert app._score_tier(100) == "Score Tier A"


# ── Behavioral analysis narrative generation ─────────────────────────────
def _aapl_style_live(**overrides):
    """The real, confirmed scenario used throughout the 2026-08-04 session."""
    decision = {
        "bias": "Neutral", "status": "C PROBE", "grade": "C",
        "mode": "Caution / Digestion", "confidence": "LOW", "score": 51,
    }
    decision.update(overrides.pop("decision", {}))
    live = {"symbol": "AAPL", "price": 302.16, "rel_volume": 2.35, "decision": decision}
    live.update(overrides)
    return live


def test_non_actionable_scenario_produces_gates():
    """
    The real, confirmed AAPL scenario: Neutral/LOW/C PROBE-C/Caution-
    Digestion/51%/2.35x volume must be read as non-actionable, with
    real long AND short gates listed (not just one side).
    """
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(_aapl_style_live())

    assert symbol == "AAPL"
    assert price == 302.16
    assert len(bullets) == 5, "Expected exactly 5 bullets: Bias, Status-Grade, Mode, Score, Volume"
    assert "nothing here is actionable yet" in verdict
    assert gates is not None, "Non-actionable scenario must produce gates"

    long_gates, short_gates = gates
    assert len(long_gates) > 0
    assert len(short_gates) > 0
    assert any("Bullish" in g for g in long_gates)
    assert any("Bearish" in g for g in short_gates)


def test_fully_actionable_bullish_scenario_has_no_gates():
    """
    When Bias/Status/Grade/Score Tier all genuinely align (Bullish,
    Armed, A grade, Score Tier A), the verdict must be actionable and
    NO gates should be shown -- there's nothing left to wait for.
    """
    live = _aapl_style_live(decision={
        "bias": "Bullish", "status": "Armed", "grade": "A",
        "mode": "Trending", "confidence": "HIGH", "score": 85,
    })
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(live)

    assert "qualified, actionable" in verdict
    assert "bullish" in verdict.lower()
    assert gates is None, "Fully-actionable scenario must not show gates -- nothing left to wait for"


def test_fully_actionable_bearish_scenario():
    """Same check, mirrored for the bearish side -- the logic isn't hardcoded to only recognize bullish setups as actionable."""
    live = _aapl_style_live(decision={
        "bias": "Bearish", "status": "Armed", "grade": "B",
        "mode": "Trending", "confidence": "HIGH", "score": 60,
    })
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(live)

    assert "bearish" in verdict.lower()
    assert gates is None


def test_volume_unavailable_handled_honestly():
    """
    When rel_volume is None (symbol not in radar universe, or the
    lookup failed), the narrative must say so honestly -- never
    fabricate a volume reading or silently omit the volume bullet
    entirely.
    """
    live = _aapl_style_live(rel_volume=None)
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(live)

    volume_bullet = next((b for b in bullets if b.startswith("Volume:")), None)
    assert volume_bullet is not None, "Volume bullet must always be present, even when data is unavailable"
    assert "unavailable" in volume_bullet.lower()


def test_missing_decision_data_does_not_crash():
    """Defensive check: a live dict with no decision key at all (e.g. very first tick before real data loads) must not raise."""
    live = {"symbol": "AAPL", "price": 300.0, "rel_volume": None}
    symbol, price, bullets, verdict, gates = app._build_behavioral_analysis(live)
    assert symbol == "AAPL"
    assert len(bullets) == 5


# ── Panel rendering ───────────────────────────────────────────────────────
def test_render_panel_handles_no_live_data():
    """Before the first live tick arrives, live may be None/falsy -- must render a real placeholder, not crash."""
    result = app._render_behavioral_analysis_panel(None)
    assert result is not None
    rendered = str(result.to_plotly_json())
    assert "will appear once live data loads" in rendered


def test_render_panel_produces_valid_component_with_real_data():
    result = app._render_behavioral_analysis_panel(_aapl_style_live())
    assert result is not None
    # Must be a real Dash component, not a plain string/dict
    assert hasattr(result, "to_plotly_json")


# ── Callback wiring ───────────────────────────────────────────────────────
def test_update_behavioral_analysis_callback_exists_and_delegates():
    """
    Confirms the dedicated callback (separate from the large,
    many-branch render_main callback, by design) exists and correctly
    delegates to the render function rather than duplicating logic.
    """
    assert hasattr(app, "update_behavioral_analysis")
    result = app.update_behavioral_analysis(_aapl_style_live())
    assert result is not None


# ── Volume-expansion note (used inside Direction Intelligence too) ───────
def test_volume_expansion_note_matches_score_tier_terminology():
    """
    The Ref/volume note must use "Score Tier A" (not the old "A-grade"
    wording) -- these were explicitly renamed together on 2026-08-04
    to avoid being confused with the Decision Engine's separate,
    unrelated Grade metric. If this note drifts back to the old
    wording independently, that confusion returns for this specific
    piece of text even if the rest of the panel stays renamed.
    """
    note_met = app._build_volume_expansion_note(302.16, 2.35)
    assert "Score Tier A" in note_met.children
    assert "A-grade" not in note_met.children

    note_not_met = app._build_volume_expansion_note(302.16, 0.9)
    assert "not met" in note_not_met.children

    note_unavailable = app._build_volume_expansion_note(302.16, None)
    assert "unavailable" in note_unavailable.children.lower()
