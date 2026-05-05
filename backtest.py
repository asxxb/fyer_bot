#!/usr/bin/env python3
"""
backtest.py
Simple event-driven backtest using saved candle data.

Usage:
    python backtest.py --symbol SBIN-EQ --days 10

Reads from: data/candles_<symbol>.csv  OR fetches live and saves.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
import argparse
import pandas as pd
from datetime import datetime
from utils.telegram import send_telegram
from utils.logger import get_logger
from config import settings
from strategies.ema_rsi_scalper import EmaRsiScalper, SIGNAL_LONG, SIGNAL_SHORT
from core.risk_manager import RiskManager

log = get_logger()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_and_save(symbol, exchange, days):
    """Fetch candles from FYERS and save to CSV."""
    from core.broker import FyersBroker
    broker = FyersBroker()
    if not broker.login():
        log.error("Login failed — cannot fetch data for backtest.")
        sys.exit(1)
    df = broker.get_candles(symbol=symbol, exchange=exchange, lookback_days=days)
    path = os.path.join(DATA_DIR, f"candles_{symbol.replace('-','_')}.csv")
    df.to_csv(path, index=False)
    log.info(f"Saved {len(df)} candles to {path}")
    return df


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    initial_capital: float = 1000.0
):

    strategy = EmaRsiScalper()
    risk = RiskManager()

    capital = initial_capital
    trades = []

    in_trade = False

    entry = 0
    sl = 0
    tp = 0
    side = ""
    qty_bt = 0

    original_sl = 0

    # Cooldown after SL
    cooldown = 0

    # ---------------------------------------------------------
    # Walk Forward Candle By Candle
    # ---------------------------------------------------------

    for i in range(60, len(df)):

        window = df.iloc[:i+1].copy()

        signal, info = strategy.get_signal(window)

        row = df.iloc[i]

        ltp = row["close"]

        # -----------------------------------------------------
        # Cooldown Decrement
        # -----------------------------------------------------

        if cooldown > 0:
            cooldown -= 1

        # -----------------------------------------------------
        # TRADE MANAGEMENT
        # -----------------------------------------------------

        if in_trade:

            hit = None

            # ---------------------------------------------
            # BUY MANAGEMENT
            # ---------------------------------------------

            if side == "BUY":

                initial_risk = entry - original_sl

                # -----------------------------------------
                # Move SL To Breakeven
                # -----------------------------------------

                if (
                    ltp >= entry + initial_risk
                    and sl < entry
                ):

                    sl = entry

                # -----------------------------------------
                # Exit Checks
                # -----------------------------------------

                if ltp <= sl:
                    hit = "SL"

                elif ltp >= tp:
                    hit = "TP"

            # ---------------------------------------------
            # SELL MANAGEMENT
            # ---------------------------------------------

            elif side == "SELL":

                initial_risk = original_sl - entry

                if (
                    ltp <= entry - initial_risk
                    and sl > entry
                ):

                    sl = entry

                if ltp >= sl:
                    hit = "SL"

                elif ltp <= tp:
                    hit = "TP"

            # ---------------------------------------------
            # EXIT TRADE
            # ---------------------------------------------

            if hit:

                pnl = (
                    (ltp - entry) * qty_bt
                    if side == "BUY"
                    else (entry - ltp) * qty_bt
                )

                capital += pnl

                trades.append({
                    "date": row["datetime"],
                    "symbol": symbol,  # Add symbol
                    "side": side,
                    "entry": round(entry, 2),
                    "exit": round(ltp, 2),
                    "qty": qty_bt,
                    "pnl": round(pnl, 2),
                    "hit": hit,
                    "cap": round(capital, 2),
                })

                # -----------------------------------------
                # Cooldown After Loss
                # -----------------------------------------

                if pnl < 0:
                    cooldown = 3

                in_trade = False

                continue

        # -----------------------------------------------------
        # ENTRY LOGIC
        # -----------------------------------------------------

        if not in_trade and cooldown == 0 and info:

            atr = info.get("atr", ltp * 0.01)

            if atr <= 0:
                atr = ltp * 0.01

            # ---------------------------------------------
            # LONG ENTRY
            # ---------------------------------------------

            if signal == SIGNAL_LONG:

                qty_bt, sl, tp = risk.calculate_qty(
                    ltp,
                    atr
                )

                entry = ltp

                original_sl = sl

                side = "BUY"

                in_trade = True

            # ---------------------------------------------
            # SHORT ENTRY
            # ---------------------------------------------

            elif signal == SIGNAL_SHORT:

                qty_bt, sl, tp = risk.calculate_short_qty(
                    ltp,
                    atr
                )

                entry = ltp

                original_sl = sl

                side = "SELL"

                in_trade = True

    # ---------------------------------------------------------
    # RESULTS
# ---------------------------------------------------------

    results = pd.DataFrame(trades)

    # Check if trades generated
    if results.empty:
        log.info("No trades generated in backtest.")
        # Write empty status
        status_data = {
            "bot_status": "RUNNING",
            "capital": float(capital),
            "daily_pnl": 0.0,
            "active_trade": "NONE",
            "last_update": str(datetime.now())
        }
        with open("data/status.json", "w") as f:
            json.dump(status_data, f, indent=4)
        return

    status_data = {
        "bot_status": "RUNNING",
        "capital": float(capital),
        "daily_pnl": float(results['pnl'].sum()),
        "active_trade": "NONE",
        "last_update": str(datetime.now())
    }

    with open("data/status.json", "w") as f:
        json.dump(status_data, f, indent=4)

    # ---------------------------------------------------------
    # Calculate Metrics
    # ---------------------------------------------------------

    wins = results[results["pnl"] > 0]
    losses = results[results["pnl"] <= 0]

    profit_factor = (
        wins["pnl"].sum() / abs(losses["pnl"].sum())
        if not losses.empty and losses["pnl"].sum() != 0
        else 0
    )

    summary_msg = (
        f"📊 BACKTEST RESULT\n\n"
        f"Symbol: {symbol}\n"
        f"Candles: {len(df)}\n"
        f"Trades: {len(results)}\n"
        f"Win Rate: {len(wins)/len(results)*100:.1f}%\n"
        f"Profit Factor: {profit_factor:.2f}\n"
        f"PnL: ₹{results['pnl'].sum():.2f}\n"
        f"Capital: ₹{capital:.2f}\n"
        f"Return: {((capital-initial_capital)/initial_capital*100):.2f}%"
    )

    send_telegram(summary_msg)

    # ---------------------------------------------------------
    # SAVE RESULTS
    # ---------------------------------------------------------

    out_path = os.path.join(
        DATA_DIR,
        f"backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )

    # results.to_csv(out_path, index=False)
    results.to_csv("data/trades.csv", index=False)
    # ---------------------------------------------------------
    # UPDATE EQUITY CURVE
    # ---------------------------------------------------------

    capital_log = pd.DataFrame([
        {
            "time": str(datetime.now()),
            "capital": capital
        }
    ])

    if os.path.exists("data/equity.csv"):

        capital_log.to_csv(
            "data/equity.csv",
            mode="a",
            header=False,
            index=False
        )

    else:

        capital_log.to_csv(
            "data/equity.csv",
            index=False
        )

    log.info(f"\nFull results saved to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol",   default=settings.SYMBOL)
    parser.add_argument("--exchange", default=settings.EXCHANGE)
    parser.add_argument("--days",     default=10, type=int)
    parser.add_argument("--use-cached", action="store_true",
                        help="Load from local CSV instead of fetching live")
    args = parser.parse_args()

    cached_path = os.path.join(DATA_DIR, f"candles_{args.symbol.replace('-','_')}.csv")

    if args.use_cached and os.path.exists(cached_path):
        log.info(f"Loading cached data from {cached_path}")
        df = pd.read_csv(cached_path, parse_dates=["datetime"])
    else:
        df = fetch_and_save(args.symbol, args.exchange, args.days)

    run_backtest(
    df,
    symbol=args.symbol,
    initial_capital=settings.CAPITAL
    )
