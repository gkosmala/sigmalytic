# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/voice.py
----------------
Sigmalytic Quantum(TM), prototype (admin only): speak to the AI Sigmalytic Assistant and hear its answers, and
hear the morning report in a natural voice.

How a spoken question is answered
  1. The browser records the question (up to 60 seconds) and sends the audio here.
  2. OpenAI speech-to-text (VOICE_STT_MODEL, default gpt-transcribe) turns it into text.
  3. The text goes to the existing assistant (backend/assistant.py) exactly as a typed question would, so the same
     lookups, number checks, wording checks, spending cap and log apply. Voice adds no second "brain".
  4. A spoken version of the checked answer is made by code, not by a model: markdown, tables, links and the Research
     context section are removed and the answer is cut at a sentence boundary. Every number spoken therefore comes
     from the checked answer; nothing new is said.
  5. OpenAI text-to-speech (VOICE_TTS_MODEL, default gpt-4o-mini-tts) speaks it in a built-in voice, steered by
     VOICE_STYLE (a deep, sophisticated British male voice by default). The voice is original: it imitates no real person or
     film character. The page labels it as an AI-generated voice.

Why not OpenAI's prompt-to-voice: voices made from a description work only in GPT-Live, which writes its own answers
and would bypass the assistant's number checks. This module keeps Claude (or ChatGPT) as the only source of answers.

