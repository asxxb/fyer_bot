import time

import pandas as pd

from strategies.ema_rsi_scalper import EmaRsiScalper
from core.broker import FyersBroker
from config import settings
from core.scanner import (
    get_performance_data,
    to_internal,
    should_include_stock,
    passes_momentum_filter,
    compute_score,
    safe_divide
)
from utils.logger import get_logger

log = get_logger()

# Reload performance data every 5 minutes
PERF_RELOAD_INTERVAL = 300


class LiveScanner:

    def __init__(self):
        self.broker = FyersBroker()
        self.strategy = EmaRsiScalper()
        # Cache for performance data with refresh
        self._perf_data = None
        self._last_reload = 0

    # ---------------------------------------------------
    # Scan Stocks
    # ---------------------------------------------------

    def scan(self):

        results = []

        for symbol in settings.WATCHLIST:

            try:

                df = self.broker.get_candles(
                    symbol=symbol
                )

                if df.empty or len(df) < 60:
                    continue

                df = self.strategy.compute_indicators(df)

                row = df.iloc[-2]

                # -----------------------------------------
                # Relative Volume (with division safety)
                # -----------------------------------------

                rel_volume = safe_divide(
                    row["volume"],
                    row["vol_ma"]
                )

                # -----------------------------------------
                # Momentum % (with division safety)
                # -----------------------------------------

                old_close = df.iloc[-10]["close"]

                change_pct = safe_divide(
                    row["close"] - old_close,
                    old_close
                ) * 100

                # -----------------------------------------
                # Trend Strength (with division safety)
                # -----------------------------------------

                trend_strength = safe_divide(
                    abs(row["ema20"] - row["ema50"]),
                    row["close"]
                )

                # -----------------------------------------
                # STEP 1: QUALITY FILTER (Performance)
                # -----------------------------------------
                
                # Get fresh performance data (auto-reload every 5 mins)
                now = time.time()
                if self._perf_data is None or (now - self._last_reload) > PERF_RELOAD_INTERVAL:
                    self._perf_data = get_performance_data()
                    self._last_reload = now
                
                # Cache perf_data for faster lookups
                perf_data = self._perf_data
                perf = perf_data.get(to_internal(symbol))  # Returns None if missing
                
                # Handle None (missing) vs valid data
                if perf is None:
                    if settings.ALLOW_UNKNOWN_STOCKS:
                        log.debug(f"{symbol}: Allowing unknown stock")
                    else:
                        log.debug(f"{symbol}: Skipping - no performance data")
                        continue
                else:
                    include, reason = should_include_stock(symbol, perf)
                    if not include:
                        log.debug(f"{symbol}: Skipping - {reason}")
                        continue

                # -----------------------------------------
                # Score (using shared function)
                # -----------------------------------------

                score = compute_score(row, rel_volume, change_pct, trend_strength)

                # -----------------------------------------
                # STEP 2: MOMENTUM FILTER
                # -----------------------------------------

                if passes_momentum_filter(change_pct, score):

                    results.append({

                        "symbol": symbol,

                        "score": score,

                        "change_pct": round(
                            change_pct,
                            2
                        ),

                        "close": round(
                            row["close"],
                            2
                        ),

                        "rsi": round(
                            row["rsi"],
                            2
                        )

                    })

            except Exception as e:

                log.error(
                    f"Scanner error "
                    f"{symbol}: {e}"
                )

        # ---------------------------------------------------
        # Sort
        # ---------------------------------------------------

        results = sorted(

            results,

            key=lambda x: x["score"],

            reverse=True

        )

        return results

    # ---------------------------------------------------
    # Best Stock
    # ---------------------------------------------------

    def best_stock(self):

        results = self.scan()

        if not results:

            return None

        best = results[0]

        log.info(

            f"🔥 BEST STOCK: "

            f"{best['symbol']} | "

            f"Score={best['score']} | "

            f"Move={best['change_pct']}%"

        )

        return best