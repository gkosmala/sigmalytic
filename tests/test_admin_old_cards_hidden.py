"""The nine campaign / old-engine cards are no longer placed on the Admin tab (code kept)."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
HIDDEN = ["symbol_backtest_block", "portfolio_rankings_block", "decay_monitor_block", "closure_engine_block",
          "state_transition_block", "campaign_outcome_block", "bme_memory_status_block",
          "operator_footprint_block", "enriched_campaign_table_block", "grade_grid", "score_table"]
KEPT = ["setup_deployment_block", "journal_correction_block", "subscriber_alerts_block"]


def _src():
    return open(os.path.join(ROOT, "frontend", "app.py"), encoding="utf-8").read()


def test_hidden_cards_are_not_in_either_admin_layout():
    s = _src()
    for name in HIDDEN:
        assert not re.search(r"^[ ]+" + name + r",\n", s, re.M), name


def test_kept_cards_are_in_both_admin_layouts():
    s = _src()
    for name in KEPT:
        assert len(re.findall(r"^[ ]+" + name + r",\n", s, re.M)) == 2, name