Settings (Render environment variables on the backend service)
  OPENAI_API_KEY             required for voice (speech-to-text and text-to-speech)
  VOICE_STT_MODEL            default "gpt-transcribe"
  VOICE_TTS_MODEL            default "gpt-4o-mini-tts"
  VOICE_TTS_VOICE            default "onyx" (OpenAI's deepest built-in male voice; the accent comes from VOICE_STYLE)
  VOICE_STYLE                speaking-style instructions sent with every request (default below)
  VOICE_MAX_SPOKEN_WORDS     default 120   a longer answer is cut at a sentence and ends "The full answer is on screen."
  VOICE_DAILY_LIMIT_USD      default 2     voice spending cap per calendar day, Eastern time (separate from the
                                           assistant's own cap)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
STT_URL = "https://api.openai.com/v1/audio/transcriptions"
TTS_URL = "https://api.openai.com/v1/audio/speech"
BRAND = "Sigmalytic Quantum™"
AI_VOICE_NOTICE = "AI-generated voice"

DEFAULT_STYLE = (
    "Voice: a deep, sophisticated British male voice; original, not an imitation of any celebrity, real person or "
    "film character. Tone: calm, authoritative, articulate, natural and professional. Pacing: measured and unhurried. "
    "Pronunciation: precise with financial terminology; say stock tickers letter by letter (S-P-Y, N-V-D-A); read "
    "prices and percentages naturally."
)
STT_PROMPT = ("Sigmalytic market questions. Terms: Sigmalytic, Sigma Radar, Early Warning Radar, Sweet 16, bull trap, "
              "bear trap, breakout, breakdown, buying climax, selling climax, absorption, distribution, RSI, "
              "S&P 500, Nasdaq, SPY, QQQ, IWM, NVDA, TSLA, AAPL, MSFT, GOOG, AMZN, META.")

MAX_AUDIO_BYTES = 3 * 1024 * 1024        # about 60 seconds of browser speech, with room to spare
MAX_RECORD_SECONDS = 60
TTS_CHUNK_CHARS = 3800                   # OpenAI's speech endpoint takes up to 4,096 characters per request
MAX_SPEAK_CHARS = 30000                  # about 30 minutes of speech: a long morning report fits
CACHE_TTL_SECONDS = 7 * 24 * 3600
CACHE_MAX_BYTES = 8 * 1024 * 1024
WORDS_PER_MINUTE = 150
PRICES_PER_MINUTE = {"tts": 0.015, "stt": 0.0045}   # USD per minute of speech; estimates for the daily cap
SPEND_KEY = "voice:spend:{day}"
CACHE_KEY = "voice:tts:{h}"
_LOCAL_SPEND: Dict[str, float] = {}
FAILS_BEFORE_COOLDOWN = 3          # consecutive text-to-speech failures before retries pause
RETRY_COOLDOWN_SECONDS = 300       # how long automatic audio retries stay off after repeated failures
_TTS_HEALTH: Dict[str, float] = {"fails": 0, "retry_off_until": 0.0}

MIME_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/m4a": "m4a", "audio/x-m4a": "m4a",
            "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav"}


# ───────────────────────────── settings ─────────────────────────────

def _env(name: str, default: str) -> str:
    return (os.getenv(name) or "").strip() or default


def stt_model() -> str:
    return _env("VOICE_STT_MODEL", "gpt-transcribe")


def tts_model() -> str:
    return _env("VOICE_TTS_MODEL", "gpt-4o-mini-tts")


def tts_voice() -> str:
    return _env("VOICE_TTS_VOICE", "onyx")


def style() -> str:
    return _env("VOICE_STYLE", DEFAULT_STYLE)


def max_spoken_words() -> int:
    try:
        return max(20, int(_env("VOICE_MAX_SPOKEN_WORDS", "120")))
    except ValueError:
        return 120


def daily_limit() -> float:
    try:
        return max(0.0, float(_env("VOICE_DAILY_LIMIT_USD", "2")))
    except ValueError:
        return 2.0


def configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def status() -> Dict[str, Any]:
    spent = spent_today()
    return {"ok": True, "brand": BRAND, "configured": configured(), "stt_model": stt_model(),
            "tts_model": tts_model(), "voice": tts_voice(), "max_spoken_words": max_spoken_words(),
            "spent_today_usd": round(spent, 4), "daily_limit_usd": daily_limit(), "notice": AI_VOICE_NOTICE}


# ───────────────────────────── spending cap ─────────────────────────────

def _redis():
    try:
        from backend.radar_service import _redis_client
        return _redis_client
    except Exception:
        return None


def _day() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def spent_today() -> float:
    r = _redis()
    key = SPEND_KEY.format(day=_day())
    if r is None:
        return _LOCAL_SPEND.get(key, 0.0)
    try:
        return float(r.get(key) or 0.0)
    except Exception:
        return _LOCAL_SPEND.get(key, 0.0)


def _record(usd: float) -> None:
    key = SPEND_KEY.format(day=_day())
    r = _redis()
    if r is not None:
        try:
            r.incrbyfloat(key, usd)
            r.expire(key, 3 * 24 * 3600)
            return
        except Exception:
            pass
    _LOCAL_SPEND[key] = _LOCAL_SPEND.get(key, 0.0) + usd


def _check_cap(est_usd: float) -> Optional[str]:
    spent, cap = spent_today(), daily_limit()
    if spent + est_usd > cap:
        return (f"Today's voice limit is reached (${spent:.2f} of ${cap:.2f}). It resets at midnight Eastern; "
                f"typed questions still work.")
    return None


def speech_minutes(text: str) -> float:
    return len(re.findall(r"\S+", text or "")) / WORDS_PER_MINUTE


# ───────────────────────────── spoken text ─────────────────────────────

_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
_URL = re.compile(r"https?://\S+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def spoken_text(answer: str, max_words: Optional[int] = None) -> str:
    """The checked written answer turned into something worth hearing. Removes the Research context section,
    markdown, tables, links and footnote marks; keeps the sentences in order and cuts at a sentence boundary.
    Code only: no model is involved, so nothing is said that the checked answer does not already say."""
    from backend.assistant import split_research
    body, _research = split_research(answer or "")
    lines: List[str] = []
    table_said = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("|"):
            if not table_said:
                lines.append("The table is on screen.")
                table_said = True
            continue
        if re.fullmatch(r"[-*_=\s]{3,}", line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^(?:[-*+•]|\d+[.)])\s+", "", line)
        line = _LINK.sub(r"\1", line)
        line = _URL.sub("", line)
        line = re.sub(r"[*_`~]+", "", line)
        line = re.sub(r"\[\^?\d+\]|¹|²|³|[⁰-⁹]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if not re.search(r"[.!?:;]$", line):
            line += "."
        lines.append(line)
    text = " ".join(lines)
    limit = max_words or max_spoken_words()
    sentences = [s.strip() for s in _SENT.split(text) if s.strip()]
    out: List[str] = []
    words = 0
    for s in sentences:
        n = len(s.split())
        if out and words + n > limit:
            out.append("The full answer is on screen.")
            break
        out.append(s)
        words += n
    return " ".join(out)


def chunk_text(text: str, size: int = TTS_CHUNK_CHARS) -> List[str]:
    """Splits text into pieces under `size` characters, at sentence ends where possible, then at spaces."""
    text = re.sub(r"\s+", " ", text or "").strip()
    chunks: List[str] = []
    cur = ""
    for s in _SENT.split(text):
        while len(s) > size:                       # one very long sentence: split at the last space
            cut = s.rfind(" ", 0, size)
            cut = cut if cut > 0 else size
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(s[:cut].strip())
            s = s[cut:].strip()
        if cur and len(cur) + 1 + len(s) > size:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


# ───────────────────────────── OpenAI calls ─────────────────────────────

def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"}


def _error_text(r: Any) -> str:
    try:
        return (r.json().get("error") or {}).get("message") or r.text[:200]
    except Exception:
        return str(getattr(r, "text", ""))[:200]


def decode_audio(data: str) -> Tuple[bytes, str]:
    """(bytes, mime) from a data URL or plain base64."""
    s = str(data or "")
    mime = "audio/webm"
    m = re.match(r"data:([^;,]+)[^,]*,", s)
    if m:
        mime = m.group(1).lower()
        s = s[m.end():]
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception as exc:
        raise ValueError("The recording could not be read.") from exc
    return raw, mime


def transcribe(audio: str, mime: Optional[str] = None, duration_ms: Optional[float] = None) -> Dict[str, Any]:
    if not configured():
        return {"ok": False, "error": "OPENAI_API_KEY is not set on the backend service in Render, so voice is off."}
    try:
        raw, found_mime = decode_audio(audio)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    mime = (mime or found_mime or "audio/webm").split(";")[0].strip().lower()
    if not raw:
        return {"ok": False, "error": "The recording was empty. Hold the button a little longer."}
    if len(raw) > MAX_AUDIO_BYTES:
        return {"ok": False, "error": f"Recordings are limited to {MAX_RECORD_SECONDS} seconds."}
    seconds = min(MAX_RECORD_SECONDS, max(1.0, float(duration_ms or 0) / 1000 or len(raw) / 16000))
    est = seconds / 60 * PRICES_PER_MINUTE["stt"]
    cap = _check_cap(est)
    if cap:
        return {"ok": False, "error": cap}
    import requests
    ext = MIME_EXT.get(mime, "webm")
    try:
        r = requests.post(STT_URL, headers=_headers(), timeout=60,
                          files={"file": (f"question.{ext}", raw, mime)},
                          data={"model": stt_model(), "language": "en", "prompt": STT_PROMPT,
                                "response_format": "json"})
    except Exception as exc:
        return {"ok": False, "error": f"Speech-to-text could not be reached: {str(exc)[:160]}"}
    if not r.ok:
        return {"ok": False, "error": f"Speech-to-text failed ({r.status_code}): {_error_text(r)}"}
    _record(est)
    text = str((r.json() or {}).get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "No speech was heard. Try again a little closer to the microphone."}
    return {"ok": True, "text": text, "seconds": round(seconds, 1), "cost_usd": round(est, 5)}


def _cache_get(h: str) -> Optional[bytes]:
    r = _redis()
    if r is None:
        return None
    try:
        v = r.get(CACHE_KEY.format(h=h))
        return base64.b64decode(v) if v else None
    except Exception:
        return None


def _cache_put(h: str, audio: bytes) -> None:
    r = _redis()
    if r is None or len(audio) > CACHE_MAX_BYTES:
        return
    try:
        r.setex(CACHE_KEY.format(h=h), CACHE_TTL_SECONDS, base64.b64encode(audio).decode())
    except Exception:
        pass


def synthesize(text: str) -> Dict[str, Any]:
    """MP3 audio for `text` in the Sigmalytic Quantum voice. Long text is spoken in pieces and joined (MP3 frames join cleanly).
    Identical text is served from a 7-day cache, so a report played twice is paid for once."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return {"ok": False, "error": "Nothing to say."}
    if len(text) > MAX_SPEAK_CHARS:
        return {"ok": False, "error": f"Text is too long to speak (over {MAX_SPEAK_CHARS:,} characters)."}
    if not configured():
        return {"ok": False, "error": "OPENAI_API_KEY is not set on the backend service in Render, so voice is off."}
    h = hashlib.sha256("|".join([tts_model(), tts_voice(), style(), text]).encode()).hexdigest()
    cached = _cache_get(h)
    if cached:
        return {"ok": True, "audio": cached, "mime": "audio/mpeg", "cached": True, "cost_usd": 0.0}
    est = speech_minutes(text) * PRICES_PER_MINUTE["tts"]
    cap = _check_cap(est)
    if cap:
        return {"ok": False, "error": cap}
    import requests
    parts: List[bytes] = []
    for piece in chunk_text(text):
        body = {"model": tts_model(), "voice": tts_voice(), "input": piece, "response_format": "mp3"}
        if style():
            body["instructions"] = style()
        try:
            r = requests.post(TTS_URL, headers={**_headers(), "Content-Type": "application/json"},
                              data=json.dumps(body), timeout=120)
        except Exception as exc:
            return {"ok": False, "error": f"Text-to-speech could not be reached: {str(exc)[:160]}"}
        if not r.ok:
            return {"ok": False, "error": f"Text-to-speech failed ({r.status_code}): {_error_text(r)}"}
        parts.append(r.content)
    audio = b"".join(parts)
    _record(est)
    _cache_put(h, audio)
    return {"ok": True, "audio": audio, "mime": "audio/mpeg", "cached": False, "cost_usd": round(est, 5)}


def data_url(audio: bytes, mime: str = "audio/mpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(audio).decode()}"


# ───────────────────────────── what the endpoints call ─────────────────────────────

def speak(text: str, mode: str = "text") -> Dict[str, Any]:
    """mode 'answer': text is an assistant answer, so it is shortened by spoken_text() first. mode 'text': read as is."""
    said = spoken_text(text) if mode == "answer" else re.sub(r"\s+", " ", str(text or "")).strip()
    out = synthesize(said)
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error")}
    return {"ok": True, "spoken": said, "audio": data_url(out["audio"], out["mime"]), "cached": out["cached"],
            "cost_usd": out["cost_usd"], "notice": AI_VOICE_NOTICE}


def ask(payload: Dict[str, Any], admin: str = "") -> Dict[str, Any]:
    """A spoken (or typed) question in, the assistant's checked answer out, plus the spoken version as audio.
    Speech never blocks the answer: if text-to-speech fails, it is retried once (unless retries are cooling down after
    repeated failures), and if it still fails the written answer is returned with a voice_error. With speak false,
    no speech is generated at all. The browser's token is echoed so a late reply cannot be mistaken for a newer one."""
    p = payload or {}
    question = str(p.get("question") or "").strip()
    heard = None
    if p.get("audio"):
        t = transcribe(p["audio"], p.get("mime"), p.get("duration_ms"))
        if not t["ok"]:
            return {"ok": False, "error": t["error"], "stage": "listen"}
        question = heard = t["text"]
    if not question:
        return {"ok": False, "error": "Say or type a question first.", "stage": "listen"}
    from backend import assistant
    result = assistant.ask(question, p.get("history"), admin=admin, attachment=p.get("attachment"))
    result = dict(result or {})
    result["question"] = question
    if heard is not None:
        result["heard"] = heard
    if result.get("ok") and p.get("speak", True):
        s = speak(result.get("answer") or "", mode="answer")
        _note_tts(s.get("ok", False))
        if not s.get("ok") and not _is_limit(s.get("error")):
            if retry_allowed():
                result["audio_retried"] = True
                s = speak(result.get("answer") or "", mode="answer")
                _note_tts(s.get("ok", False))
            else:
                result["audio_retry_skipped"] = True
        if s.get("ok"):
            result.update({"spoken": s["spoken"], "audio": s["audio"], "voice_cost_usd": s["cost_usd"],
                           "voice_notice": AI_VOICE_NOTICE})
        else:
            result["voice_error"] = s.get("error")
    if "token" in p:
        result["token"] = p["token"]
    return result


def _is_limit(error: Any) -> bool:
    return "limit" in str(error or "").lower()


def retry_allowed() -> bool:
    """One automatic audio retry per answer, unless text-to-speech has failed repeatedly; then retries pause for
    RETRY_COOLDOWN_SECONDS so a broken voice service cannot cause an endless loop."""
    return time.time() >= _TTS_HEALTH["retry_off_until"]


def _note_tts(ok: bool) -> None:
    if ok:
        _TTS_HEALTH["fails"] = 0
        return
    _TTS_HEALTH["fails"] += 1
    if _TTS_HEALTH["fails"] >= FAILS_BEFORE_COOLDOWN:
        _TTS_HEALTH["retry_off_until"] = time.time() + RETRY_COOLDOWN_SECONDS
        _TTS_HEALTH["fails"] = 0


def morning_report(text: Optional[str]) -> Dict[str, Any]:
    if not (text or "").strip():
        return {"ok": False, "error": "No morning report is saved yet."}
    return speak(text, mode="text")
