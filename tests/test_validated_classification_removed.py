import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SRC = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "app.py"), encoding="utf-8").read()


def test_old_validated_research_classification_is_gone_from_the_command_center():
    assert "Validated Research Classification" not in SRC
    assert "validated-classification" not in SRC
    assert "validated_classification" not in SRC


def test_old_wyckoff_verdict_is_gone_from_the_command_center_card():
    assert 'slabel("Wyckoff Verdict")' not in SRC
    assert 'live.get("wyckoff_verdict")' not in SRC
    assert "{clean}/wyckoff-verdict" not in SRC
