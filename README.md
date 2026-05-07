# Sigmalytic — Decision Intelligence Platform
### Institutional-Grade MVP · Python · FastAPI + Dash + Alpaca

---

## Project Structure

```
sigmalytic/
├── shared/
│   └── engine.py          # Core decision logic (shared by backend + frontend)
├── backend/
│   └── main.py            # FastAPI — REST + WebSocket + Alpaca stream
├── frontend/
│   └── app.py             # Dash — Plotly chart, real-time UI
├── requirements.txt
├── .env.example
└── README.md
```

---

## Local Development

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up environment variables
```bash
cp .env.example .env
# Edit .env and add your Alpaca API key + secret
```

### 3. Start the backend
```bash
uvicorn backend.main:app --reload --port 8000
```

### 4. Start the frontend (new terminal)
```bash
python frontend/app.py
# Open http://localhost:8050
```

---

## Alpaca Setup

1. Create a free account at https://alpaca.markets
2. Go to **Paper Trading** → **API Keys** → Generate new key
3. Paste `ALPACA_API_KEY` and `ALPACA_API_SECRET` into your `.env`
4. Free IEX feed gives ~15min delayed data
5. Upgrade to **Alpaca Unlimited** ($9/mo) for real-time SIP feed

---

## Deployment (Render)

### Backend service
| Setting       | Value                              |
|---------------|------------------------------------|
| Runtime       | Python 3.11                        |
| Build command | `pip install -r requirements.txt`  |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Env vars      | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER`  |

### Frontend service
| Setting       | Value                              |
|---------------|------------------------------------|
| Runtime       | Python 3.11                        |
| Build command | `pip install -r requirements.txt`  |
| Start command | `gunicorn frontend.app:server -b 0.0.0.0:$PORT`        |
| Env vars      | `BACKEND_URL=https://your-backend.onrender.com`         |
|               | `BACKEND_WS_URL=wss://your-backend.onrender.com`        |

---

## API Reference

| Method | Endpoint                  | Description                        |
|--------|---------------------------|------------------------------------|
| GET    | `/api/health`             | Health check + stream status       |
| GET    | `/api/stock/{symbol}`     | Latest quote + decision output     |
| GET    | `/api/candles/{symbol}`   | OHLCV bars (default: 1Min, 50 bars)|
| WS     | `/ws/{symbol}`            | Real-time tick stream              |

---

## Architecture

```
Alpaca WebSocket ──► FastAPI backend ──► /ws/{symbol} ──► Dash frontend
                           │
                    Alpaca REST API ──► /api/stock/{symbol}
                                   ──► /api/candles/{symbol}
```

- **One Alpaca WS connection per symbol** — shared across all connected clients
- **Auto-reconnect** with exponential backoff on stream disconnect
- **Synthetic fallback** — UI stays live even without API key (dev mode)
- **Plotly chart** — interactive zoom, pan, hover with live level overlays

---

## Next Steps (Post-MVP)

- [ ] JWT authentication (FastAPI Users)
- [ ] Multi-user firm accounts (PostgreSQL)
- [ ] Real options flow (Tradier API)
- [ ] PDF report export (WeasyPrint)
- [ ] Audit logging (structured JSON logs → S3)
- [ ] Role-based access (admin / trader / viewer)
- [ ] Alert webhooks (Slack, email, SMS via Twilio)
