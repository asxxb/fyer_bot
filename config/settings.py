"""
config/settings.py
Loads and validates all environment variables.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

RUNTIME_CONFIG = "data/runtime_config.json"

paper_trade_runtime = True

if os.path.exists(RUNTIME_CONFIG):

    try:

        with open(RUNTIME_CONFIG, "r") as f:

            runtime_data = json.load(f)

            paper_trade_runtime = runtime_data.get(
                "paper_trade",
                True
            )

    except Exception:

        pass

def _get(key, default=None, required=False, cast=str):
    val = os.getenv(key, default)
    if required and val is None:
        raise EnvironmentError(f"Required env var '{key}' is not set. Check your .env file.")
    if val is not None:
        try:
            return cast(val)
        except Exception:
            raise ValueError(f"Env var '{key}' has invalid value: {val}")
    return val

# ── Credentials ────────────────────────────────────────────────────────────────
# FYERS
FYERS_APP_ID       = _get("FYERS_APP_ID",       required=True)
FYERS_SECRET_ID   = _get("FYERS_SECRET_ID",   required=True)
FYERS_REDIRECT_URI= _get("FYERS_REDIRECT_URI",required=True)
FYERS_ACCESS_TOKEN = _get("FYERS_ACCESS_TOKEN", default="")

# ── Trading Parameters ─────────────────────────────────────────────────────────
CAPITAL             = _get("CAPITAL",             default="1000",  cast=float)
RISK_PER_TRADE_PCT  = _get("RISK_PER_TRADE_PCT",  default="1.0",   cast=float)
MAX_TRADES_PER_DAY  = _get("MAX_TRADES_PER_DAY",  default="5",     cast=int)
MAX_LOSS_PER_DAY_PCT= _get("MAX_LOSS_PER_DAY_PCT",default="2.0",   cast=float)

SYMBOL              = _get("SYMBOL",              default="SBIN-EQ")
EXCHANGE            = _get("EXCHANGE",            default="NSE")

# ── Strategy Settings ──────────────────────────────────────────────────────────
EMA_FAST            = _get("EMA_FAST",            default="9",     cast=int)
EMA_SLOW            = _get("EMA_SLOW",            default="21",    cast=int)
EMA_SIGNAL          = _get("EMA_SIGNAL",          default="9",     cast=int)
RSI_PERIOD          = _get("RSI_PERIOD",          default="14",    cast=int)
RSI_OVERBOUGHT      = _get("RSI_OVERBOUGHT",      default="70",    cast=float)
RSI_OVERSOLD        = _get("RSI_OVERSOLD",        default="30",    cast=float)
ATR_PERIOD          = _get("ATR_PERIOD",          default="14",    cast=int)
ATR_MULTIPLIER      = _get("ATR_MULTIPLIER",      default="1.5",   cast=float)
BREAKEVEN_PCT       = _get("BREAKEVEN_PCT",     default="5.0",   cast=float)  # Disabled - let trailing do the work
TRAIL_FAST_MULT     = _get("TRAIL_FAST_MULT",   default="0.8",   cast=float)  # Tight trailing multiplier
TRAIL_SLOW_MULT     = _get("TRAIL_SLOW_MULT",   default="1.2",   cast=float)  # Normal trailing multiplier
TRAIL_TIGHTEN_PCT   = _get("TRAIL_TIGHTEN_PCT",default="1.0",   cast=float)  # Profit % to activate tight trailing
VWAP_DEV_THRESHOLD   = _get("VWAP_DEV_THRESHOLD",default="0.005", cast=float)  # Max % deviation from VWAP to allow trade
TRAIL_ATR_MULT      = _get("TRAIL_ATR_MULT",    default="1.0",   cast=float)  # Legacy - kept for compatibility
TRAIL_ACTIVATE_PCT  = _get("TRAIL_ACTIVATE_PCT",default="0.3",  cast=float)  # Legacy - kept for compatibility
CANDLE_INTERVAL     = _get("CANDLE_INTERVAL",     default="5",     cast=int)

# ── Scanner Filters ────────────────────────────────────────────────────────────
MIN_MOMENTUM_PCT    = _get("MIN_MOMENTUM_PCT",   default="0.2",   cast=float)  # Minimum price change %
MIN_EXPECTANCY      = _get("MIN_EXPECTANCY",     default="0",     cast=float)  # Minimum positive expectancy
MIN_BACKTEST_TRADES = _get("MIN_BACKTEST_TRADES",default="20",    cast=int)    # Minimum trades for reliable expectancy
SCORE_THRESHOLD     = _get("SCORE_THRESHOLD",     default="7",     cast=int)    # Minimum score to include
ALLOW_UNKNOWN_STOCKS= _get("ALLOW_UNKNOWN_STOCKS",default="false", cast=str).lower() == "true"  # Allow stocks without backtest data

# ── Mode ───────────────────────────────────────────────────────────────────────
# PAPER_TRADE         = _get("PAPER_TRADE",         default="true").lower() == "true"
PAPER_TRADE = paper_trade_runtime
LOG_LEVEL           = _get("LOG_LEVEL",           default="INFO")

# ── Derived ────────────────────────────────────────────────────────────────────
RISK_AMOUNT         = CAPITAL * RISK_PER_TRADE_PCT / 100
MAX_DAILY_LOSS      = CAPITAL * MAX_LOSS_PER_DAY_PCT / 100

# ── Market Timing (IST) ────────────────────────────────────────────────────────
MARKET_OPEN_H, MARKET_OPEN_M     = 9, 15
MARKET_CLOSE_H, MARKET_CLOSE_M   = 15, 30
TRADING_START_H, TRADING_START_M = 9, 20   # Wait a few mins after open
SQUARE_OFF_H, SQUARE_OFF_M       = 15, 15  # Square off before close

def summary():
    mode = "🟡 PAPER TRADE" if PAPER_TRADE else "🔴 LIVE TRADE"
    return (
        f"\n{'='*50}\n"
        f"  Mode     : {mode}\n"
        f"  Symbol   : {SYMBOL} ({EXCHANGE})\n"
        f"  Capital  : ₹{CAPITAL:,.0f}\n"
        f"  Risk/Trade: ₹{RISK_AMOUNT:.1f} ({RISK_PER_TRADE_PCT}%)\n"
        f"  Max Loss : ₹{MAX_DAILY_LOSS:.1f}/day\n"
        f"  Max Trades: {MAX_TRADES_PER_DAY}/day\n"
        f"  Interval : {CANDLE_INTERVAL}m candles\n"
        f"  Trail ATR: {TRAIL_ATR_MULT}\n"
        f"  Trail %  : {TRAIL_ACTIVATE_PCT}%\n"
        f"{'='*50}\n"
    )


TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


WATCHLIST = [
    # Banking
    "SBIN-EQ",
    "HDFCBANK-EQ",
    "ICICIBANK-EQ",
    "YESBANK-EQ",
    "PNB-EQ",
    "BANKBARODA-EQ",
    "UCOBANK-EQ",
    "IDFCFIRSTB-EQ",
    "KOTAKBANK-EQ",
    "AXISBANK-EQ",
    # Finance
    "BAJFINANCE-EQ",
    "JIOFIN-EQ",
    "IRFC-EQ",
    "LICHSGFIN-EQ",
    # Power
    "NTPC-EQ",
    "NHPC-EQ",
    "SUZLON-EQ",
    "TATAPOWER-EQ",
    "ADANIPOWER-EQ",
    # Railway & Infrastructure
    "RVNL-EQ",
    "NBCC-EQ",
    "IRCON-EQ",
    # Steel & Metal
    "SAIL-EQ",
    "TATASTEEL-EQ",
    "JSWSTEEL-EQ",
    # Others
    "IREDA-EQ",
    "RELIANCE-EQ",
    "ADANIENSOL-EQ",
]

FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY"
)

# ---------------------------------------------------
# Runtime Mode Helpers
# ---------------------------------------------------

def set_paper_trade_mode(enabled: bool):

    global PAPER_TRADE

    PAPER_TRADE = enabled

    data = {
        "paper_trade": enabled
    }

    with open(RUNTIME_CONFIG, "w") as f:
        json.dump(data, f, indent=2)


def get_trade_mode():

    return PAPER_TRADE