"""
scanner.py
Stock scanner using FYERS API (primary) or yfinance (fallback).
"""

import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import yfinance as yf
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

from config import settings
from utils.logger import get_logger

from core.scanner import (
    compute_score,
    get_performance_data,
    to_internal,
    should_include_stock,
    passes_momentum_filter
)

from core.broker import FyersBroker

log = get_logger()

# FYERS broker singleton
_broker = None


def _get_broker():
    """Get or create FYERS broker."""
    global _broker
    if _broker is None:
        _broker = FyersBroker()
        _broker.login()
    return _broker


def scan_stock_fyers(symbol):
    """Scan a single stock using FYERS API."""
    
    try:
        broker = _get_broker()
        if not broker or not broker.logged_in:
            log.debug(f"{symbol}: Not logged in")
            return None

        # Get 5-minute candles
        full_symbol = f"{symbol}-EQ"
        df = broker.get_candles(
            symbol=full_symbol,
            interval=5,
            lookback_days=5
        )

        if df is None or df.empty:
            log.debug(f"{symbol}: No data from FYERS")
            return None

        if len(df) < 60:
            log.debug(f"{symbol}: Only {len(df)} candles, need 60")
            return None

        # Use lowercase column names from broker
        close_col = df["close"]
        ltp = close_col.iloc[-1]
        prev = close_col.iloc[-2] if len(close_col) > 1 else ltp
        change_pct = ((ltp - prev) / prev) * 100

        # EMA
        ema_9 = EMAIndicator(close_col, window=9).ema_indicator().iloc[-1]
        ema_21 = EMAIndicator(close_col, window=21).ema_indicator().iloc[-1]
        rsi_14 = RSIIndicator(close_col, window=14).rsi().iloc[-1]

        # MACD
        macd = MACD(close_col)
        macd_hist = macd.macd_diff().iloc[-1]

        vol = df["volume"]
        avg_vol = vol.rolling(20).mean().iloc[-1]
        rel_volume = float(vol.iloc[-1]) / float(avg_vol) if avg_vol > 0 else 1.0

        trend = "SIDEWAYS"
        trend_strength = 0
        if pd.notna(ema_9) and pd.notna(ema_21):
            if ema_9 > ema_21:
                trend = "UP"
                trend_strength = 2
            elif ema_9 < ema_21:
                trend = "DOWN"
                trend_strength = 1

        row_dict = df.iloc[-1].to_dict()
        score = compute_score(row_dict, rel_volume, change_pct, trend_strength)

        return {
            "symbol": symbol,
            "ltp": round(float(ltp), 2),
            "change_pct": round(float(change_pct), 2),
            "score": round(float(score), 1),
            "volume": int(vol.iloc[-1]),
            "trend": trend,
            "ema_9": round(float(ema_9), 2) if pd.notna(ema_9) else None,
            "ema_21": round(float(ema_21), 2) if pd.notna(ema_21) else None,
            "rsi": round(float(rsi_14), 1) if pd.notna(rsi_14) else None,
            "macd_hist": round(float(macd_hist), 2),
            "source": "FYERS"
        }

    except Exception as e:
        log.debug(f"{symbol}: FYERS Error - {e}")
        import traceback
        traceback.print_exc()
        return None


def scan_stock_yfinance(symbol):
    """Scan a single stock using yfinance (fallback)."""

    try:
        yahoo_symbol = f"{symbol}.NS"

        # Fetch data with retry
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
                log.debug(f"{symbol}: Retry - {e}")
        
        if df is None or df.empty:
            log.debug(f"{symbol}: No data")
            return None

        # Fix multiindex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if len(df) < 60:
            log.debug(f"{symbol}: Insufficient data")
            return None

        # Get latest price
        close = df["Close"]
        ltp = close.iloc[-1]
        prev_close = close.iloc[-2] if len(close) > 1 else ltp
        change_pct = ((ltp - prev_close) / prev_close) * 100

        # Calculate indicators
        ema_9 = EMAIndicator(close, window=9).ema_indicator()
        ema_21 = EMAIndicator(close, window=21).ema_indicator()
        rsi_14 = RSIIndicator(close, window=14).rsi()
        
        macd = MACD(close)
        macd_hist = macd.macd_diff().iloc[-1] if len(macd.macd_diff()) > 0 else 0

        vol = df["Volume"]
        avg_vol = vol.rolling(20).mean().iloc[-1]
        rel_volume = vol.iloc[-1] / avg_vol if avg_vol > 0 else 1

        trend = "SIDEWAYS"
        trend_strength = 0

        if pd.notna(ema_9) and pd.notna(ema_21):
            if ema_9 > ema_21:
                trend = "UP"
                trend_strength = 2
            elif ema_9 < ema_21:
                trend = "DOWN"
                trend_strength = 1

        row_dict = df.iloc[-1].to_dict()
        score = compute_score(row_dict, rel_volume, change_pct, trend_strength)

        return {
            "symbol": symbol,
            "ltp": round(ltp, 2),
            "change_pct": round(change_pct, 2),
            "score": round(score, 1),
            "volume": int(vol.iloc[-1]),
            "trend": trend,
            "ema_9": round(ema_9, 2) if pd.notna(ema_9) else None,
            "ema_21": round(ema_21, 2) if pd.notna(ema_21) else None,
            "rsi": round(rsi_14, 1) if pd.notna(rsi_14) else None,
            "macd_hist": round(macd_hist, 2),
            "source": "yfinance"
        }

    except Exception as e:
        log.debug(f"{symbol}: yfinance Error - {e}")
        return None


# Default scanner - tries FYERS first, falls back to yfinance
def scan_stock(symbol):
    """Scan a single stock. Returns result regardless of score."""
    
    # Try FYERS first
    result = scan_stock_fyers(symbol)
    if result:
        return result
    
    # Fallback to yfinance
    result = scan_stock_yfinance(symbol)
    if result:
        return result
    
    return None


# For backward compatibility
WATCHLIST = [s.replace("-EQ", "") for s in settings.WATCHLIST]