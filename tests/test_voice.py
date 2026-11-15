"""Sigmalytic Quantum voice: spoken text, chunking, speech-to-text and text-to-speech calls, the daily cap, the
ask flow and admin-only routes. OpenAI and the assistant are faked; no network."""
import base64
import json

import pytest

from backend import voice as v


MP3 = b"\xff\xfb\x90\x00"          # an MP3 frame header: what OpenAI's speech endpoint returns


class FakeResp:
    def __init__(self, status=200, payload=None, content=MP3 + b""):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload or {}
        self.content = content
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(v, "_redis", lambda: None)
    v._LOCAL_SPEND.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for k in ("VOICE_STT_MODEL", "VOICE_TTS_MODEL", "VOICE_TTS_VOICE", "VOICE_STYLE", "VOICE_MAX_SPOKEN_WORDS",
              "VOICE_DAILY_LIMIT_USD"):
        monkeypatch.delenv(k, raising=False)


def _audio_url(n=4000):
    return "data:audio/webm;codecs=opus;base64," + base64.b64encode(b"\x1a" * n).decode()


# ── spoken text ──

def test_spoken_text_strips_markdown_tables_links_and_research():
    answer = ("### Summary\n**NVDA** broke down below $180.40 two sessions ago.\n\n"
              "| Symbol | Price |\n|---|---|\n| NVDA | 171.25 |\n\n"
              "- AMD is above $236.50, see [the report](https://example.com/r).\n\n"
              "### Research context\nAnalysts at a bank said 99 things.\n")
    s = v.spoken_text(answer)
    assert s.startswith("Summary.") or s.startswith("Summary")
    assert "NVDA broke down below $180.40 two sessions ago." in s
    assert "The table is on screen." in s and "171.25" not in s
    assert "AMD is above $236.50, see the report." in s
    assert "http" not in s and "*" not in s and "#" not in s and "|" not in s
    assert "Analysts" not in s and "99" not in s          # the research section is never spoken


def test_spoken_text_cuts_at_sentence_and_says_so():
    answer = " ".join(f"Sentence number {i} has exactly seven words." for i in range(1, 40))
    s = v.spoken_text(answer, max_words=30)
    assert s.endswith("The full answer is on screen.")
    assert len(s.split()) <= 30 + 7
    assert "Sentence number 4 has" in s and "Sentence number 6 has" not in s


def test_spoken_text_numbers_all_come_from_the_answer():
    answer = "SPY closed at $612.40, up 1.2%. QQQ held $540.10. RSI on IWM is 41."
    nums = set(__import__("re").findall(r"\d+(?:\.\d+)?", v.spoken_text(answer)))
    assert nums <= set(__import__("re").findall(r"\d+(?:\.\d+)?", answer))


def test_chunk_text_respects_limit_and_keeps_everything():
    text = " ".join(f"This is sentence {i} of the morning report." for i in range(600))
    chunks = v.chunk_text(text, size=500)
    assert all(len(c) <= 500 for c in chunks) and len(chunks) > 5
    assert " ".join(chunks) == text
    long_word_run = "word " * 400
    assert all(len(c) <= 300 for c in v.chunk_text(long_word_run, size=300))


# ── speech-to-text ──

