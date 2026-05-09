import pandas as pd
import numpy as np

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from config import settings
from utils.logger import get_logger

log = get_logger()

SIGNAL_LONG  = 1
SIGNAL_SHORT = -1
SIGNAL_NONE  = 0


class EmaRsiScalper:

    def __init__(self):
        self.atr_period = 14
        self.vwap_dev_threshold = getattr(settings, 'VWAP_DEV_THRESHOLD', 0.005)

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        df["ema20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
        df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
        df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
        df["atr"] = AverageTrueRange(df["high"], df["low"], df["close"], window=self.atr_period).average_true_range()

        df["datetime"] = pd.to_datetime(df["datetime"])
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["date"] = df["datetime"].dt.date
        df["tpv"] = typical_price * df["volume"]

        df["vwap"] = df.groupby("date")["tpv"].cumsum() / df.groupby("date")["volume"].cumsum()

        df["vol_ma"] = df["volume"].rolling(20).mean()

        return df

    def vwap_filter(self, row: pd.Series) -> tuple:
        close = row["close"]
        vwap = row["vwap"]

        if pd.isna(vwap):
            return True, "VWAP not available"

        deviation = abs(close - vwap) / vwap
        if deviation > self.vwap_dev_threshold:
            return False, "VWAP deviation too high"

        return True, "OK"

    def get_signal(self, df: pd.DataFrame):

        df = self.compute_indicators(df)

        if len(df) < 60:
            return SIGNAL_NONE, {}

        row = df.iloc[-2]

        vwap_allowed, vwap_reason = self.vwap_filter(row)
        
        if not vwap_allowed:
            log.debug("VWAP filter blocked: " + vwap_reason)
            return SIGNAL_NONE, {}

        signal = SIGNAL_NONE

        candle_body = abs(row["close"] - row["open"])
        candle_range = row["high"] - row["low"]

        strong_bullish = row["close"] > row["open"] and candle_range > 0 and (candle_body / candle_range) > 0.4
        strong_bearish = row["close"] < row["open"] and candle_range > 0 and (candle_body / candle_range) > 0.4
        atr_pct = row["atr"] / row["close"]

        vwap_aligned_long = row["close"] > row["vwap"]
        vwap_aligned_short = row["close"] < row["vwap"]

        if (
            row["ema20"] > row["ema50"]
            and vwap_aligned_long
            and row["rsi"] > 50
            and row["rsi"] < 70
            and row["volume"] > row["vol_ma"] * 0.8
            and strong_bullish
            and atr_pct > 0.001
        ):
            signal = SIGNAL_LONG

        elif (
            row["ema50"] > row["ema20"]
            and vwap_aligned_short
            and row["rsi"] < 50
            and row["rsi"] > 30
            and row["volume"] > row["vol_ma"] * 0.8
            and strong_bearish
            and atr_pct > 0.001
        ):
            signal = SIGNAL_SHORT

        close_val = row["close"]
        vwap_val = row["vwap"]
        rsi_val = row["rsi"]
        log.debug("close=%.2f vwap=%.2f rsi=%.2f bullish=%s" % (close_val, vwap_val, rsi_val, strong_bullish))

        info = {
            "close": round(row["close"], 2),
            "atr": round(row["atr"], 2),
            "rsi": round(row["rsi"], 2),
            "vwap": round(row["vwap"], 2) if pd.notna(row.get("vwap")) else None,
        }

        return signal, info

    def description(self):
        return "5m VWAP Momentum Strategy"
