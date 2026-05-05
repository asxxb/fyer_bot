# """
# strategies/ema_rsi_scalper.py

# Strategy: EMA Crossover + RSI Filter + ATR Stop Loss

# Logic:
#   LONG  → Fast EMA crosses ABOVE Slow EMA + RSI > 50 + RSI < overbought
#   SHORT → Fast EMA crosses BELOW Slow EMA + RSI < 50 + RSI > oversold
#   SL    → ATR-based (configurable multiplier)
#   TP    → 2:1 Risk:Reward
# """
# import pandas as pd
# import numpy as np
# from ta.trend import EMAIndicator
# from ta.momentum import RSIIndicator
# from ta.volatility import AverageTrueRange

# from config import settings
# from utils.logger import get_logger

# log = get_logger()

# # Signal constants
# SIGNAL_LONG  =  1
# SIGNAL_SHORT = -1
# SIGNAL_NONE  =  0


# class EmaRsiScalper:

#     def __init__(self):
#         self.ema_fast = settings.EMA_FAST
#         self.ema_slow = settings.EMA_SLOW
#         self.rsi_period = settings.RSI_PERIOD
#         self.rsi_ob = settings.RSI_OVERBOUGHT
#         self.rsi_os = settings.RSI_OVERSOLD
#         self.atr_period = settings.ATR_PERIOD

#     def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
#         """
#         Add indicator columns to the candle DataFrame.
#         Requires columns: open, high, low, close, volume
#         Returns enriched DataFrame (may have NaN rows at start).
#         """
#         if len(df) < self.ema_slow + 5:
#             log.warning(f"Not enough candles ({len(df)}) to compute indicators.")
#             return df

#         df = df.copy()

#         # EMAs
#         df["ema_fast"] = EMAIndicator(df["close"], window=self.ema_fast).ema_indicator()
#         df["ema_slow"] = EMAIndicator(df["close"], window=self.ema_slow).ema_indicator()

#         # RSI
#         df["rsi"] = RSIIndicator(df["close"], window=self.rsi_period).rsi()

#         # ATR
#         atr_ind = AverageTrueRange(df["high"], df["low"], df["close"], window=self.atr_period)
#         df["atr"] = atr_ind.average_true_range()

#         # EMA cross direction (+1 fast>slow, -1 fast<slow)
#         df["ema_cross"] = np.where(df["ema_fast"] > df["ema_slow"], 1, -1)

#         # Crossover detection (change in ema_cross)
#         df["crossover"] = df["ema_cross"].diff().fillna(0)
#         # +2 = bullish cross, -2 = bearish cross

#         return df

#     def get_signal(self, df: pd.DataFrame) -> tuple[int, dict]:
#         """
#         Analyse the latest complete candle and return a trade signal.

#         Returns:
#             signal : SIGNAL_LONG | SIGNAL_SHORT | SIGNAL_NONE
#             info   : dict with indicator values for logging
#         """
#         df = self.compute_indicators(df)

#         if df.empty or df.iloc[-1].isnull().any():
#             return SIGNAL_NONE, {}

#         # Use last COMPLETE candle (index -2 is safer than -1 which may be forming)
#         row = df.iloc[-2]

#         info = {
#             "close":    round(row["close"], 2),
#             "ema_fast": round(row["ema_fast"], 2),
#             "ema_slow": round(row["ema_slow"], 2),
#             "rsi":      round(row["rsi"], 1),
#             "atr":      round(row["atr"], 2),
#             "crossover": row["crossover"],
#         }

#         signal = SIGNAL_NONE

#         # ── LONG signal ────────────────────────────────────────────────────────
#         if (
#             row["crossover"] >= 2               # fresh bullish EMA cross
#             and row["rsi"] > 50                 # momentum confirms up
#             and row["rsi"] < self.rsi_ob        # not overbought
#         ):
#             signal = SIGNAL_LONG

#         # ── SHORT signal ───────────────────────────────────────────────────────
#         elif (
#             row["crossover"] <= -2              # fresh bearish EMA cross
#             and row["rsi"] < 50                 # momentum confirms down
#             and row["rsi"] > self.rsi_os        # not oversold
#         ):
#             signal = SIGNAL_SHORT

