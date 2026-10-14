"""The Admin tab is for the administrator only: hidden for guests/subscribers and never built for them."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
os.environ["SIGMALYTIC_ADMIN_EMAILS"] = "owner@example.com"
import app as dash_app  # noqa: E402


def _admin_style(session):
    out = dash_app.sync_active_tab_styles("home", session)
    keys = [k for k, _ in dash_app.ALL_TABS]
    return out[keys.index("admin")]


def test_admin_button_hidden_for_guest_and_subscriber():
    assert _admin_style(None).get("display") == "none"
    assert _admin_style({"email": "sub@example.com"}).get("display") == "none"


def test_admin_button_shown_for_admin():
    assert _admin_style({"email": "OWNER@example.com"}).get("display") != "none"


def test_other_tabs_stay_visible_for_guest():
    out = dash_app.sync_active_tab_styles("home", None)
    keys = [k for k, _ in dash_app.ALL_TABS]
    assert all(out[i].get("display") != "none" for i, k in enumerate(keys) if k != "admin")


def test_admin_page_denied_for_non_admin():
    html_str = str(dash_app.build_admin_tab(session={"email": "sub@example.com"}, backend_url="http://x"))
    assert "Admin Access Only" in html_str
