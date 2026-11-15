// Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
// Sigmalytic Quantum (prototype, admin only): the voice conversation, run as a state machine.
//
// States (shown in the status pill): Ready, Listening, Processing, Speaking, Text only, Reconnecting,
// Microphone unavailable, Stopped.
//
// Rules
//  - Push to talk is the default: tap Talk to start, tap again to send (60 seconds at most).
//  - Hands-free listens only after the user switches it on. It sends after a pause in speech and, after EVERY
//    outcome (spoken answer, text-only answer, read-aloud off, error, timeout), returns to Ready and reopens the
//    microphone after a short, configurable delay. It never waits on audio succeeding.
//  - The backend retries audio once and pauses retries after repeated failures; the browser only sees the result.
//  - A watchdog ends Processing if no reply arrives in time (network failure, dropped request).
//  - After repeated consecutive failures, automatic listening pauses until Talk is tapped (no endless loop).
//  - If microphone permission is lost or the device disappears, automatic listening stops, a warning shows and a
//    Reconnect microphone button appears.
//  - Stop always stops capture, playback and any pending reopen; it also switches hands-free off.
//  - Only one listening session and one playback at a time; a late reply for an older question is ignored.
//
// Settings come from data-* attributes on #sigmalytic-quantum-panel (frontend environment variables).
(function () {
  var MAX_MS = 60000;
  var ST = {
    READY: ["Ready", "rgba(148,163,184,.18)", "#FFFFFF"],
    LISTENING: ["Listening", "rgba(220,38,38,.25)", "#FCA5A5"],
    PROCESSING: ["Processing", "rgba(59,130,246,.22)", "#93C5FD"],
    SPEAKING: ["Speaking", "rgba(201,162,39,.22)", "#E5C66B"],
    TEXT_ONLY: ["Text only", "rgba(148,163,184,.22)", "#E2E8F0"],
    RECONNECTING: ["Reconnecting", "rgba(234,179,8,.22)", "#FDE68A"],
    MIC_UNAVAILABLE: ["Microphone unavailable", "rgba(220,38,38,.25)", "#FCA5A5"],
    STOPPED: ["Stopped", "rgba(148,163,184,.18)", "#CBD5E1"]
  };
  var state = "READY", token = 0, pendingToken = null;
  var rec = null, chunks = [], started = 0, stream = null, cancelReason = null;
  var audioCtx = null, vadTimer = null, heard = false, lastVoice = 0;
  var timers = { resume: null, max: null, watchdog: null };
  var errors = 0, autoPaused = false, micBlocked = false, opening = false;

  // ── helpers ──
  function $(id) { return document.getElementById(id); }
  function cfg(name, def) {
    var p = $("sigmalytic-quantum-panel");
    var v = p ? parseInt(p.getAttribute("data-" + name), 10) : NaN;
    return isNaN(v) ? def : v;
  }
  function setProps(id, props) {
    if (window.dash_clientside && window.dash_clientside.set_props) { window.dash_clientside.set_props(id, props); }
  }
  function message(text) { setProps("assistant-voice-status", { children: text || "" }); }
  function handsFree() {
    var box = document.querySelector("#assistant-voice-handsfree input[type=checkbox]");
    return !!(box && box.checked);
  }
  function player() { return $("assistant-voice-audio"); }
  function clear(name) { clearTimeout(timers[name]); timers[name] = null; }
  function clearAll() { clear("resume"); clear("max"); clear("watchdog"); }

  function setState(next, text) {
    state = next;
    var s = ST[next], pill = $("assistant-voice-state");
    if (pill) {
      pill.textContent = "● " + s[0];
      pill.style.background = s[1];
      pill.style.color = s[2];
    }
    var b = $("assistant-mic-btn");
    if (b) {
      var live = next === "LISTENING";
      b.textContent = live ? (handsFree() ? "■ Send now" : "■ Stop and send")
                           : (handsFree() ? "🎙 Talk (hands-free)" : "🎙 Talk");
      b.style.background = live ? "#B91C1C" : "rgba(201,162,39,.15)";
      b.style.color = live ? "#FFFFFF" : "#E5C66B";
    }
    var rc = $("assistant-mic-reconnect");
    if (rc) { rc.style.display = next === "MIC_UNAVAILABLE" ? "inline-block" : "none"; }
    if (text !== undefined) { message(text); }
  }

  // ── reopening the microphone (hands-free only) ──
  function canAutoListen() { return handsFree() && !autoPaused && !micBlocked && state !== "STOPPED"; }
  function scheduleResume() {
    clear("resume");
    if (!canAutoListen()) { return; }
    timers.resume = setTimeout(function () {
      timers.resume = null;
      if (canAutoListen() && (state === "READY" || state === "TEXT_ONLY") && !rec && !opening) { startListening(); }
    }, cfg("resume-ms", 900));
  }
  function settle(next, text, failed) {
    // Every outcome ends here: leave Processing/Speaking for a valid resting state, then maybe listen again.
    clear("watchdog");
    pendingToken = null;
    if (failed) {
      errors += 1;
      if (handsFree() && errors >= cfg("max-errors", 3)) {
        autoPaused = true;
        setState("READY", (text ? text + " " : "") + "Hands-free paused after repeated problems. Tap Talk to " +
                          "try again.");
        return;
      }
    } else {
      errors = 0;
    }
    setState(next, text);
    scheduleResume();
  }

  // ── listening ──
  // Pause detection, relative to the room: the first half second measures the background noise (fans, computers,
  // traffic), and speech and silence are judged against that level, not a fixed number. A sound must last about a
  // fifth of a second to count as speech, so a click or a cough does not start the clock.
  var CALIBRATE_MS = 500, SPEECH_MS = 200;
  function level(pct) {
    var bar = $("assistant-voice-level-bar");
    if (bar) { bar.style.width = Math.max(0, Math.min(100, pct)) + "%"; }
  }
  function noPauseDetection() {
    message("Listening… pause detection is not available in this browser: tap Send now when you finish.");
  }
  function startVad(s) {
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { noPauseDetection(); return; }
    try {
      audioCtx = new Ctx();
      if (audioCtx.state === "suspended" && audioCtx.resume) { audioCtx.resume(); }
      var analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      audioCtx.createMediaStreamSource(s).connect(analyser);
      var buf = new Float32Array(analyser.fftSize);
      var t0 = Date.now(), samples = [], floor = null, speechFor = 0, lastTick = t0, warned = false;
      heard = false;
      lastVoice = t0;
      vadTimer = setInterval(function () {
        var now = Date.now(), dt = now - lastTick;
        lastTick = now;
        if (audioCtx && audioCtx.state === "suspended") {           // the browser would not start audio analysis
          if (!warned && now - t0 > 800) { warned = true; noPauseDetection(); }
          return;
        }
        analyser.getFloatTimeDomainData(buf);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) { sum += buf[i] * buf[i]; }
        var rms = Math.sqrt(sum / buf.length);
        if (floor === null) {                                        // measuring the room
          samples.push(rms);
          if (now - t0 < CALIBRATE_MS) { return; }
          samples.sort(function (a, b) { return a - b; });
          floor = samples[Math.floor(samples.length / 2)] || 0;
        }
        var speakAt = Math.max(0.012, floor * 2.5 + 0.004);
        var quietBelow = Math.max(0.008, floor * 1.6 + 0.002);
        level(rms / (speakAt * 2) * 100);
        if (rms > speakAt) {
          speechFor += dt;
          if (speechFor >= SPEECH_MS) { heard = true; }
          if (heard) { lastVoice = now; }
        } else {
          speechFor = 0;
          if (!heard && rms < quietBelow) { floor = floor * 0.95 + rms * 0.05; }   // follow the room while waiting
        }
        if (heard && now - lastVoice > cfg("silence-ms", 1500)) { stopListening(null); }
        else if (!heard && now - started > cfg("no-speech-ms", 10000)) { stopListening("no_speech"); }
      }, 100);
    } catch (e) { stopVad(); noPauseDetection(); }
  }
  function stopVad() {
    clearInterval(vadTimer);
    vadTimer = null;
    level(0);
    if (audioCtx) { try { audioCtx.close(); } catch (e) { /* closed */ } audioCtx = null; }
  }
  function releaseMic() {
    stopVad();
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
  }
  function pickMime() {
    var options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) { return ""; }
    for (var i = 0; i < options.length; i++) { if (MediaRecorder.isTypeSupported(options[i])) { return options[i]; } }
    return "";
  }
  function micFailed(err) {
    releaseMic();
    rec = null;
    var name = (err && err.name) || "";
    micBlocked = true;
    clear("resume");
    if (name === "NotAllowedError" || name === "SecurityError") {
      setState("MIC_UNAVAILABLE", "Microphone access is blocked. Allow the microphone for this site, then tap " +
                                  "Reconnect microphone.");
    } else if (name === "NotFoundError" || name === "OverconstrainedError") {
      setState("MIC_UNAVAILABLE", "No microphone was found. Connect one, then tap Reconnect microphone.");
    } else {
      setState("MIC_UNAVAILABLE", "The microphone could not be opened. Tap Reconnect microphone to try again.");
    }
  }
  function startListening() {
    if (rec || opening || state === "PROCESSING") { return; }   // never two sessions at once
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setState("MIC_UNAVAILABLE", "This browser cannot record audio. Use a current Chrome, Edge or Safari.");
      return;
    }
    clear("resume");
    var p = player();
    if (p && !p.paused) { p.pause(); }                      // never listen and speak at the same time
    opening = true;                                         // waiting for the microphone (or the permission prompt)
    message("Opening the microphone… (tap Talk or Stop to cancel)");
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then(function (s) {
        if (!opening) { s.getTracks().forEach(function (t) { t.stop(); }); return; }   // cancelled meanwhile
        opening = false;
        stream = s;
        micBlocked = false;
        s.getAudioTracks().forEach(function (t) {
          t.onended = function () {                          // device unplugged or permission revoked mid-session
            if (rec) { stopListening("mic_lost"); }
          };
        });
        var mime = pickMime();
        try {
          rec = mime ? new MediaRecorder(s, { mimeType: mime }) : new MediaRecorder(s);
        } catch (e) { micFailed(e); return; }
        chunks = [];
        cancelReason = null;
        rec.ondataavailable = function (e) { if (e.data && e.data.size) { chunks.push(e.data); } };
        rec.onstop = finishRecording;
        started = Date.now();
        rec.start();
        if (handsFree()) {
          startVad(s);
          setState("LISTENING", "Listening\u2026 ask your question, then pause: it sends after a short silence (or tap Send now).");
        } else {
          setState("LISTENING", "Listening… tap again to send (60 seconds at most).");
        }
        timers.max = setTimeout(function () { stopListening(null); }, MAX_MS);
      })
      .catch(function (err) {
        if (!opening) { return; }                          // cancelled meanwhile: nothing to report
        opening = false;
        micFailed(err);
      });
  }
  function stopListening(reason) {
    clear("max");
    stopVad();
    cancelReason = reason;
    if (rec && rec.state === "recording") { rec.stop(); } else { releaseMic(); rec = null; }
  }
  function finishRecording() {
    var ms = Date.now() - started, type = (rec && rec.mimeType) || "audio/webm";
    var blob = new Blob(chunks, { type: type });
    rec = null;
    chunks = [];
    releaseMic();
    var reason = cancelReason;
    cancelReason = null;
    if (reason === "stopped") { return; }                                  // Stop already set the state
    if (reason === "mic_lost") {
      micBlocked = true;
      setState("MIC_UNAVAILABLE", "The microphone was disconnected or its permission was removed. Tap Reconnect " +
                                  "microphone.");
      return;
    }
    if (reason === "no_speech") {
      autoPaused = true;
      setState("READY", "Hands-free paused: nothing was heard. Tap Talk to continue.");
      return;
    }
    if (ms < 500 || !blob.size) {
      settle("READY", "That was too short. Ask your question, then pause or tap to send.", false);
      return;
    }
    token += 1;
    pendingToken = token;
    setState("PROCESSING", "Thinking…");
    clear("watchdog");
    var mine = token;
    timers.watchdog = setTimeout(function () {
      if (pendingToken === mine) {
        settle("READY", "No reply arrived in time. Check your connection; the microphone is ready again.", true);
      }
    }, cfg("processing-timeout-ms", 215000));
    var reader = new FileReader();
    reader.onload = function () {
      setProps("assistant-voice-recording", {
        data: { audio: reader.result, mime: type.split(";")[0], duration_ms: ms, token: mine, at: Date.now() }
      });
    };
    reader.onerror = function () { settle("READY", "The recording could not be read. Please try again.", true); };
    reader.readAsDataURL(blob);
  }

  // ── speaking ──
  function play(src, okText) {
    var p = player();
    if (!p) { settle("TEXT_ONLY", "Text only: the audio player is missing.", false); return; }
    if (rec) { stopListening("stopped"); }                 // a manual playback never overlaps a recording
    try { p.pause(); } catch (e) { /* not playing */ }
    p.src = src;
    setState("SPEAKING", okText || "");
    var playing = p.play();
    if (playing && playing.catch) {
      playing.catch(function () {                          // autoplay blocked or the audio would not decode
        if (state === "SPEAKING") {
          settle("TEXT_ONLY", "Text only: the browser would not play the audio. Press play on the player to " +
                              "hear it.", false);
        }
      });
    }
  }
  document.addEventListener("ended", function (e) {
    if (e.target && e.target.id === "assistant-voice-audio" && state === "SPEAKING") { settle("READY", "", false); }
  }, true);
  document.addEventListener("error", function (e) {
    if (e.target && e.target.id === "assistant-voice-audio" && state === "SPEAKING") {
      settle("TEXT_ONLY", "Text only: the audio could not be played.", false);
    }
  }, true);
  document.addEventListener("pause", function (e) {      // the user paused the player by hand
    var p = e.target;
    if (p && p.id === "assistant-voice-audio" && state === "SPEAKING" && !p.ended && p.currentTime > 0) {
      setState("READY", "Paused. Press play to continue, or tap Talk.");
      clear("resume");
    }
  }, true);
  document.addEventListener("play", function (e) {       // the user resumed the player by hand
    if (e.target && e.target.id === "assistant-voice-audio" && state === "READY") { setState("SPEAKING", ""); }
  }, true);

  // ── results from the server (via the clientside callback) ──
  function onResult(r) {
    if (!r) { return; }
    if (r.kind !== "manual") {
      if (r.token == null || r.token !== pendingToken) { return; }   // a late reply for an older question
    } else if (state === "STOPPED") {
      state = "READY";
    }
    if (r.outcome === "audio" && r.audio) {
      clear("watchdog");
      pendingToken = null;
      errors = 0;
      play(r.audio, r.message || "");
    } else if (r.outcome === "text_only") {
      settle("TEXT_ONLY", r.message || "Text only.", false);
    } else if (r.outcome === "no_speech") {
      settle("READY", r.message || "No speech was heard.", true);
    } else {
      settle("READY", r.message || "Something went wrong; the microphone is ready again.", r.kind !== "manual");
    }
  }
  window.SigmalyticQuantum = { onResult: onResult, state: function () { return state; } };

  // ── controls ──
  function stopSession() {
    clearAll();
    pendingToken = null;
    opening = false;
    if (rec) { stopListening("stopped"); } else { releaseMic(); }
    var p = player();
    if (p && !p.paused) { p.pause(); }
    if (handsFree()) { setProps("assistant-voice-handsfree", { value: [] }); }
    setState("STOPPED", "Session stopped. The microphone is off.");
  }
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) { return; }
    if (t.closest("#assistant-mic-btn")) {
      e.preventDefault();
      if (rec && rec.state === "recording") { stopListening(null); return; }
      if (opening) {                                       // permission prompt unanswered: cancel the request
        opening = false;
        setState("READY", "Microphone request cancelled. Tap Talk to try again.");
        return;
      }
      if (state === "PROCESSING") { message("Still working on the last question…"); return; }
      autoPaused = false;
      errors = 0;
      if (state === "STOPPED" || state === "MIC_UNAVAILABLE" || state === "TEXT_ONLY") { setState("READY"); }
      startListening();                                    // also interrupts speech (barge-in)
    } else if (t.closest("#assistant-voice-stop")) {
      e.preventDefault();
      stopSession();
    } else if (t.closest("#assistant-mic-reconnect")) {
      e.preventDefault();
      micBlocked = false;
      autoPaused = false;
      errors = 0;
      setState("RECONNECTING", "Reconnecting the microphone…");
      startListening();
    }
  });
  document.addEventListener("change", function (e) {
    if (!e.target || !e.target.closest || !e.target.closest("#assistant-voice-handsfree")) { return; }
    if (handsFree()) {
      autoPaused = false;
      errors = 0;
      if (state === "STOPPED" || state === "MIC_UNAVAILABLE") { state = "READY"; }
      setState(state, "");
      if (state === "READY" || state === "TEXT_ONLY") { startListening(); }
    } else {
      clear("resume");
      opening = false;
      if (rec) { stopListening("stopped"); }
      if (state === "LISTENING") { setState("READY", "Hands-free is off. Tap Talk to ask a question."); }
      else { setState(state); }
    }
  });

  // Permission revoked in browser settings while the page is open.
  try {
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: "microphone" }).then(function (perm) {
        perm.onchange = function () {
          if (perm.state === "denied") {
            if (rec) { stopListening("mic_lost"); }
            else {
              micBlocked = true;
              clear("resume");
              setState("MIC_UNAVAILABLE", "Microphone permission was removed. Allow it, then tap Reconnect " +
                                          "microphone.");
            }
          }
        };
      }).catch(function () { /* this browser cannot report microphone permission */ });
    }
  } catch (e) { /* ignore */ }
})();