#         label = {1: "LONG 📈", -1: "SHORT 📉", 0: "HOLD ⏸"}.get(signal, "HOLD")
#         log.debug(
#             f"Signal: {label} | close={info['close']} "
#             f"ema9={info['ema_fast']} ema21={info['ema_slow']} "
#             f"rsi={info['rsi']} atr={info['atr']}"
#         )

#         return signal, info

#     def description(self) -> str:
#         return (
#             f"EMA({self.ema_fast}/{self.ema_slow}) + RSI({self.rsi_period}) Scalper | "
#             f"OB={self.rsi_ob} OS={self.rsi_os} | ATR-SL×{settings.ATR_MULTIPLIER}"
#         )



import pandas as pd
import numpy as np

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from config import settings
from utils.logger import get_logger

log = get_logger()

# ---------------------------------------------------
# Signal Constants
# ---------------------------------------------------
SIGNAL_LONG  = 1
SIGNAL_SHORT = -1
SIGNAL_NONE  = 0


class EmaRsiScalper:

    def __init__(self):
        self.atr_period = 14

    # ---------------------------------------------------
    # Compute Indicators
    # ---------------------------------------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        # EMA
        df["ema20"] = EMAIndicator(
            close=df["close"],
            window=20
        ).ema_indicator()

        df["ema50"] = EMAIndicator(
            close=df["close"],
            window=50
        ).ema_indicator()

        # RSI
        df["rsi"] = RSIIndicator(
            close=df["close"],
            window=14
        ).rsi()

        # ATR
        atr = AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=self.atr_period
        )

        df["atr"] = atr.average_true_range()

        # ---------------------------------------------------
        # VWAP (Daily Reset)
        # ---------------------------------------------------
        df["datetime"] = pd.to_datetime(df["datetime"])

        typical_price = (
            df["high"] +
            df["low"] +
            df["close"]
        ) / 3

        df["date"] = df["datetime"].dt.date

        df["tpv"] = typical_price * df["volume"]

        df["vwap"] = (
            df.groupby("date")["tpv"].cumsum()
            / df.groupby("date")["volume"].cumsum()
        )

        # Volume MA
        df["vol_ma"] = df["volume"].rolling(20).mean()

        return df

    # ---------------------------------------------------
    # Generate Signal
    # ---------------------------------------------------
    def get_signal(self, df: pd.DataFrame):

        df = self.compute_indicators(df)

        # Need enough candles
        if len(df) < 60:
            return SIGNAL_NONE, {}

        # Use previous completed candle
        row = df.iloc[-2]

        signal = SIGNAL_NONE

        # ---------------------------------------------------
        # Candle Strength
        # ---------------------------------------------------
        candle_body = abs(row["close"] - row["open"])
        candle_range = row["high"] - row["low"]

        strong_bullish = (
            row["close"] > row["open"]
            and candle_range > 0
            and (candle_body / candle_range) > 0.4
        )

        # ---------------------------------------------------
        # ATR Volatility %
        # ---------------------------------------------------
        atr_pct = row["atr"] / row["close"]

        # ---------------------------------------------------
        # LONG ENTRY CONDITIONS
        # ---------------------------------------------------
        if (
            row["ema20"] > row["ema50"]
            and row["close"] > row["vwap"]
            and row["rsi"] > 50
            and row["volume"] > row["vol_ma"] * 0.8
            and strong_bullish
            and atr_pct > 0.001
        ):
            signal = SIGNAL_LONG

        # ---------------------------------------------------
        # Debug Logs
        # ---------------------------------------------------
        log.debug(
            f"close={row['close']:.2f} | "
            f"ema20={row['ema20']:.2f} | "
            f"ema50={row['ema50']:.2f} | "
            f"vwap={row['vwap']:.2f} | "
            f"rsi={row['rsi']:.2f} | "
            f"atr%={atr_pct:.4f} | "
            f"bullish={strong_bullish}"
        )

        # ---------------------------------------------------
        # Info
        # ---------------------------------------------------
        info = {
            "close": round(row["close"], 2),
            "atr": round(row["atr"], 2),
            "rsi": round(row["rsi"], 2),
        }

        return signal, info

    # ---------------------------------------------------
    # Strategy Description
    # ---------------------------------------------------
    def description(self):
        return "5m VWAP Momentum Strategy"