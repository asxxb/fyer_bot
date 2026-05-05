#!/usr/bin/env python3
"""
main.py — Entry point for the FYERS Intraday Trading Bot
"""
import sys
import os
import json
import signal
from datetime import datetime
from utils.telegram import telegram
# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import get_logger
from config import settings

log = get_logger(level=settings.LOG_LEVEL)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")


def _write_status(bot_status="RUNNING", active_trade=None):
    """Write status to file for API consumption."""
    status = {
        "bot_status": bot_status,
        "capital": settings.CAPITAL,
        "active_trade": active_trade,
        "last_update": datetime.now().isoformat()
    }
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to write status: {e}")


def check_mode():
    """Quick sanity check: login + fetch one quote."""
    log.info("Running connection check...")
    from core.broker import FyersBroker
    broker = FyersBroker()
    
    if not broker.access_token:
        log.info("No access token. Generating auth URL...")
        broker.generate_auth_url()
        log.info("Steps:")
        log.info("  1. Open the URL above in your browser")
        log.info("  2. Login and authorize")
        log.info("  3. Copy the 'code' from redirect URL")
        log.info("  4. Run: python main.py --login <code>")
        return
    
    if not broker.login():
        log.error("❌ Login failed. Check FYERS credentials.")
        sys.exit(1)
    
    # Save access token to .env
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    try:
        lines = []
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("FYERS_ACCESS_TOKEN="):
                        lines.append(f"FYERS_ACCESS_TOKEN={broker.access_token}\n")
                    else:
                        lines.append(line)
        if not any(l.startswith("FYERS_ACCESS_TOKEN=") for l in lines):
            lines.append(f"FYERS_ACCESS_TOKEN={broker.access_token}\n")
        with open(env_file, "w") as f:
            f.writelines(lines)
        log.info("✅ Access token saved to .env")
    except Exception as e:
        log.warning(f"Could not save token: {e}")
    
    ltp = broker.get_ltp()
    if ltp:
        log.info(f"✅ Market data OK | {settings.SYMBOL} LTP = ₹{ltp:.2f}")
    else:
        log.warning("⚠️  LTP returned None — market may be closed.")
    candles = broker.get_candles(lookback_days=2)
    log.info(f"✅ Candles fetched: {len(candles)} rows")
    log.info("Check complete.")


def run_api():
    """Run both bot and API server in one process."""
    import threading
    
    # Start bot in background thread
    def run_bot_thread():
        from core.engine import TradingEngine
        engine = TradingEngine()
        _write_status("RUNNING", settings.SYMBOL)
        
        try:
            engine.start()
        except Exception as e:
            _write_status("STOPPED", None)
            log.error(f"Bot crashed: {e}")
    
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
    bot_thread.start()
    
    # Run API in main thread
    import uvicorn
    log.info("Starting API server on http://0.0.0.0:8000")
    uvicorn.run("api:app", host="0.0.0.0", port=8000)


def run_bot():

    from core.engine import TradingEngine

    engine = TradingEngine()

    telegram.send(

        "🤖 *Algo Bot Started*\n\n"

        f"Mode: {'🟡 PAPER' if settings.PAPER_TRADE else '🔴 LIVE'}\n"

        f"Capital: ₹{settings.CAPITAL:,.0f}\n"

        f"Symbol: {settings.SYMBOL}\n"

        "Status: RUNNING"

    )

    # Write initial status for API
    _write_status("RUNNING", settings.SYMBOL)

    try:

        engine.start()

    except Exception as e:
        _write_status("STOPPED", None)
        telegram.send(

            f"❌ *Bot Crashed*\n\n{str(e)}"

        )

        raise


def shutdown_handler(sig, frame):
    _write_status("STOPPED", None)
    telegram.send(
        "🛑 *Algo Bot Stopped*"
    )

    sys.exit(0)

def main():
    args = sys.argv[1:]

    if "--check" in args:
        check_mode()
    elif "--login" in args:
        idx = args.index("--login")
        if idx + 1 < len(args):
            auth_code = args[idx + 1]
            from core.broker import FyersBroker
            broker = FyersBroker()
            if broker.login(auth_code):
                # Save token to .env
                env_file = os.path.join(os.path.dirname(__file__), ".env")
                try:
                    lines = []
                    if os.path.exists(env_file):
                        with open(env_file, "r") as f:
                            for line in f:
                                if line.startswith("FYERS_ACCESS_TOKEN="):
                                    lines.append(f"FYERS_ACCESS_TOKEN={broker.access_token}\n")
                                else:
                                    lines.append(line)
                    if not any(l.startswith("FYERS_ACCESS_TOKEN=") for l in lines):
                        lines.append(f"FYERS_ACCESS_TOKEN={broker.access_token}\n")
                    with open(env_file, "w") as f:
                        f.writelines(lines)
                    log.info("✅ Token saved to .env")
                except Exception as e:
                    log.warning(f"Could not save token: {e}")
                log.info("✅ Login successful!")
            else:
                log.error("❌ Login failed")
    elif "--backtest" in args:
        log.info("Backtest mode coming soon. Run the strategy on historical CSV data.")
    elif "--api" in args:
        run_api()
    else:
        run_bot()


if __name__ == "__main__":

    signal.signal(
        signal.SIGINT,
        shutdown_handler
    )

    signal.signal(
        signal.SIGTERM,
        shutdown_handler
    )

    main()
