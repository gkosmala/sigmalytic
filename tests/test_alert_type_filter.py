"""Alert emails go only to users who switched that alert type on. Default is nothing."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import email_service as es

TS = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # Wednesday, market hours
ALERT = {"symbol": "X", "alert_type": "ab_score", "score": 0, "weis_state": True, "timestamp": TS}


def wants(types, alert=ALERT):
    return es.user_wants_alert({"alert_types": types, "market_hours_only": False}, alert)


def test_on_is_sent_and_off_is_not():
    assert wants({"ab_score": True}) is True
    assert wants({"ab_score": False}) is False


def test_other_type_on_does_not_send_this_type():
    assert wants({"gann": True}) is False


def test_nothing_saved_or_everything_off_sends_nothing():
    assert wants(None) is False and wants({}) is False and wants([]) is False
    assert wants({"wyckoff": False, "gann": False, "ab_score": False, "elliott": False, "fibonacci": False}) is False


def test_older_list_format_still_works():
    assert wants(["ab_score"]) is True and wants(["gann"]) is False


def test_daily_report_flag_is_not_an_alert_type():
    assert wants({"daily_report_email": True}) is False
    assert es.enabled_alert_types({"daily_report_email": True, "gann": True}) == {"gann"}


def test_missing_prefs_key_sends_nothing():
    assert es.user_wants_alert({"market_hours_only": False}, ALERT) is False
