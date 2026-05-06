#!/usr/bin/env python3
"""
run_full_backtest.py
Run backtest on all watchlist stocks and generate backtest_results.json

Usage:
    python run_full_backtest.py --days 30
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
import argparse
import pandas as pd
from datetime import datetime

from config import settings
from strategies.ema_rsi_scalper import EmaRsiScalper, SIGNAL_LONG, SIGNAL_SHORT
from core.risk_manager import RiskManager
from core.broker import FyersBroker
from utils.logger import get_logger
from utils.telegram import telegram

log = get_logger()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_FILE = os.path.join(DATA_DIR, "backtest_results.json")


def fetch_candles(symbol, days):
    """Fetch candles from cached CSV or FYERS API."""
    # Try cached data first
    csv_path = os.path.join(DATA_DIR, f"candles_{symbol.replace('-','_')}.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, parse_dates=["datetime"])
            if len(df) >= 60:
                log.info(f"  Using cached data for {symbol}: {len(df)} candles")
                return df
        except Exception as e:
            log.warning(f"Failed to load cached data for {symbol}: {e}")
    
    # Fallback to API
    broker = FyersBroker()
    if not broker.login():
        log.error(f"Login failed for {symbol}")
        return None
    
    df = broker.get_candles(symbol=symbol, lookback_days=days)
    return df


def run_backtest(df: pd.DataFrame, initial_capital: float = 1000.0):
    """Run backtest and return metrics."""
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
    cooldown = 0

    for i in range(60, len(df)):
        window = df.iloc[:i+1].copy()
        signal, info = strategy.get_signal(window)
        row = df.iloc[i]
        ltp = row["close"]

        if cooldown > 0:
            cooldown -= 1

        if in_trade:
            hit = None

            if side == "BUY":
                initial_risk = entry - original_sl
                if ltp >= entry + initial_risk and sl < entry:
                    sl = entry
                if ltp <= sl:
                    hit = "SL"
                elif ltp >= tp:
                    hit = "TP"

            elif side == "SELL":
                initial_risk = original_sl - entry
                if ltp <= entry - initial_risk and sl > entry:
                    sl = entry
                if ltp >= sl:
                    hit = "SL"
                elif ltp <= tp:
                    hit = "TP"

            if hit:
                pnl = (ltp - entry) * qty_bt if side == "BUY" else (entry - ltp) * qty_bt
                capital += pnl
                trades.append({"pnl": pnl, "hit": hit})
                if pnl < 0:
                    cooldown = 3
                in_trade = False
                continue

        if not in_trade and cooldown == 0 and info:
            atr = info.get("atr", ltp * 0.01)
            if atr <= 0:
                atr = ltp * 0.01

            if signal == SIGNAL_LONG:
                qty_bt, sl, tp = risk.calculate_qty(ltp, atr)
                entry = ltp
                original_sl = sl
                side = "BUY"
                in_trade = True

            elif signal == SIGNAL_SHORT:
                qty_bt, sl, tp = risk.calculate_short_qty(ltp, atr)
                entry = ltp
                original_sl = sl
                side = "SELL"
                in_trade = True

    if not trades:
        return None

    results = pd.DataFrame(trades)
    wins = results[results["pnl"] > 0]
    losses = results[results["pnl"] <= 0]

    total_trades = len(results)
    if total_trades == 0:
        return None

    win_rate = len(wins) / total_trades
    
    avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses["pnl"].mean()) if len(losses) > 0 else 0
    
    # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    loss_rate = 1 - win_rate
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    profit_factor = wins["pnl"].sum() / abs(losses["pnl"].sum()) if losses["pnl"].sum() != 0 else 0

    return {
        "trades": total_trades,
        "win_rate": round(win_rate, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor else 0
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", default=30, type=int, help="Days of data to fetch")
    args = parser.parse_args()

    log.info(f"Running full backtest on {len(settings.WATCHLIST)} stocks...")
    
    results = {}
    failed = []
    
    for symbol in settings.WATCHLIST:
        log.info(f"Backtesting {symbol}...")
        
        try:
            df = fetch_candles(symbol, args.days)
            
            if df is None or df.empty or len(df) < 60:
                log.warning(f"Not enough data for {symbol}, skipping")
                failed.append(symbol)
                continue
            
            # Save candles
            csv_path = os.path.join(DATA_DIR, f"candles_{symbol.replace('-','_')}.csv")
            df.to_csv(csv_path, index=False)
            
            metrics = run_backtest(df)
            
            if metrics:
                results[symbol] = metrics
                log.info(f"  {symbol}: {metrics['trades']} trades, expectancy={metrics['expectancy']}, win_rate={metrics['win_rate']}")
            else:
                log.warning(f"No trades generated for {symbol}")
                failed.append(symbol)
                
        except Exception as e:
            log.error(f"Error backtesting {symbol}: {e}")
            failed.append(symbol)
    
    # Save results
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    
    log.info(f"\n✅ Backtest complete!")
    log.info(f"  Results: {len(results)} stocks")
    log.info(f"  Failed: {len(failed)} stocks")
    log.info(f"  Saved to: {RESULTS_FILE}")
    
    # Send telegram
    msg = f"📊 *Full Backtest Complete*\n\n"
    msg += f"Stocks tested: {len(settings.WATCHLIST)}\n"
    msg += f"Passed: {len(results)}\n"
    msg += f"Failed: {len(failed)}\n\n"
    msg += f"Top performers:\n"
    
    sorted_results = sorted(results.items(), key=lambda x: x[1].get('expectancy', 0), reverse=True)[:5]
    for sym, m in sorted_results:
        msg += f"• {sym}: exp={m['expectancy']}, wr={m['win_rate']}\n"
    
    telegram.send(msg)


if __name__ == "__main__":
    main()