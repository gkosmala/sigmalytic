
# Sigmalytic Quant Corporation
# Futures Market Data Dashboard — Read Only

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sigmalytic | Futures Market Data</title>
<style>
:root {
  color-scheme: dark;
  --bg:#071321;
  --panel:#101f32;
  --line:#263c53;
  --gold:#d9b765;
  --text:#e9f0f8;
  --muted:#9baec2;
  --green:#43d6a0;
  --red:#ff7885;
}
* { box-sizing:border-box; }
body {
  margin:0;
  background:var(--bg);
  color:var(--text);
  font:14px system-ui,Arial,sans-serif;
}
main { max-width:1500px; margin:auto; padding:28px; }
header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  flex-wrap:wrap;
  gap:16px;
  margin-bottom:26px;
}
.brand { display:flex; align-items:center; gap:16px; }
.sigma { font-size:56px; color:var(--gold); }
h1 { margin:0; font-size:24px; letter-spacing:1px; }
.subtitle { color:var(--muted); margin-top:5px; }
.pill {
  border:1px solid var(--line);
  padding:9px 14px;
  border-radius:20px;
}
.cards {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:14px;
  margin-bottom:22px;
}
.card,.panel {
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:12px;
  padding:20px;
}
.label { color:var(--muted); font-size:12px; }
.value { font-size:27px; font-weight:700; margin-top:10px; }
.good { color:var(--green); }
.bad { color:var(--red); }
.gold { color:var(--gold); }
.controls {
  display:flex;
  gap:12px;
  flex-wrap:wrap;
  align-items:center;
  margin-bottom:18px;
}
input,button {
  background:#091728;
  color:var(--text);
  border:1px solid var(--line);
  padding:11px 14px;
  border-radius:8px;
}
input { min-width:260px; flex:1; }
button { cursor:pointer; }
button:hover { border-color:var(--gold); }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th,td {
  padding:13px 12px;
  border-bottom:1px solid var(--line);
  text-align:right;
  white-space:nowrap;
}
th {
  color:var(--gold);
  font-size:12px;
  text-transform:uppercase;
}
th:first-child,td:first-child { text-align:left; }
tbody tr:hover { background:#1b3048; }
small { color:var(--muted); }
.footer { color:var(--muted); margin-top:22px; }
</style>
</head>
<body>
<main>
<header>
  <div class="brand">
    <div class="sigma">Σ</div>
    <div>
      <h1>SIGMALYTIC QUANT CORPORATION</h1>
      <div class="subtitle">Futures Market Intelligence | DXLink</div>
    </div>
  </div>
  <div class="pill" id="connection">Connecting...</div>
</header>

<section class="cards">
  <div class="card">
    <div class="label">Feed Entitlement</div>
    <div class="value gold" id="entitlement">—</div>
  </div>
  <div class="card">
    <div class="label">Subscribed Contracts</div>
    <div class="value" id="subscribed">—</div>
  </div>
  <div class="card">
    <div class="label">Contracts Received</div>
    <div class="value good" id="received">—</div>
  </div>
  <div class="card">
    <div class="label">Subscription Coverage</div>
    <div class="value" id="coverage">—</div>
  </div>
</section>

<section class="panel" style="margin-bottom:22px"><h2 style="color:var(--gold)">Volatility Watchlist</h2><div class="cards" id="vol-watchlist"></div><small>VIX = cash volatility index; VXX = exchange-traded ETN; VX = VIX futures. Missing data is never estimated.</small></section>

<div class="panel">
  <div class="controls">
    <input id="search" placeholder="Search futures symbol..."
           aria-label="Search futures symbol">
    <label><input type="checkbox" id="fresh"> Fresh only</label>
    <button id="refresh">Refresh Now</button>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Contract</th>
          <th>Bid</th>
          <th>Ask</th>
          <th>Spread</th>
          <th>Last Trade</th>
          <th>Day Volume</th>
          <th>Last Received (UTC)</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="rows">
        <tr><td colspan="8">Loading market data...</td></tr>
      </tbody>
    </table>
  </div>
  <p><small id="count">Waiting for data</small></p>
</div>

<div class="footer">
  Source: tastytrade DXLink |
  Read-only market-data monitoring |
  Refresh interval: 5 seconds
  <p>
    No trade execution is available.
  </p>
</div>
</main>

<script>
let allQuotes = {};
let busy = false;

const el = id => document.getElementById(id);

function number(v, digits=2) {
  return typeof v === "number" && Number.isFinite(v)
    ? v.toLocaleString("en-US", {
        minimumFractionDigits:digits,
        maximumFractionDigits:digits
      })
    : "—";
}

function cell(value, cls="") {
  const td = document.createElement("td");
  td.textContent = String(value);
  if (cls) td.className = cls;
  return td;
}

function render() {
  const search = el("search").value.trim().toUpperCase();
  const freshOnly = el("fresh").checked;
  const body = el("rows");
  body.replaceChildren();

  const matches = Object.entries(allQuotes)
    .filter(([symbol, q]) =>
      symbol.toUpperCase().includes(search) &&
      (!freshOnly || !q.stale)
    )
    .sort((a,b) => a[0].localeCompare(b[0]));

  for (const [symbol, q] of matches) {
    const quote = q.quote || {};
    const trade = q.trade || {};
    const bid = quote.bidPrice;
    const ask = quote.askPrice;
    const spread =
      typeof bid === "number" && typeof ask === "number"
        ? ask - bid : null;

    const tr = document.createElement("tr");
    tr.append(
      cell(symbol),
      cell(number(bid)),
      cell(number(ask)),
      cell(number(spread)),
      cell(number(trade.price)),
      cell(number(trade.dayVolume,0)),
      cell(q.received_at || "—"),
      cell(q.stale ? "STALE" : "FRESH",
           q.stale ? "bad" : "good")
    );
    body.appendChild(tr);
  }

  if (!matches.length) {
    const tr = document.createElement("tr");
    const td = cell("No matching received contracts");
    td.colSpan = 8;
    tr.appendChild(td);
    body.appendChild(tr);
  }

  el("count").textContent =
    `${matches.length} contracts displayed`;
}

async function refresh() {
  if (busy) return;
  busy = true;

  try {
    const [statusResponse,quotesResponse] = await Promise.all([
      fetch("/api/futures/status",{cache:"no-store"}),
      fetch("/api/futures/quotes?limit=500",{cache:"no-store"})
    ]);

    if (!statusResponse.ok || !quotesResponse.ok) {
      throw new Error("Market-data API unavailable");
    }

    const status = await statusResponse.json();
    const data = await quotesResponse.json();

    el("connection").textContent =
      status.stream_connected && status.stream_authorized
        ? "● CONNECTED" : "● DISCONNECTED";

    el("connection").className =
      "pill " + (status.stream_connected &&
        status.stream_authorized ? "good" : "bad");

    el("entitlement").textContent =
      (status.entitlement_level || "Unknown").toUpperCase();
    el("subscribed").textContent =
      number(status.subscribed_symbols,0);
    el("received").textContent =
      number(status.received_symbols,0);
    el("coverage").textContent =
      number(status.coverage_percent) + "%";

    allQuotes = data.quotes || {};
    render();
    volatilityWatchlist();
    // Cash VIX uses DXLink data.
  } catch (error) {
    el("connection").textContent = "● API ERROR";
    el("connection").className = "pill bad";
    el("count").textContent = error.message;
  } finally {
    busy = false;
  }
}

el("search").addEventListener("input",render);
el("fresh").addEventListener("change",render);
el("refresh").addEventListener("click",refresh);


// SIGMALYTIC VOLATILITY WATCHLIST V1
function volatilityWatchlist() {
  const container = el('vol-watchlist');
  container.replaceChildren();
  const instruments = [
    {name:'VIX',type:'Cboe Cash Volatility Index',root:'VIX'},
    {name:'VXX',type:'VIX Short-Term Futures ETN',root:'VXX'},
    {name:'VX Futures',type:'Cboe Volatility Futures',root:'VX'}
  ];
  for (const item of instruments) {
    const entries = Object.entries(allQuotes).filter(([symbol]) => item.root && (item.root===String.fromCharCode(86,73,88) ? symbol===String.fromCharCode(86,73,88) : item.root===String.fromCharCode(86,88,88) ? symbol===String.fromCharCode(86,88,88) : symbol.startsWith(String.fromCharCode(47,86,88))));
    const active = entries.find(([symbol,q]) => !q.stale) || entries[0];
    const q = active ? active[1] : null;
    const price = q ? (q.trade?.price ?? q.quote?.bidPrice ?? null) : null;
    const card = document.createElement('div');
    card.className = 'card';
    const heading = document.createElement('div'); heading.className='label'; heading.textContent=item.name+' | '+item.type;
    const value = document.createElement('div'); value.className='value'; value.textContent=price === null ? 'NO DATA' : number(price);
    const note = document.createElement('small'); note.textContent=active ? active[0]+' | '+(q.stale?'STALE':'FRESH') : 'Feed not available in current futures stream';
    card.append(heading,value,note); container.appendChild(card);
  }
}


// SIGMALYTIC VIX VXX FETCH V1
async function updateCashVolatility() {
  try {
    const response=await fetch('/api/futures/volatility',{cache:'no-store'});
    if (!response.ok) return;
    const data=await response.json();
    for (const card of el('vol-watchlist').querySelectorAll('.card')) {
      const name=card.querySelector('.label')?.textContent?.split(' | ')[0];
      if (name!=='VIX') continue;
      const q=data.quotes?.[name];
      const raw=q?.last ?? q?.mark ?? q?.bid;
      const price=raw===null || raw===undefined || raw==='' ? null : Number(raw);
      const value=card.querySelector('.value');
      const note=card.querySelector('small');
      value.textContent=price!==null && Number.isFinite(price) ? number(price) : 'NO DATA';
      note.textContent=q ? 'tastytrade | '+(q.updated_at || 'Timestamp unavailable') : (data.error || 'Quote unavailable under current entitlement');
    }
  } catch (error) { console.warn('Volatility data unavailable'); }
}

refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
"""


@router.get("/api/futures/dashboard", response_class=HTMLResponse)
def futures_dashboard():
    return HTMLResponse(PAGE)
