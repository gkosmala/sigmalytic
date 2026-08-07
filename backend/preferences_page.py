# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
preferences_page.py — Sigmalytic Quant
Standalone FastAPI route serving a full HTML preferences page.
Mount in main.py:
    from preferences_page import router as prefs_page_router
    app.include_router(prefs_page_router)

NOTE (2026-08-07): confirmed via full-codebase search this router is
genuinely never mounted anywhere -- the include_router() call shown
above was never actually added to main.py. The live, actual
preferences UI is frontend/app.py's own inline build_preferences_tab()
function inside the main Dash app (frontend/preferences_tab.py is
ALSO unused, for the same reason -- app.py never imports it either).
This file is intentionally left as dead code rather than deleted,
since it's a real, complete, working standalone page that could be
revived (e.g. for an email 'manage your preferences' link) -- but as
of this note, it is not live, not reachable, and not a bug. If ever
mounted, note the alert type options (wyckoff/gann/ab_score/elliott/
fibonacci) reference several methods (Gann, Elliott) already
deliberately excluded from the live scoring system's doctrine -- see
doctrine_deep_engine.py's own docstring -- and would need updating
first to avoid offering toggles for signals that no longer exist.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/preferences")
async def preferences_page(user_id: str = "", email: str = ""):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sigmalytic — Alert Preferences</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0d1b2e;
    color: #f1f5f9;
    font-family: 'DM Sans', -apple-system, sans-serif;
    min-height: 100vh;
    padding: 32px 16px;
  }}
  .container {{ max-width: 560px; margin: 0 auto; }}
  .header {{ text-align: center; margin-bottom: 32px; }}
  .logo {{ font-size: 36px; font-weight: 900; color: #34d399; }}
  .tagline {{ font-size: 11px; color: #64748b; letter-spacing: 0.2em; margin-top: 4px; text-transform: uppercase; }}
  .page-title {{ font-size: 20px; font-weight: 700; margin-top: 12px; color: #f1f5f9; }}
  .card {{
    background: #111f35;
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
  }}
  .section-title {{
    font-size: 10px; font-weight: 800; text-transform: uppercase;
    letter-spacing: .15em; color: #34d399;
    margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid rgba(255,255,255,.08);
  }}
  .label {{
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .2em; color: #64748b; margin-bottom: 10px;
  }}
  .btn-group {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .btn {{
    background: rgba(0,0,0,.2);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 8px; color: #94a3b8;
    font-family: inherit; font-size: 12px; font-weight: 700;
    padding: 8px 16px; cursor: pointer; transition: all .15s;
  }}
  .btn.active {{
    background: rgba(45,143,111,.18);
    border-color: rgba(45,143,111,.35);
    color: #34d399;
  }}
  .slider-wrap {{ padding: 8px 0 16px; }}
  input[type=range] {{
    width: 100%; -webkit-appearance: none;
    height: 4px; background: rgba(255,255,255,.1);
    border-radius: 2px; outline: none;
  }}
  input[type=range]::-webkit-slider-thumb {{
    -webkit-appearance: none; width: 18px; height: 18px;
    border-radius: 50%; background: #34d399; cursor: pointer;
  }}
  .score-val {{ color: #34d399; font-size: 18px; font-weight: 800; margin-top: 4px; }}
  .watchlist-row {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  input[type=text] {{
    background: rgba(0,0,0,.3); border: 1px solid rgba(255,255,255,.08);
    border-radius: 8px; color: #f1f5f9; font-family: inherit;
    font-size: 13px; padding: 10px 14px; width: 160px;
    text-transform: uppercase; outline: none;
  }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 6px; min-height: 24px; }}
  .tag {{
    background: rgba(0,0,0,.2); border: 1px solid rgba(255,255,255,.08);
    border-radius: 6px; color: #f1f5f9; font-size: 12px;
    padding: 4px 10px; display: flex; align-items: center; gap: 6px;
  }}
  .tag-x {{ color: #f87171; cursor: pointer; font-size: 14px; }}
  .hours-row {{ display: flex; align-items: center; gap: 16px; }}
  .hours-info {{ flex: 1; }}
  .hours-title {{ font-size: 13px; font-weight: 600; color: #f1f5f9; }}
  .hours-sub {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
  .save-btn {{
    width: 100%; background: #2d8f6f; border: none; border-radius: 12px;
    color: #fff; font-family: inherit; font-size: 14px; font-weight: 800;
    padding: 16px; cursor: pointer; margin-bottom: 12px; transition: opacity .15s;
  }}
  .save-btn:hover {{ opacity: .85; }}
  .status {{ text-align: center; font-size: 13px; min-height: 20px; margin-bottom: 24px; }}
  .back {{ display: block; text-align: center; color: #64748b; font-size: 12px; text-decoration: none; margin-top: 16px; }}
  .back:hover {{ color: #34d399; }}
  .empty {{ font-size: 12px; color: #64748b; font-style: italic; }}
  #loading {{ text-align: center; color: #64748b; padding: 40px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="logo">Σ</div>
    <div class="tagline">Sigmalytic Quant Corporation</div>
    <div class="page-title">Alert Preferences</div>
  </div>

  <div id="loading">Loading your preferences…</div>
  <div id="main" style="display:none">

    <!-- Delivery Mode -->
    <div class="card">
      <div class="section-title">📬 Delivery Mode</div>
      <div class="label">How often do you want alerts?</div>
      <div class="btn-group" id="mode-group">
        <button class="btn active" data-val="realtime" onclick="setMode(this)">Real-time</button>
        <button class="btn" data-val="hourly" onclick="setMode(this)">Hourly Digest</button>
        <button class="btn" data-val="daily" onclick="setMode(this)">Daily Summary</button>
      </div>
    </div>

    <!-- Min Score -->
    <div class="card">
      <div class="section-title">🎯 Minimum Confluence Score</div>
      <div class="label">Only alert when score is at least:</div>
      <div class="slider-wrap">
        <input type="range" id="score-slider" min="0" max="100" step="5" value="60"
               oninput="document.getElementById('score-val').textContent=this.value">
      </div>
      <div class="score-val" id="score-val">60</div>
      <div style="font-size:11px;color:#64748b;margin-top:4px;">Higher = fewer, higher-quality alerts</div>
    </div>

    <!-- Alert Types -->
    <div class="card">
      <div class="section-title">⚡ Alert Types</div>
      <div class="label">Select any combination — or activate all:</div>
      <div class="btn-group">
        <button class="btn" onclick="setAllTypes(true)">✓ All</button>
        <button class="btn" onclick="setAllTypes(false)">✗ None</button>
        <button class="btn active" data-type="wyckoff"   onclick="toggleType(this)">Structure Alerts</button>
        <button class="btn active" data-type="gann"      onclick="toggleType(this)">Vector Alerts</button>
        <button class="btn active" data-type="ab_score"  onclick="toggleType(this)">Score Alerts</button>
        <button class="btn"        data-type="elliott"   onclick="toggleType(this)">Cycle Alerts</button>
        <button class="btn"        data-type="fibonacci" onclick="toggleType(this)">Level Alerts</button>
      </div>
    </div>

    <!-- Watchlist -->
    <div class="card">
      <div class="section-title">📋 Watchlist</div>
      <div class="label">Only alert on these symbols (leave empty for all 1,403)</div>
      <div class="watchlist-row">
        <input type="text" id="sym-input" placeholder="e.g. AAPL" maxlength="5"
               onkeydown="if(event.key==='Enter')addSymbol()">
        <button class="btn active" onclick="addSymbol()">Add</button>
      </div>
      <div class="tags" id="watchlist-tags">
        <span class="empty">All symbols — no filter applied</span>
      </div>
    </div>

    <!-- Market Hours -->
    <div class="card">
      <div class="section-title">🕐 Market Hours</div>
      <div class="hours-row">
        <div class="hours-info">
          <div class="hours-title">Market hours only</div>
          <div class="hours-sub">Suppress alerts outside 9:30–4:00 PM ET</div>
        </div>
        <button class="btn active" id="hours-btn" onclick="toggleHours()">ON</button>
      </div>
    </div>

    <button class="save-btn" onclick="savePrefs()">Save Preferences</button>
    <div class="status" id="status"></div>
  </div>

  <a class="back" href="https://sigmalytic-frontend.onrender.com">← Back to Sigmalytic</a>
</div>

<script>
const USER_ID = "{user_id}";
const BACKEND = "";  // same origin
let watchlist = [];
let hoursOn = true;

// ── Load ──────────────────────────────────────────────────────────────────────
async function loadPrefs() {{
  if (!USER_ID) {{
    document.getElementById('loading').textContent = 'No user ID. Please log in first.';
    return;
  }}
  try {{
    const r = await fetch('/api/preferences/' + USER_ID);
    if (r.ok) {{
      const p = await r.json();
      applyPrefs(p);
    }}
  }} catch(e) {{
    console.warn('Could not load prefs:', e);
  }}
  document.getElementById('loading').style.display = 'none';
  document.getElementById('main').style.display = 'block';
}}

function applyPrefs(p) {{
  // Mode
  if (p.delivery_mode) {{
    document.querySelectorAll('#mode-group .btn').forEach(b => {{
      b.classList.toggle('active', b.dataset.val === p.delivery_mode);
    }});
  }}
  // Score
  if (p.min_score !== undefined) {{
    document.getElementById('score-slider').value = p.min_score;
    document.getElementById('score-val').textContent = p.min_score;
  }}
  // Types
  if (p.alert_types) {{
    document.querySelectorAll('[data-type]').forEach(b => {{
      b.classList.toggle('active', p.alert_types.includes(b.dataset.type));
    }});
  }}
  // Watchlist
  if (p.watchlist && p.watchlist.length > 0) {{
    watchlist = p.watchlist;
    renderWatchlist();
  }}
  // Hours
  if (p.market_hours_only !== undefined) {{
    hoursOn = p.market_hours_only;
    updateHoursBtn();
  }}
}}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setMode(el) {{
  document.querySelectorAll('#mode-group .btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}}

function toggleType(el) {{ el.classList.toggle('active'); }}

function setAllTypes(val) {{
  document.querySelectorAll('[data-type]').forEach(b => b.classList.toggle('active', val));
}}

function toggleHours() {{
  hoursOn = !hoursOn;
  updateHoursBtn();
}}

function updateHoursBtn() {{
  const btn = document.getElementById('hours-btn');
  btn.textContent = hoursOn ? 'ON' : 'OFF';
  btn.classList.toggle('active', hoursOn);
}}

function addSymbol() {{
  const input = document.getElementById('sym-input');
  const sym = input.value.trim().toUpperCase();
  if (!sym || watchlist.includes(sym)) {{ input.value = ''; return; }}
  watchlist.push(sym);
  input.value = '';
  renderWatchlist();
}}

function removeSymbol(sym) {{
  watchlist = watchlist.filter(s => s !== sym);
  renderWatchlist();
}}

function renderWatchlist() {{
  const container = document.getElementById('watchlist-tags');
  if (!watchlist.length) {{
    container.innerHTML = '<span class="empty">All symbols — no filter applied</span>';
    return;
  }}
  container.innerHTML = watchlist.map(s =>
    `<div class="tag">${{s}}<span class="tag-x" onclick="removeSymbol('${{s}}')">×</span></div>`
  ).join('');
}}

// ── Save ──────────────────────────────────────────────────────────────────────
async function savePrefs() {{
  const status = document.getElementById('status');
  status.style.color = '#94a3b8';
  status.textContent = 'Saving…';

  const mode = document.querySelector('#mode-group .btn.active')?.dataset.val || 'realtime';
  const score = parseInt(document.getElementById('score-slider').value);
  const types = [...document.querySelectorAll('[data-type].active')].map(b => b.dataset.type);

  const payload = {{
    delivery_mode: mode,
    min_score: score,
    alert_types: types,
    watchlist: watchlist,
    market_hours_only: hoursOn,
  }};

  try {{
    let r = await fetch('/api/preferences/' + USER_ID, {{
      method: 'PATCH',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload),
    }});
    if (r.status === 404) {{
      r = await fetch('/api/preferences/' + USER_ID, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{...payload, user_id: USER_ID, email: USER_ID}}),
      }});
    }}
    if (r.ok) {{
      status.style.color = '#34d399';
      status.textContent = '✅ Preferences saved!';
    }} else {{
      const err = await r.json();
      status.style.color = '#f87171';
      status.textContent = '❌ ' + (err.detail || 'Save failed');
    }}
  }} catch(e) {{
    status.style.color = '#f87171';
    status.textContent = '❌ ' + e.message;
  }}
}}

loadPrefs();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


