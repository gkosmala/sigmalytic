"""The Command Center chart is served from a short URL, not re-sent inside every update."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


def test_same_chart_gives_the_same_url():
    html_doc = "<html>" + "x" * 5000 + "</html>"
    assert app._cc_chart_url(html_doc) == app._cc_chart_url(html_doc)


def test_changed_chart_gives_a_new_url():
    assert app._cc_chart_url("<html>a</html>") != app._cc_chart_url("<html>b</html>")


def test_url_is_short_and_serves_the_exact_document():
    doc = "<html><body>" + "y" * 200000 + "</body></html>"
    url = app._cc_chart_url(doc)
    assert len(url) < 60
    r = app.server.test_client().get(url)
    assert r.status_code == 200
    assert r.get_data(as_text=True) == doc
    assert r.mimetype == "text/html"


def test_unknown_token_is_404():
    assert app.server.test_client().get("/cc-chart/doesnotexist").status_code == 404


def test_registry_is_bounded():
    for i in range(app._CC_CHART_BY_TOKEN_MAX + 20):
        app._cc_chart_url(f"<html>{i}</html>")
    assert len(app._CC_CHART_BY_TOKEN) <= app._CC_CHART_BY_TOKEN_MAX
