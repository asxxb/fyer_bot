# FastAPI Dashboard - Architecture & Instructions

## Overview

This refactoring replaces Streamlit with a lightweight FastAPI + Jinja2 solution suitable for VPS deployment.

### Architecture

```
shoonya_bot/
├── main.py           # Bot entry point (runs standalone)
├── api.py            # FastAPI backend + serves HTML
├── templates/
│   └── dashboard.html    # Server-rendered HTML dashboard
├── data/
│   ├── status.json       # Bot status (written by main.py)
│   ├── active_trade.json # Active trade (written by tracker)
│   ├── trades.csv       # Trade history
│   ├── journal_YYYY-MM-DD.csv  # Daily journal
│   └── equity.csv      # Equity curve
├── core/
│   ├── engine.py     # Trading engine (unchanged)
│   ├── trade_tracker.py
│   ├── risk_manager.py
│   └── broker.py
├── config/
│   └── settings.py
└── requirements.txt    # Added fastapi, uvicorn, jinja2
```

## How It Works

### 1. Bot Running (Headless)
- `python main.py` - Runs TradingEngine in background loop
- Maintains `data/status.json` for status sharing
- Uses existing `data/active_trade.json` for crash recovery

### 2. API Server (`api.py`)
- Runs on FastAPI (async)
- Reads bot state from JSON files
- Thread-safe data access via lock
- Provides JSON APIs for dashboard

### 3. Dashboard (`dashboard.html`)
- Server-rendered by Jinja2
- Vanilla JS with fetch() API
- Auto-refresh every 3 seconds
- No React, no frameworks

## Installation

```bash
# Install new dependencies
pip install -r requirements.txt
```

## Running

### Option 1: Separate Processes (Recommended for Development)

**Terminal 1 - Bot only:**
```bash
python main.py
```

**Terminal 2 - API only:**
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

### Option 2: Combined (Bot + API in one process)
```bash
python main.py --api
```

## Access

- Dashboard: http://localhost:8000/
- API Status: http://localhost:8000/api/status
- API Trade: http://localhost:8000/api/trade
- API PnL: http://localhost:8000/api/pnl
- API Metrics: http://localhost:8000/api/metrics
- API Health: http://localhost:8000/api/health

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|------------|
| `/` | GET | Render dashboard HTML |
| `/api/status` | GET | Bot mode, symbol, WS status |
| `/api/trade` | GET | Active trade details |
| `/api/pnl` | GET | Realized P&L, trades today |
| `/api/metrics` | GET | Win rate, PF, expectancy |
| `/api/health` | GET | Health check |
| `/api/latest-trades` | GET | Recent trades (limit=N) |
| `/api/mode` | POST | Switch paper/live |

## Security Considerations

### Optional: API Token Authentication

To add basic auth, wrap the API with a Bearer token:

```python
# In api.py, add:
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

@app.get("/api/status")
async def get_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != "your-secret-token":
        raise HTTPException(401, "Invalid token")
    ...
```

Then in JavaScript:
```javascript
fetch('/api/status', {
    headers: { 'Authorization': 'Bearer your-secret-token' }
})
```

### Firewall (Production)

```bash
# Allow only your IP
ufw allow from YOUR_IP to any port 8000
```

Or use nginx with basic auth.

## Performance

- Memory: ~30-50MB (vs 200MB+ for Streamlit)
- CPU: Minimal (JSON file reads)
- Network: ~5KB per refresh
- VPS: Works on $5/mo instance

## Error Handling

The API handles gracefully:
- Missing journal file → Returns empty metrics
- Malformed JSON → Returns defaults
- Bot stopped → Shows "Stopped" status
- No active trade → Shows "No open trade"

## Dashboard Features

1. **Mode Badge** - PAPER (yellow) / LIVE (red)
2. **Live P&L** - Today's realized P&L with color
3. **Active Trade** - Entry, SL, TP, side, qty
4. **Risk Summary** - Daily loss limit
5. **PerformanceMetrics** - Win rate, PF, expectancy, total trades
6. **Recent Trades** - Last 5 trades table
7. **Auto-refresh** - Every 3 seconds via setInterval
8. **Retry Logic** - 5 retries with backoff on fetch failures

## File Descriptions

### api.py (345 lines)

Provides:
- FastAPI app with 7 endpoints
- Thread-safe state management
- Jinja2 template rendering
- Metrics calculation from CSV
- Optional mode switching

### dashboard.html (490 lines)

Features:
- Dark theme matching original Streamlit
- Vanilla JS (no frameworks)
- fetch() with 5s timeout
- setInterval 3s refresh
- Responsive grid layout

### main.py changes (+30 lines)

Added:
- `_write_status()` function
- `run_api()` for combined mode
- `--api` CLI flag
- Status file writing on start/stop

## Migration Notes

- Trading logic unchanged (core/, strategies/)
- TradeTracker writes same JSON/CSV files
- Frontend reimplemented in vanilla HTML/JS
- No database migration needed
- Telegram notifications continue to work