def test_transcribe_sends_audio_and_returns_text(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        seen.update(url=url, files=files, data=data, auth=headers["Authorization"])
        return FakeResp(payload={"text": "What is the market risk regime today?"})

    monkeypatch.setattr("requests.post", fake_post)
    out = v.transcribe(_audio_url(), duration_ms=4000)
    assert out["ok"] and out["text"] == "What is the market risk regime today?"
    assert seen["url"] == v.STT_URL and seen["data"]["model"] == "gpt-transcribe"
    name, raw, mime = seen["files"]["file"]
    assert name == "question.webm" and mime == "audio/webm" and raw == b"\x1a" * 4000
    assert seen["auth"] == "Bearer test-key"
    assert v.spent_today() > 0


def test_transcribe_refuses_without_key_and_oversized(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert "OPENAI_API_KEY" in v.transcribe(_audio_url())["error"]
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert "60 seconds" in v.transcribe(_audio_url(v.MAX_AUDIO_BYTES + 10))["error"]


def test_transcribe_empty_speech(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(payload={"text": "  "}))
    assert "No speech" in v.transcribe(_audio_url())["error"]


# ── text-to-speech ──

def test_synthesize_chunks_joins_and_steers_style(monkeypatch):
    bodies = []

    def fake_post(url, headers=None, data=None, timeout=None):
        bodies.append(json.loads(data))
        return FakeResp(content=MP3 + str(len(bodies)).encode())

    monkeypatch.setattr("requests.post", fake_post)
    text = " ".join(f"Line {i} of a long report." for i in range(800))
    out = v.synthesize(text)
    assert out["ok"] and out["mime"] == "audio/mpeg"
    assert len(bodies) > 1 and all(len(b["input"]) <= v.TTS_CHUNK_CHARS for b in bodies)
    assert out["audio"] == b"".join(MP3 + str(i).encode() for i in range(1, len(bodies) + 1))
    b = bodies[0]
    assert b["model"] == "gpt-4o-mini-tts" and b["voice"] == "onyx" and b["response_format"] == "mp3"
    assert "British" in b["instructions"] and "celebrity" in b["instructions"]


def test_synthesize_uses_cache(monkeypatch):
    store = {}

    class R:
        def get(self, k):
            return store.get(k)

        def setex(self, k, ttl, val):
            store[k] = val

        def incrbyfloat(self, k, n):
            store[k] = float(store.get(k) or 0) + n

        def expire(self, k, t):
            pass

    monkeypatch.setattr(v, "_redis", lambda: R())
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(1) or FakeResp(content=MP3 + b"AUDIO"))
    first = v.synthesize("Good morning. Markets are calm.")
    second = v.synthesize("Good morning. Markets are calm.")
    assert first["ok"] and second["ok"] and second["cached"] and second["audio"] == MP3 + b"AUDIO"
    assert len(calls) == 1


def test_daily_cap_blocks(monkeypatch):
    monkeypatch.setenv("VOICE_DAILY_LIMIT_USD", "0")
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("no call past the cap"))
    out = v.synthesize("Hello there.")
    assert not out["ok"] and "voice limit" in out["error"]


def test_speak_answer_mode_shortens(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(content=MP3 + b"A"))
    out = v.speak("**Bold** claim at $10.", mode="answer")
    assert out["ok"] and out["spoken"] == "Bold claim at $10." and out["audio"].startswith("data:audio/mpeg;base64,")
    assert out["notice"] == "AI-generated voice"


# ── ask flow ──

def test_ask_transcribes_asks_assistant_and_speaks(monkeypatch):
    from backend import assistant

    asked = {}

    def fake_ask(q, history=None, admin="", attachment=None):
        asked.update(q=q, history=history, admin=admin)
        return {"ok": True, "answer": "### Answer\nSPY is above $600.00.", "disclaimer": "d", "lookups": ["scan"]}

    def fake_post(url, **kw):
        if url == v.STT_URL:
            return FakeResp(payload={"text": "Where is SPY?"})
        return FakeResp(content=MP3 + b"VOICE")

    monkeypatch.setattr(assistant, "ask", fake_ask)
    monkeypatch.setattr("requests.post", fake_post)
    out = v.ask({"audio": _audio_url(), "duration_ms": 3000, "history": [{"role": "user", "content": "hi"}]},
                admin="greg")
    assert out["ok"] and out["heard"] == "Where is SPY?" and asked["q"] == "Where is SPY?"
    assert asked["admin"] == "greg" and asked["history"] == [{"role": "user", "content": "hi"}]
    assert out["spoken"] == "Answer. SPY is above $600.00." and out["audio"].startswith("data:audio/mpeg")
    assert out["answer"].startswith("### Answer")              # the written answer is unchanged


def test_ask_keeps_answer_when_speech_fails(monkeypatch):
    from backend import assistant

    monkeypatch.setattr(assistant, "ask", lambda *a, **k: {"ok": True, "answer": "Fine."})
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(status=500, payload={"error": {"message": "x"}}))
    out = v.ask({"question": "typed"})
    assert out["ok"] and out["answer"] == "Fine." and "Text-to-speech failed" in out["voice_error"]


def test_ask_withheld_answer_is_never_spoken(monkeypatch):
    from backend import assistant

    monkeypatch.setattr(assistant, "ask", lambda *a, **k: {"ok": False, "withheld": True, "error": "withheld"})
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("nothing is spoken"))
    out = v.ask({"question": "q"})
    assert not out["ok"] and "audio" not in out


def test_ask_listen_failure_reports_stage(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(payload={"text": ""}))
    out = v.ask({"audio": _audio_url()})
    assert not out["ok"] and out["stage"] == "listen"


def test_morning_report_needs_text():
    assert not v.morning_report("")["ok"]


# ── routes ──

def test_main_voice_routes_use_require_admin():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "backend", "main.py")).read()
    for route in ('@app.get("/api/admin/voice/status")', '@app.post("/api/admin/voice/ask")',
                  '@app.post("/api/admin/voice/speak")', '@app.post("/api/admin/voice/morning-report")'):
        block = src.split(route, 1)[1].split("\n@app.", 1)[0]
        assert "Depends(require_admin)" in block


# ── recovery rules ──

