// Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
// Sigmalytic Quantum (prototype, admin only): records spoken questions for the AI Sigmalytic Assistant.
//
// Push to talk (default): tap Talk to start, tap again to send (60 seconds at most).
// Hands-free conversation (optional switch): listening starts at once; the question is sent after about 1.5 seconds
// of silence; after the spoken answer finishes playing, listening starts again. If nothing is said for 10 seconds,
// hands-free pauses until Talk is tapped. The microphone is never open while an answer is playing (so the assistant
// does not hear itself), and it is released whenever recording stops.
//
// A finished recording goes into the Dash store "assistant-voice-recording"; a server callback sends it to
// /api/admin/voice/ask.
(function () {
  var MAX_MS = 60000, SILENCE_MS = 1500, NO_SPEECH_MS = 10000, LEVEL = 0.02;
  var rec = null, chunks = [], started = 0, timer = null, stream = null;
  var audioCtx = null, vadTimer = null, heard = false, lastVoice = 0, cancelled = false;

  function setProps(id, props) {
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props(id, props);
    }
  }
  function status(text) { setProps("assistant-voice-status", { children: text }); }
  function handsFree() {
    var box = document.querySelector("#assistant-voice-handsfree input[type=checkbox]");
    return !!(box && box.checked);
  }
  function player() { return document.getElementById("assistant-voice-audio"); }
  function label(text, active) {
    var b = document.getElementById("assistant-mic-btn");
    if (!b) { return; }
    b.textContent = text;
    b.style.background = active ? "#B91C1C" : "rgba(201,162,39,.15)";
    b.style.color = active ? "#FFFFFF" : "#E5C66B";
  }
  function idleLabel() { label(handsFree() ? "🎙 Talk (hands-free)" : "🎙 Talk", false); }
  function pickMime() {
    var options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) { return ""; }
    for (var i = 0; i < options.length; i++) {
      if (MediaRecorder.isTypeSupported(options[i])) { return options[i]; }
    }
    return "";
  }

  // Hands-free: watch the microphone level; stop after a pause that follows speech.
  function startVad(s) {
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { return; }
    audioCtx = new Ctx();
    var analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    audioCtx.createMediaStreamSource(s).connect(analyser);
    var buf = new Float32Array(analyser.fftSize);
    heard = false;
    lastVoice = Date.now();
    vadTimer = setInterval(function () {
      analyser.getFloatTimeDomainData(buf);
      var sum = 0;
      for (var i = 0; i < buf.length; i++) { sum += buf[i] * buf[i]; }
      var rms = Math.sqrt(sum / buf.length), now = Date.now();
      if (rms > LEVEL) { heard = true; lastVoice = now; }
      if (heard && now - lastVoice > SILENCE_MS) { stop(false); }
      else if (!heard && now - started > NO_SPEECH_MS) { stop(true); }
    }, 100);
  }
  function stopVad() {
    clearInterval(vadTimer);
    vadTimer = null;
    if (audioCtx) { try { audioCtx.close(); } catch (e) { /* already closed */ } audioCtx = null; }
  }

  function start() {
    if (rec) { return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      status("This browser cannot record audio. Use a current Chrome, Edge or Safari.");
      return;
    }
    var p = player();
    if (p && !p.paused) { p.pause(); }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      .then(function (s) {
        stream = s;
        var mime = pickMime();
        rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
        chunks = [];
        cancelled = false;
        rec.ondataavailable = function (e) { if (e.data && e.data.size) { chunks.push(e.data); } };
        rec.onstop = finish;
        started = Date.now();
        rec.start();
        if (handsFree()) {
          startVad(stream);
          label("■ Listening… (tap to stop)", true);
          status("Listening… speak naturally; your question is sent when you pause.");
        } else {
          label("■ Stop and send", true);
          status("Listening… tap again to send (60 seconds at most).");
        }
        timer = setTimeout(function () { stop(false); }, MAX_MS);
      }).catch(function () {
        status("Microphone access was blocked. Allow the microphone for this site and try again.");
      });
  }
  function stop(cancel) {
    clearTimeout(timer);
    stopVad();
    cancelled = !!cancel;
    if (rec && rec.state === "recording") { rec.stop(); }
  }
  function finish() {
    var ms = Date.now() - started;
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    var type = (rec && rec.mimeType) || "audio/webm";
    var blob = new Blob(chunks, { type: type });
    rec = null;
    chunks = [];
    idleLabel();
    if (cancelled) {
      status("Hands-free paused: nothing was heard. Tap Talk to continue.");
      return;
    }
    if (ms < 500 || !blob.size) {
      status("That was too short. Tap Talk, ask your question, then tap again.");
      return;
    }
    status("Thinking…");
    var reader = new FileReader();
    reader.onload = function () {
      setProps("assistant-voice-recording", {
        data: { audio: reader.result, mime: type.split(";")[0], duration_ms: ms, at: Date.now() }
      });
    };
    reader.readAsDataURL(blob);
  }

  // Talk button: start, or stop and send (in hands-free, a tap while listening sends at once).
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("#assistant-mic-btn") : null;
    if (!b) { return; }
    e.preventDefault();
    if (rec && rec.state === "recording") { stop(false); } else { start(); }
  });

  // Hands-free switch: turning it on starts listening; turning it off ends any listening without sending.
  document.addEventListener("change", function (e) {
    if (!e.target || !e.target.closest || !e.target.closest("#assistant-voice-handsfree")) { return; }
    if (handsFree()) {
      idleLabel();
      var p = player();
      if (!p || p.paused) { start(); }
    } else {
      if (rec && rec.state === "recording") { stop(true); }
      idleLabel();
      status("");
    }
  });

  // After a spoken answer finishes, hands-free listens again ("ended" does not bubble, so listen in capture).
  document.addEventListener("ended", function (e) {
    if (e.target && e.target.id === "assistant-voice-audio" && handsFree()) {
      setTimeout(start, 350);
    }
  }, true);

  // An answer that comes back with nothing to play (an error, a withheld answer, or read-aloud switched off) would
  // leave hands-free waiting for an "ended" that never comes. Watch the status line: when it leaves "Thinking…" and
  // nothing starts playing within a second, listen again.
  var lastStatus = "", watched = null, lastLoad = 0;
  ["loadstart", "play"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      if (e.target && e.target.id === "assistant-voice-audio") { lastLoad = Date.now(); }
    }, true);
  });
  function onStatus() {
    var el = document.getElementById("assistant-voice-status");
    var now = el ? el.textContent : "";
    var was = lastStatus;
    lastStatus = now;
    if (was.indexOf("Thinking") !== 0 || now.indexOf("Thinking") === 0) { return; }
    setTimeout(function () {
      var p = player();
      var loading = Date.now() - lastLoad < 3000;   // an answer is loading or playing: "ended" will resume
      if (handsFree() && !rec && !loading && (!p || p.paused)) { start(); }
    }, 1000);
  }
  setInterval(function () {
    var el = document.getElementById("assistant-voice-status");
    if (!el || el === watched) { return; }
    watched = el;
    lastStatus = el.textContent;
    new MutationObserver(onStatus).observe(el, { childList: true, characterData: true, subtree: true });
  }, 1000);
})();
