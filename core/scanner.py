"""
core/scanner.py
Unified scanner with quality + momentum filtering.
Used by: scanner.py, scanner_worker.py, live_scanner.py
"""
import json
import os
import time
import pandas as pd

from config import settings
from utils.logger import get_logger

log = get_logger()


# ---------------------------------------------------
# SYMBOL NORMALIZATION
# ---------------------------------------------------

def to_internal(symbol):
    """Convert to internal format (SBIN-EQ)."""
    return symbol if "-EQ" in symbol else f"{symbol}-EQ"

def to_yfinance(symbol):
    """Convert to yfinance format (SBIN.NS)."""
    return f"{symbol.replace('-EQ', '')}.NS"

def to_display(symbol):
    """Convert to display format (SBIN)."""
    return symbol.replace("-EQ", "")


# ---------------------------------------------------
# PERFORMANCE DATA (DYNAMIC RELOAD)
# ---------------------------------------------------

_performance_cache = None
_last_loaded = 0
RELOAD_INTERVAL = 300  # Reload every 5 minutes


def load_performance_data():
    """Load backtest performance data from file."""
    path = "data/backtest_results.json"
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Failed to load performance data: {e}")
    return {}


def get_performance_data(force=False):
    """
    Get performance data with optional reload.
    Reloads automatically every 5 minutes or when force=True.
    """
    global _performance_cache, _last_loaded
    
    now = time.time()
    
    if _performance_cache is None or force or (now - _last_loaded) > RELOAD_INTERVAL:
        _performance_cache = load_performance_data()
        _last_loaded = now
        log.debug(f"Performance data reloaded ({len(_performance_cache)} stocks)")
    
    return _performance_cache


def reload_performance_data():
    """Force reload performance data."""
    return get_performance_data(force=True)


# Keep for backward compatibility
PERFORMANCE_DATA = {}  # Deprecated - use get_performance_data() instead


# ---------------------------------------------------
# STOCK SCORING (SHARED LOGIC)
# ---------------------------------------------------

def compute_score(row, rel_volume, change_pct, trend_strength):
    """Compute momentum score for a stock."""
    import pandas as pd
    
    score = 0
    
    # EMA Trend (with NaN safety)
    ema20 = row.get("ema20")
    ema50 = row.get("ema50")
    if pd.notna(ema20) and pd.notna(ema50) and ema20 > ema50:
        score += 2
    
    # Above VWAP (with NaN safety)
    vwap = row.get("vwap")
    if pd.notna(vwap) and pd.notna(row.get("close")) and row["close"] > vwap:
        score += 2
    
    # RSI Strength (with NaN safety)
    rsi = row.get("rsi")
    if pd.notna(rsi) and rsi > 50:
        score += 2
    
    # Relative Volume
    if rel_volume > 1:
        score += 2
    
    # Momentum Score
    if change_pct > 2:
        score += 4
    elif change_pct > 1:
        score += 3
    elif change_pct > 0.5:
        score += 2
    elif change_pct > 0:
        score += 1
    else:
        score -= 3
    
    # Strong Trend
    if trend_strength > 0.001:
        score += 1
    
    # Volatility (with division safety)
    close = row.get("close")
    atr = row.get("atr", 0)
    if pd.notna(close) and close > 0:
        atr_pct = atr / close
        if atr_pct > 0.0005:
            score += 1
    
    return score


# ---------------------------------------------------
# STOCK FILTERING (SHARED LOGIC)
# ---------------------------------------------------

def should_include_stock(symbol, perf=None):
    """
    STEP 1: Quality Filter
    Returns: (should_include: bool, reason: str)
    """
    # If no performance data, use setting to decide
    if not perf:
        if settings.ALLOW_UNKNOWN_STOCKS:
            return True, "no_perf_data"
        return False, "no_perf_data"
    
    # Require minimum trades for reliability
    if perf.get("trades", 0) < settings.MIN_BACKTEST_TRADES:
        return False, f"insufficient_trades({perf.get('trades', 0)})"
    
    # Skip stocks with negative expectancy
    if perf.get("expectancy", 0) <= settings.MIN_EXPECTANCY:
        return False, f"negative_expectancy({perf.get('expectancy', 0):.2f})"
    
    return True, "passed"


def passes_momentum_filter(change_pct, score):
    """
    STEP 2: Momentum Filter
    Returns: (should_include: bool)
    """
    return (
        score >= settings.SCORE_THRESHOLD
        and change_pct >= settings.MIN_MOMENTUM_PCT
    )


# ---------------------------------------------------
# DIVISION SAFETY HELPERS
# ---------------------------------------------------

def safe_divide(a, b, default=0):
    """Safe division with default value."""
    return a / b if b else default


# ---------------------------------------------------
# EXPORTED FUNCTIONS
# ---------------------------------------------------

__all__ = [
    "PERFORMANCE_DATA",  # Deprecated - use get_performance_data()
    "get_performance_data",
    "reload_performance_data",
    "to_internal",
    "to_yfinance", 
    "to_display",
    "compute_score",
    "should_include_stock",
    "passes_momentum_filter",
    "safe_divide"
]