@pytest.fixture
def fresh_health(monkeypatch):
    monkeypatch.setitem(v._TTS_HEALTH, "fails", 0)
    monkeypatch.setitem(v._TTS_HEALTH, "retry_off_until", 0.0)


def _fake_assistant(monkeypatch, answer="SPY is above $600.00."):
    from backend import assistant
    monkeypatch.setattr(assistant, "ask", lambda *a, **k: {"ok": True, "answer": answer})


def test_audio_retried_once_then_succeeds(monkeypatch, fresh_health):
    _fake_assistant(monkeypatch)
    calls = []

    def flaky(url, **kw):
        calls.append(url)
        return FakeResp(status=500, payload={"error": {"message": "busy"}}) if len(calls) == 1 else FakeResp(content=MP3 + b"OK")

    monkeypatch.setattr("requests.post", flaky)
    out = v.ask({"question": "q", "token": 7})
    assert out["ok"] and out["audio_retried"] and out["audio"].startswith("data:audio/mpeg")
    assert len(calls) == 2 and out["token"] == 7


def test_audio_fails_twice_text_still_returned(monkeypatch, fresh_health):
    _fake_assistant(monkeypatch)
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(1) or FakeResp(status=503, payload={}))
    out = v.ask({"question": "q"})
    assert out["ok"] and out["answer"] and "audio" not in out and out["voice_error"]
    assert len(calls) == 2                                   # one try plus at most one retry


def test_retries_pause_after_repeated_failures(monkeypatch, fresh_health):
    _fake_assistant(monkeypatch)
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(1) or FakeResp(status=503, payload={}))
    v.ask({"question": "q1"})                                 # 2 failures
    v.ask({"question": "q2"})                                 # 3rd failure starts the cooldown, 4th is not tried
    assert not v.retry_allowed()
    n = len(calls)
    out = v.ask({"question": "q3"})
    assert out["audio_retry_skipped"] and len(calls) == n + 1   # one attempt, no retry while cooling down


def test_no_retry_when_voice_limit_reached(monkeypatch, fresh_health):
    _fake_assistant(monkeypatch)
    monkeypatch.setenv("VOICE_DAILY_LIMIT_USD", "0")
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("no call past the cap"))
    out = v.ask({"question": "q"})
    assert out["ok"] and "voice limit" in out["voice_error"] and "audio_retried" not in out


def test_read_aloud_off_skips_speech_entirely(monkeypatch, fresh_health):
    _fake_assistant(monkeypatch)
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("no speech when read-aloud is off"))
    out = v.ask({"question": "q", "speak": False, "token": 3})
    assert out["ok"] and "audio" not in out and "voice_error" not in out and out["token"] == 3


def test_assistant_prompt_forbids_unconfirmed_live_claims():
    from backend import assistant
    p = assistant.build_system_prompt()
    assert "Never call data live, real-time or up to the minute unless" in p


# ── audio format checks ──

def test_not_audio_is_reported_not_played(monkeypatch):
    class R(FakeResp):
        headers = {"Content-Type": "application/json"}
    monkeypatch.setattr("requests.post", lambda *a, **k: R(content=b'{"error": "odd"}'))
    out = v.synthesize("Hello there.")
    assert not out["ok"] and "not audio" in out["error"] and "application/json" in out["error"]


def test_sniff_formats_and_mime():
    assert v.sniff_audio(b"ID3\x04" + b"\x00" * 10) == "audio/mpeg"
    assert v.sniff_audio(b"\xff\xf3\x00\x00") == "audio/mpeg"
    assert v.sniff_audio(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "audio/wav"
    assert v.sniff_audio(b"OggS\x00") == "audio/ogg"
    assert v.sniff_audio(b"\x00\x00\x00\x18ftypM4A ") == "audio/mp4"
    assert v.sniff_audio(b'{"error":1}') is None and v.sniff_audio(b"") is None


def test_wav_reply_gets_wav_mime(monkeypatch):
    wav = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 20
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp(content=wav))
    out = v.speak("Hello.", mode="text")
    assert out["ok"] and out["audio"].startswith("data:audio/wav;base64,")


def test_id3_tags_dropped_between_pieces(monkeypatch):
    tag = b"ID3\x04\x00\x00\x00\x00\x00\x02AB"          # 2-byte ID3 body
    n = []
    monkeypatch.setattr("requests.post", lambda *a, **k: n.append(1) or FakeResp(content=tag + MP3 + b"X"))
    out = v.synthesize(" ".join(f"Sentence {i} of a long report." for i in range(700)))
    assert len(n) > 1 and out["audio"].startswith(tag + MP3 + b"X")
    assert out["audio"].count(b"ID3") == 1                      # only the first piece keeps its tag
