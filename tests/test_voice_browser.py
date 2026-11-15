"""Sigmalytic Quantum, browser: runs the hands-free conversation state machine (frontend/assets/quantum_voice.js)
through 33 scenarios in headless Chrome with a fake microphone and player: push to talk, hands-free resume after
spoken, text-only, read-aloud-off and blocked-playback answers, stale replies, the no-reply watchdog, the pause after
repeated failures, Stop, lost microphone permission and Reconnect, no duplicate sessions, and an unanswered
permission prompt, and pause detection relative to room noise (noisy room, soft voice, a click, blocked audio analysis). Skipped when Chrome is not installed."""
import os
import re
import shutil
import subprocess

import pytest

HARNESS = os.path.join(os.path.dirname(__file__), "browser", "quantum_voice_harness.html")
CHROME = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)


@pytest.mark.skipif(CHROME is None, reason="Chrome is not installed")
def test_hands_free_state_machine_scenarios():
    out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                          "--virtual-time-budget=60000", "--dump-dom", "file://" + os.path.abspath(HARNESS)],
                         capture_output=True, text=True, timeout=120).stdout
    log = re.search(r'<pre id="log">(.*?)DONE', out, re.S)
    assert log, "the harness did not finish"
    lines = [ln for ln in log.group(1).splitlines() if ln.startswith(("PASS", "FAIL"))]
    assert len(lines) == 33, lines
    assert not [ln for ln in lines if ln.startswith("FAIL")], "\n".join(lines)
