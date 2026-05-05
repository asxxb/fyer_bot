"""
core/risk_manager.py
Position sizing, daily loss limits, and trade guards.
"""
from config import settings
from utils.logger import get_logger

log = get_logger()


class RiskManager:
    """
    Enforces all risk rules:
    - Max trades per day
    - Max daily loss in INR
    - ATR-based position sizing
    - SL/TP calculation
    """

    def __init__(self):
        self.trades_today = 0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.blocked = False    # True = no more trades today
        self.consecutive_losses = 0

    # ── Daily Controls ──────────────────────────────────────────────────────────

    def can_trade(self) -> tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        Call this before every order attempt.
        """
        if self.blocked:
            return False, "Trading blocked for today"
        if self.trades_today >= settings.MAX_TRADES_PER_DAY:
            return False, f"Max trades reached ({settings.MAX_TRADES_PER_DAY})"
        if self.realized_pnl <= -settings.MAX_DAILY_LOSS:
            self.blocked = True
            return False, f"Daily loss limit hit (₹{settings.MAX_DAILY_LOSS:.1f})"
        if self.consecutive_losses >= 3:
            self.blocked = True
            return False, "3 consecutive losses hit"
        return True, "OK"

    def record_trade(self, pnl: float = 0.0):
        """Call after each trade closes."""
        self.trades_today += 1
        self.realized_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        log.info(
            f"Trade #{self.trades_today} | PnL: ₹{pnl:+.2f} | "
            f"Daily PnL: ₹{self.realized_pnl:+.2f}"
        )

    def reset_daily(self):
        """Call at start of each trading day."""
        self.trades_today = 0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.consecutive_losses = 0
        self.blocked = False
        log.info("Risk manager reset for new day.")

    # ── Position Sizing ─────────────────────────────────────────────────────────

    def calculate_qty(self, entry_price: float, atr: float) -> tuple[int, float, float]:
        """
        ATR-based position sizing.

        Returns:
            qty        : number of shares to buy
            stop_loss  : SL price
            target     : TP price (2:1 R:R)
        """
        sl_distance = atr * settings.ATR_MULTIPLIER
        if sl_distance <= 0:
            sl_distance = entry_price * 0.01  # fallback: 1% SL

        # Qty = Risk Amount / SL distance (floored to integer)
        qty = max(1, int(settings.RISK_AMOUNT / sl_distance))

        # Ensure we don't exceed capital
        max_qty_by_capital = max(1, int(settings.CAPITAL / entry_price))
        qty = min(qty, max_qty_by_capital)

        stop_loss = round(entry_price - sl_distance, 2)
        target    = round(entry_price + (sl_distance * 2), 2)   # 2:1 R:R

        log.debug(
            f"Sizing: entry={entry_price:.2f} atr={atr:.2f} "
            f"sl_dist={sl_distance:.2f} qty={qty} "
            f"SL={stop_loss} TP={target}"
        )
        return qty, stop_loss, target

    def calculate_short_qty(self, entry_price: float, atr: float) -> tuple[int, float, float]:
        """Same as above but for short (sell) trades."""
        sl_distance = atr * settings.ATR_MULTIPLIER
        if sl_distance <= 0:
            sl_distance = entry_price * 0.01

        qty = max(1, int(settings.RISK_AMOUNT / sl_distance))
        max_qty_by_capital = max(1, int(settings.CAPITAL / entry_price))
        qty = min(qty, max_qty_by_capital)

        stop_loss = round(entry_price + sl_distance, 2)
        target    = round(entry_price - (sl_distance * 2), 2)

        return qty, stop_loss, target

    # ── Summary ─────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        status = "🔴 BLOCKED" if self.blocked else "🟢 Active"
        return (
            f"Risk | {status} | "
            f"Trades: {self.trades_today}/{settings.MAX_TRADES_PER_DAY} | "
            f"PnL: ₹{self.realized_pnl:+.2f} | "
            f"Limit: ₹{-settings.MAX_DAILY_LOSS:.2f}"
        )
