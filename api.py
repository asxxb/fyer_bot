#!/usr/bin/env python3
"""
api.py — FastAPI backend for FYERS Trading Bot
Provides API endpoints + Jinja2 dashboard UI
"""
import os
import sys
import json
import csv
import threading
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from utils.logger import get_logger

log = get_logger(level=settings.LOG_LEVEL)

# ============================================================
# FastAPI App Setup
# ============================================================

app = FastAPI(
    title="FYERS Trading Bot API",
    description="Lightweight API for intraday trading bot",
    version="2.0.0",
)

# Lock for thread-safe access
_data_lock = threading.RLock()

# In-memory state (thread-safe via lock)
_bot_state = {
    "running": False,
    "mode": "paper",
    "current_symbol": None,
    "websocket_connected": False,
    "active_trade": None,
}

# ============================================================
# Helper Functions (Thread-Safe)
# ============================================================

def _get_data_dir() -> Path:
    """Get data directory path."""
    return PROJECT_ROOT / "data"


def _read_status_file() -> dict:
    """Read status.json safely."""
    status_file = _get_data_dir() / "status.json"
    try:
        with open(status_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_journal_today() -> list:
    """Read today's journal CSV."""
    today = datetime.now().strftime("%Y-%m-%d")
    journal_file = _get_data_dir() / f"journal_{today}.csv"
    
    trades = []
    try:
        if journal_file.exists():
            with open(journal_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("pnl"):
                        row["pnl"] = float(row["pnl"])
                    trades.append(row)
    except Exception as e:
        log.warning(f"Failed to read journal: {e}")
    
    return trades


def _read_trades_history() -> list:
    """Read full trades history from today's journal + trades.csv."""
    trades = []
    
    # First read today's journal
    today_trades = _read_journal_today()
    
    # Normalize journal fields
    for t in today_trades:
        trades.append({
            "exit_time": t.get("exit_time", ""),
            "symbol": t.get("symbol", ""),
            "side": t.get("side", ""),
            "qty": t.get("qty", ""),
            "entry_price": t.get("entry_price", ""),
            "exit_price": t.get("exit_price", ""),
            "pnl": t.get("pnl", 0),
            "exit_reason": t.get("exit_reason", ""),
        })
    
    # Also read trades.csv for historical
    trades_file = _get_data_dir() / "trades.csv"
    
    try:
        if trades_file.exists():
            with open(trades_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pnl = 0
                    try:
                        pnl = float(row.get("pnl", 0))
                    except:
                        pass
                    
                    # Map trades.csv fields to journal format
                    # trades.csv now includes symbol (added to backtest.py)
                    trades.append({
                        "exit_time": row.get("date", ""),
                        "symbol": row.get("symbol", ""),
                        "side": row.get("side", ""),
                        "qty": row.get("qty", ""),
                        "entry_price": row.get("entry", ""),
                        "exit_price": row.get("exit", ""),
                        "pnl": pnl,
                        "exit_reason": row.get("hit", ""),
                    })
    except Exception as e:
        log.warning(f"Failed to read trades: {e}")
    
    return trades


def _calculate_metrics(trades: list) -> dict:
    """Calculate performance metrics from trades."""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }
    
    # Filter valid trades
    valid_trades = [t for t in trades if "pnl" in t and t["pnl"] not in (None, "", 0)]
    
    if not valid_trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }
    
    pnls = [t["pnl"] for t in valid_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    
    total_trades = len(valid_trades)
    win_count = len(wins)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    
    total_pnl = sum(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    
    # Expectancy: (win% × avg_win) + (loss% × avg_loss)
    win_pct = win_rate / 100
    loss_pct = 1 - win_pct
    expectancy = (win_pct * avg_win) + (loss_pct * avg_loss)
    
    # Profit Factor: total wins / |total losses|
    wins_sum = sum(wins)
    losses_sum = abs(sum(losses))
    profit_factor = wins_sum / losses_sum if losses_sum > 0 else 0.0
    
    # Max Drawdown (cumulative)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    
    sorted_trades = sorted(valid_trades, key=lambda x: x.get("exit_time", ""))
    for t in sorted_trades:
        equity += t["pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    
    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }


def _update_bot_state():
    """Update bot state from config and files."""
    with _data_lock:
        _bot_state["mode"] = "paper" if settings.PAPER_TRADE else "live"
        
        # Read from status file
        status = _read_status_file()
        _bot_state["running"] = status.get("bot_status") == "RUNNING"
        _bot_state["current_symbol"] = status.get("active_trade", None)
        
        # Try to read active trade from tracker
        active_trade_file = _get_data_dir() / "active_trade.json"
        if active_trade_file.exists():
            try:
                with open(active_trade_file, "r") as f:
                    _bot_state["active_trade"] = json.load(f)
            except:
                _bot_state["active_trade"] = None
        else:
            _bot_state["active_trade"] = None


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
async def dashboard():
    """Serve the dashboard HTML."""
    return FileResponse(
        str(PROJECT_ROOT / "templates" / "dashboard.html"),
        media_type="text/html"
    )


@app.get("/api/status")
async def get_status():
    """
    Get bot status:
    - mode: paper/live
    - current_symbol: active symbol or None
    - websocket_status: connected/disconnected
    """
    _update_bot_state()
    
    return {
        "mode": _bot_state["mode"],
        "current_symbol": _bot_state["current_symbol"],
        "websocket_status": "connected" if _bot_state.get("websocket_connected") else "disconnected",
        "bot_running": _bot_state["running"],
    }


@app.get("/api/profile")
async def get_profile():
    """
    Get FYERS user profile:
    - name, email, mobile, DPid, broker name
    Uses cached session from bot.
    """
    try:
        from fyers_apiv3 import fyersModel
        from config import settings
        
        if not settings.FYERS_ACCESS_TOKEN:
            return {"success": False, "error": "No access token"}
        
        # Create fyers session (use 'token' not 'access_token')
        fyers = fyersModel.FyersModel(
            client_id=settings.FYERS_APP_ID,
            is_async=False,
            token=settings.FYERS_ACCESS_TOKEN,
            log_path=''
        )
        
        response = fyers.get_profile()
        
        if response.get('s') != 'ok':
            return {"success": False, "error": response.get('message', 'Failed')}
        
        data = response.get('data', {})
        
        # Return only safe/public info
        return {
            "success": True,
            "name": data.get('name', ''),
            "email": data.get('email_id', ''),
            "mobile": data.get('mobile_number', ''),
            "fy_id": data.get('fy_id', ''),
            "broker": "FYERS",
            "pan": data.get('PAN', ''),
            "pin_change_date": data.get('pin_change_date', ''),
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/trade")
async def get_trade():
    """
    Get active trade details:
    - entry, SL, TP, side, symbol, qty
    Returns null if no active trade.
    """
    _update_bot_state()
    
    active = _bot_state.get("active_trade")
    if not active:
        return {"active": False, "trade": None}
    
    return {
        "active": True,
        "trade": {
            "symbol": active.get("symbol"),
            "side": active.get("side"),
            "qty": active.get("qty"),
            "entry_price": active.get("entry_price"),
            "stop_loss": active.get("stop_loss"),
            "target": active.get("target"),
            "entry_time": active.get("entry_time"),
        }
    }


@app.get("/api/pnl")
async def get_pnl():
    """
    Get PnL data:
    - realized_pnl: total realized PnL today
    - trades_today: number of trades today
    - max_loss: daily loss limit
    """
    # Get today's trades
    trades = _read_journal_today()
    
    realized_pnl = sum(t.get("pnl", 0.0) for t in trades)
    trades_today = len(trades)
    
    return {
        "realized_pnl": round(realized_pnl, 2),
        "trades_today": trades_today,
        "max_loss": -settings.MAX_DAILY_LOSS,
    }


@app.get("/api/metrics")
async def get_metrics():
    """
    Get performance metrics:
    - win_rate, total_pnl, expectancy, profit_factor, max_drawdown
    Reads from journal CSV.
    """
    trades = _read_trades_history()
    metrics = _calculate_metrics(trades)
    
    # Add today's stats
    today_trades = _read_journal_today()
    today_pnl = sum(t.get("pnl", 0.0) for t in today_trades)
    metrics["today_pnl"] = round(today_pnl, 2)
    metrics["today_trades"] = len(today_trades)
    
    return metrics


@app.get("/api/health")
async def health_check():
    """Health check - returns bot running status."""
    _update_bot_state()
    
    return {
        "healthy": True,
        "bot_running": _bot_state["running"],
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# Optional: Mode Switching Endpoint
# ============================================================

@app.post("/api/mode")
async def set_mode(request: Request):
    """
    Switch between paper/live mode.
    Usage: POST /api/mode with body {"mode": "paper"} or {"mode": "live"}
    """
    try:
        body = await request.json()
        mode = body.get("mode", "paper")
    except:
        mode = "paper"
    
    if mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="Mode must be 'paper' or 'live'")
    
    settings.set_paper_trade_mode(mode == "paper")
    _update_bot_state()
    
    return {
        "success": True,
        "mode": mode,
    }


@app.get("/api/latest-trades")
async def get_latest_trades(limit: int = 5):
    """Get recent trades."""
    trades = _read_trades_history()
    
    # Sort by exit_time descending
    trades_sorted = sorted(
        trades,
        key=lambda x: x.get("exit_time", ""),
        reverse=True
    )
    
    return trades_sorted[:limit]


@app.get("/api/equity-data")
async def get_equity_data():
    """Get equity curve data for chart."""
    equity_file = _get_data_dir() / "equity.csv"
    
    data = []
    try:
        if equity_file.exists():
            with open(equity_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "capital" in row and "time" in row:
                        data.append({
                            "time": row["time"],
                            "capital": float(row["capital"])
                        })
    except Exception as e:
        log.warning(f"Failed to read equity: {e}")
    
    return {"data": data[-50:]}  # Last 50 points


@app.get("/api/scanner")
async def get_scanner_results():
    """Get scanner results including current best stock."""
    scanner_file = _get_data_dir() / "scanner_results.json"
    
    try:
        if scanner_file.exists():
            with open(scanner_file, "r") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Failed to read scanner: {e}")
    
    return {"results": [], "current_best": None, "last_scan": None}


@app.get("/api/current-stock")
async def get_current_stock():
    """Get the current best stock being monitored."""
    _update_bot_state()
    
    # Read from scanner results
    scanner_file = _get_data_dir() / "scanner_results.json"
    
    try:
        if scanner_file.exists():
            with open(scanner_file, "r") as f:
                data = json.load(f)
                return data.get("current_best", None)
    except Exception:
        pass
    
    return None


@app.post("/api/fetch-data")
async def fetch_stock_data(request: Request):
    """Fetch stock data via FYERS API."""
    try:
        body = await request.json()
        stock = body.get("stock", "SBIN")
    except:
        stock = "SBIN"
    
    # Get token directly from .env
    import os
    from dotenv import load_dotenv
    load_dotenv()
    access_token = os.getenv('FYERS_ACCESS_TOKEN', '')
    app_id = os.getenv('FYERS_APP_ID', '')
    
    if not access_token or not app_id:
        return {"success": False, "error": "Missing FYERS credentials"}
    
    try:
        from fyers_apiv3 import fyersModel
        
        # Init fyers directly with token
        fyers = fyersModel.FyersModel(
            client_id=app_id,
            is_async=False,
            token=access_token,
            log_path=''
        )
        
        profile = fyers.get_profile()
        if profile.get('s') != 'ok':
            return {"success": False, "error": f"FYERS auth failed"}
        
        symbol = f"{stock.upper()}-EQ"
        
        # Fetch candles using fyers directly
        from datetime import datetime, timedelta
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=1)
        
        response = fyers.history({
            "symbol": f"NSE:{symbol}",
            "resolution": "5",
            "date_format": "1",
            "range_from": start_dt.strftime("%Y-%m-%d"),
            "range_to": end_dt.strftime("%Y-%m-%d"),
            "cont_flag": "1"
        })
        
        if response.get("s") != "ok":
            return {"success": False, "error": f"History API error: {response}"}
        
        candles = response.get("candles", [])
        if not candles:
            return {"success": False, "error": "No candles returned"}
        
        # Convert to DataFrame
        import pandas as pd
        rows = []
        for c in candles:
            rows.append({
                "datetime": datetime.fromtimestamp(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": int(c[5]) if len(c) > 5 else 0,
            })
        
        df = pd.DataFrame(rows)
        df = df.sort_values("datetime")
        df = df.reset_index(drop=True)
        
        # Save to CSV
        filename = _get_data_dir() / f"candles_{stock.upper()}_EQ.csv"
        df.to_csv(filename, index=False)
        
        return {"success": True, "candles": len(df)}
        
    except ImportError as e:
        return {"success": False, "error": f"Import error: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/backtest")
async def run_backtest(request: Request):
    """Run backtest on a stock."""
    try:
        body = await request.json()
        stock = body.get("stock", "SBIN")
    except:
        stock = "SBIN"
    
    try:
        import subprocess
        
        result = subprocess.run(
            ["python", "backtest.py", "--symbol", f"{stock}-EQ", "--use-cached"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT)
        )
        
        if result.returncode == 0:
            return {"success": True, "output": result.stdout}
        else:
            return {"success": False, "error": result.stderr or "Backtest failed"}
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Backtest timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Main entry point for development
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)