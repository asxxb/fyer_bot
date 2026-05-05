import yfinance as yf
import pandas as pd

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

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

# ---------------------------------------------------
# WATCHLIST (strip -EQ from settings.WATCHLIST)
# ---------------------------------------------------

# Strip -EQ for yfinance symbol but keep -EQ for performance lookup
WATCHLIST = [s.replace("-EQ", "") for s in settings.WATCHLIST]

# Helper to get performance data with -EQ suffix (dynamic)
def get_performance(stock):
    """Get performance data using -EQ suffix. Returns None if missing."""
    return get_performance_data().get(to_internal(stock))

# ---------------------------------------------------
# SCAN SINGLE STOCK
# ---------------------------------------------------

def scan_stock(symbol):

    try:

        yahoo_symbol = f"{symbol}.NS"

        # -----------------------------------------
        # FETCH DATA (with retry)
        # -----------------------------------------

        df = None
        for _ in range(2):
            try:
                df = yf.download(
                    yahoo_symbol,
                    interval="5m",
                    period="5d",
                    progress=False,
                    auto_adjust=False
                )
                if df is not None and not df.empty:
                    break
            except Exception as e:
                log.debug(f"{symbol}: Retry after error - {e}")
        
        if df is None or df.empty:
            log.debug(f"{symbol}: No data (after retries)")
            return None

        # -----------------------------------------
        # EMPTY CHECK
        # -----------------------------------------

        if df.empty or len(df) < 60:

            log.debug(f"{symbol}: No data")

            return None

        # -----------------------------------------
        # FIX MULTIINDEX
        # -----------------------------------------

        if isinstance(df.columns, pd.MultiIndex):

            df.columns = (
                df.columns.get_level_values(0)
            )

        # -----------------------------------------
        # RESET INDEX
        # -----------------------------------------

        df.reset_index(inplace=True)

        # -----------------------------------------
        # RENAME COLUMNS
        # -----------------------------------------

        df.rename(columns={

            "Datetime": "datetime",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"

        }, inplace=True)

        # -----------------------------------------
        # KEEP REQUIRED COLUMNS
        # -----------------------------------------

        required_columns = [

            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume"

        ]

        if not set(required_columns).issubset(df.columns):

            log.debug(f"{symbol}: Missing OHLCV")

            return None

        df = df[required_columns]

        # -----------------------------------------
        # NUMERIC CONVERSION
        # -----------------------------------------

        for col in [

            "open",
            "high",
            "low",
            "close",
            "volume"

        ]:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df.dropna(inplace=True)

        # -----------------------------------------
        # NEED ENOUGH DATA
        # -----------------------------------------

        if len(df) < 60:

            return None

        # -----------------------------------------
        # EMA
        # -----------------------------------------

        df["ema20"] = EMAIndicator(

            close=df["close"],
            window=20

        ).ema_indicator()

        df["ema50"] = EMAIndicator(

            close=df["close"],
            window=50

        ).ema_indicator()

        # -----------------------------------------
        # RSI
        # -----------------------------------------

        df["rsi"] = RSIIndicator(

            close=df["close"],
            window=14

        ).rsi()

        # -----------------------------------------
        # ATR
        # -----------------------------------------

        atr = AverageTrueRange(

            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=14

        )

        df["atr"] = atr.average_true_range()

        # -----------------------------------------
        # VWAP
        # -----------------------------------------

        df["datetime"] = pd.to_datetime(
            df["datetime"]
        )

        typical_price = (

            df["high"] +
            df["low"] +
            df["close"]

        ) / 3

        df["date"] = (
            df["datetime"].dt.date
        )

        df["tpv"] = (
            typical_price *
            df["volume"]
        )

        df["vwap"] = (

            df.groupby("date")["tpv"].cumsum()

            /

            df.groupby("date")["volume"].cumsum()

        )

        # -----------------------------------------
        # VOLUME MA
        # -----------------------------------------

        df["vol_ma"] = (

            df["volume"]
            .rolling(20)
            .mean()

        )

        # -----------------------------------------
        # USE PREVIOUS CLOSED CANDLE
        # -----------------------------------------

        row = df.iloc[-2]

        # -----------------------------------------
        # RELATIVE VOLUME (with division safety)
        # -----------------------------------------

        rel_volume = safe_divide(
            row["volume"],
            row["vol_ma"]
        )

        # -----------------------------------------
        # PRICE CHANGE % (with division safety)
        # -----------------------------------------

        old_close = df.iloc[-10]["close"]

        change_pct = safe_divide(
            row["close"] - old_close,
            old_close
        ) * 100

        # -----------------------------------------
        # TREND STRENGTH (with division safety)
        # -----------------------------------------

        trend_strength = safe_divide(
            abs(row["ema20"] - row["ema50"]),
            row["close"]
        )

        # -----------------------------------------
        # ATR % (with division safety)
        # -----------------------------------------

        atr_pct = safe_divide(
            row["atr"],
            row["close"]
        )

        # -----------------------------------------
        # SCORE SYSTEM (using shared function)
        # -----------------------------------------

        score = compute_score(row, rel_volume, change_pct, trend_strength)

        # -----------------------------------------
        # RETURN RESULT
        # -----------------------------------------

        return {

            "symbol": symbol,

            "close": round(
                row["close"],
                2
            ),

            "rsi": round(
                row["rsi"],
                2
            ),

            "rel_volume": round(
                rel_volume,
                2
            ),

            "change_pct": round(
                change_pct,
                2
            ),

            "trend_strength": round(
                trend_strength,
                4
            ),

            "score": round(
                score,
                2
            )

        }

    except Exception as e:

        log.debug(f"{symbol} error: {e}")

    return None


# ---------------------------------------------------
# RUN SCANNER
# ---------------------------------------------------

if __name__ == "__main__":

    results = []

    for stock in WATCHLIST:

        # -----------------------------------------
        # STEP 1: QUALITY FILTER (Performance)
        # -----------------------------------------
        perf = get_performance(stock)
        
        # Handle None (missing) vs empty dict vs valid data
        if perf is None:
            if settings.ALLOW_UNKNOWN_STOCKS:
                log.debug(f"{stock}: Allowing unknown stock")
            else:
                log.debug(f"{stock}: Skipping - no performance data")
                continue
        else:
            include, reason = should_include_stock(stock, perf)
            if not include:
                log.debug(f"{stock}: Skipping - {reason}")
                continue

        result = scan_stock(stock)

        # -----------------------------------------
        # STEP 2: MOMENTUM FILTER
        # -----------------------------------------
        if result and passes_momentum_filter(result["change_pct"], result["score"]):
            results.append(result)

    # -----------------------------------------
    # SORT BY SCORE
    # -----------------------------------------

    results = sorted(

        results,

        key=lambda x: x["score"],

        reverse=True

    )

    # -----------------------------------------
    # OUTPUT
    # -----------------------------------------

    print("\n🔥 TOP MOMENTUM STOCKS 🔥\n")

    if not results:

        print(
            "No strong momentum stocks found."
        )

    else:

        for r in results:

            print(

                f"{r['symbol']} | "

                f"₹{r['close']} | "

                f"RSI={r['rsi']} | "

                f"RVOL={r['rel_volume']} | "

                f"Move={r['change_pct']}% | "

                f"Trend={r['trend_strength']} | "

                f"Score={r['score']}"

            )