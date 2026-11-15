"""Sigmalytic Quantum, frontend: every path of the spoken-question callback returns a result for the browser's
state machine (so hands-free can never be left waiting), and the panel carries its timing settings."""
import json

import pytest

app_mod = pytest.importorskip("frontend.app")


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self.ok, self._p = status, 200 <= status < 300, payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p


REC = {"audio": "data:audio/webm;base64,AAAA", "mime": "audio/webm", "duration_ms": 2000, "token": 5}


def run(monkeypatch, resp=None, exc=None, voice_on=("y",)):
    def post(*a, **k):
        if exc:
            raise exc
        return resp
    monkeypatch.setattr(app_mod.req, "post", post)
    return app_mod.handle_voice_question(REC, [], list(voice_on), {"token": "t"}, None)


def test_audio_answer(monkeypatch):
    hist, res = run(monkeypatch, Resp(payload={"ok": True, "heard": "Where is SPY?", "answer": "A.",
                                               "audio": "data:audio/mpeg;base64,QQ==", "token": 5}))
    assert res["outcome"] == "audio" and res["token"] == 5 and res["audio"].startswith("data:audio/mpeg")
    assert hist[0] == {"role": "user", "content": "Where is SPY?", "voice": True} and hist[1]["role"] == "assistant"


def test_audio_failed_is_text_only(monkeypatch):
    hist, res = run(monkeypatch, Resp(payload={"ok": True, "heard": "q", "answer": "A.", "voice_error": "TTS down"}))
    assert res["outcome"] == "text_only" and "TTS down" in res["message"] and hist[1]["content"] == "A."


def test_read_aloud_off_is_text_only_without_warning(monkeypatch):
    _, res = run(monkeypatch, Resp(payload={"ok": True, "heard": "q", "answer": "A."}), voice_on=())
    assert res["outcome"] == "text_only" and res["message"] == ""


def test_withheld_answer_is_error_result(monkeypatch):
    hist, res = run(monkeypatch, Resp(payload={"ok": False, "heard": "q", "error": "withheld"}))
    assert res["outcome"] == "error" and hist[-1]["role"] == "error"


def test_nothing_heard(monkeypatch):
    hist, res = run(monkeypatch, Resp(payload={"ok": False, "stage": "listen", "error": "No speech was heard."}))
    assert res["outcome"] == "no_speech" and hist is app_mod.no_update


def test_http_error_and_network_failure(monkeypatch):
    _, res = run(monkeypatch, Resp(status=502, payload={}))
    assert res["outcome"] == "error" and "502" in res["message"]
    _, res = run(monkeypatch, exc=TimeoutError("timed out"))
    assert res["outcome"] == "error" and res["token"] == 5


def test_unexpected_reply_still_returns_result(monkeypatch):
    class Bad(Resp):
        def json(self):
            raise ValueError("not json")
    _, res = run(monkeypatch, Bad())
    assert res["outcome"] == "error" and res["token"] == 5


def test_panel_has_states_controls_and_settings():
    panel = app_mod._quantum_voice_panel()
    flat = json.dumps(panel.to_plotly_json(), default=str)
    for needed in ("assistant-voice-state", "assistant-voice-stop", "assistant-mic-reconnect",
                   "assistant-voice-handsfree", "data-resume-ms", "data-max-errors", "AI-generated voice",
                   "SIGMALYTIC QUANTUM"):
        assert needed in flat


def test_security_policy_allows_voice_audio():
    """Without media-src, audio falls back to default-src 'self' and Chrome rejects blob:/data: audio
    ("Media load rejected by URL safety check"), so spoken answers could never play."""
    resp = app_mod.server.test_client().get("/_dash-layout")
    csp = resp.headers.get("Content-Security-Policy", "")
    media = next((d for d in csp.split(";") if d.strip().startswith("media-src")), "")
    assert "blob:" in media and "data:" in media and "'self'" in media
