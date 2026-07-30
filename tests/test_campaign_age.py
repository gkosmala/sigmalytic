"""
tests/test_campaign_age.py
----------------------------
Regression coverage for status_center.py's _campaign_age_days().

WHY THIS EXISTS: campaign_age_days/duration_days are set to 0 exactly
once, at campaign creation (campaign_discovery_engine.py), and never
updated again anywhere in the backend -- confirmed by direct search.
Every campaign, regardless of true age, was frozen at "0 days old"
forever, which caused the Yellow Alert banner to incorrectly show all
280 active campaigns as "new in the last 3 days". Fixed by computing
the real age from birth_date (set once, and correct forever without
needing to be touched again) instead. These tests pin down that the
birth_date path is used whenever available, and that the old frozen
counters are only a fallback for records that somehow lack birth_date.
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

from status_center import _campaign_age_days


def test_uses_birth_date_when_present_not_the_frozen_counter():
    """
    The exact real-world case that exposed the bug: a campaign whose
    birth_date is weeks in the past, but whose campaign_age_days /
    duration_days fields are both still 0 (frozen at creation).
    """
    campaign = {
        "birth_date": (date.today() - timedelta(days=29)).isoformat(),
        "campaign_age_days": 0,
        "duration_days": 0,
    }
    assert _campaign_age_days(campaign) == 29


def test_falls_back_to_frozen_counters_when_birth_date_missing():
    campaign = {"campaign_age_days": 5}
    assert _campaign_age_days(campaign) == 5


def test_falls_back_to_duration_days_when_both_birth_date_and_age_missing():
    campaign = {"duration_days": 12}
    assert _campaign_age_days(campaign) == 12


def test_genuinely_new_campaign_reads_zero():
    campaign = {"birth_date": date.today().isoformat()}
    assert _campaign_age_days(campaign) == 0


def test_malformed_birth_date_falls_back_gracefully_not_a_crash():
    campaign = {"birth_date": "not-a-real-date", "campaign_age_days": 7}
    assert _campaign_age_days(campaign) == 7


def test_default_when_nothing_available():
    assert _campaign_age_days({}, default=99) == 99
