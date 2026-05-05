
"""
core/engine.py
Main trading engine — the brain of the bot.
Orchestrates:
broker → scanner → strategy → risk → orders → tracking
"""

import time
import json
from datetime import datetime

import pytz
import schedule
from config import settings

from core.broker import FyersBroker
from core.live_scanner import LiveScanner
from core.risk_manager import RiskManager
from core.trade_tracker import TradeTracker

from strategies.ema_rsi_scalper import (
    EmaRsiScalper,
    SIGNAL_LONG,
    SIGNAL_SHORT,
)

from utils.logger import get_logger
from utils.telegram import telegram

log = get_logger(level=settings.LOG_LEVEL)

IST = pytz.timezone("Asia/Kolkata")


class TradingEngine:

    def __init__(self):

        self.scanner = LiveScanner()

        self.broker = FyersBroker()

        self.risk = RiskManager()

        self.tracker = TradeTracker()

        self.strategy = EmaRsiScalper()

        self.running = False

    # ---------------------------------------------------
    # START ENGINE
    # ---------------------------------------------------

    def start(self):

        log.info(settings.summary())

        log.info(
            f"Strategy: "
            f"{self.strategy.description()}"
        )

        # -----------------------------------------
        # LOGIN
        # -----------------------------------------

        if not self.broker.login():

            log.error(
                "Cannot start bot — login failed."
            )

            return

        # -----------------------------------------
        # MODE
        # -----------------------------------------

        mode = (

            "PAPER TRADE 🟡"

            if settings.PAPER_TRADE

            else

            "⚠️ LIVE TRADE 🔴"

        )

        log.info(

            f"\n{'='*40}\n"

            f"BOT STARTING — {mode}\n"

            f"{'='*40}\n"

        )

        self.running = True

        # -----------------------------------------
        # SCHEDULER
        # -----------------------------------------

        interval = settings.CANDLE_INTERVAL

        schedule.every(interval).minutes.do(
            self._tick
        )

        # Daily reset
        schedule.every().day.at(
            "09:00"
        ).do(
            self._daily_reset
        )

        # Square-off
        sq_time = (

            f"{settings.SQUARE_OFF_H:02d}:"

            f"{settings.SQUARE_OFF_M:02d}"

        )

        schedule.every().day.at(
            sq_time
        ).do(
            self._square_off_and_stop
        )

        log.info(

            f"Scheduler active. "

            f"Checking every {interval} minute(s). "

            f"Square-off at {sq_time} IST."

        )

        log.info(
            "Press Ctrl+C to stop.\n"
        )

        # -----------------------------------------
        # MAIN LOOP
        # -----------------------------------------

        try:

            while self.running:

                schedule.run_pending()

                time.sleep(10)

        except KeyboardInterrupt:

            log.info(
                "\nKeyboard interrupt — shutting down..."
            )

            self._shutdown()

    # ---------------------------------------------------
    # CORE TICK
    # ---------------------------------------------------

    def _tick(self):
        
        now = datetime.now(IST)

        # -----------------------------------------
        # HEARTBEAT CHECK
        # -----------------------------------------

        if not self.broker.websocket_alive():
            log.warning(
                "WebSocket heartbeat lost"
            )
            telegram.send(
                "⚠️ WebSocket heartbeat lost"
            )
            # Attempt reconnection
            self.broker.reconnect_websocket()
            return

        # -----------------------------------------
        # TRADING HOURS CHECK
        # -----------------------------------------

        if not self._is_trading_time(now):

            log.debug(

                f"Outside trading hours "

                f"({now.strftime('%H:%M')})"

            )

            return

        log.info(

            f"── Tick "

            f"{now.strftime('%H:%M:%S')} | "

            f"{self.risk.summary()} ──"

        )

        # -----------------------------------------
        # MANAGE EXISTING TRADE
        # -----------------------------------------

        if self.tracker.has_open_trade():

            active_symbol = (

                self.tracker.active_trade["symbol"]

            )

            ltp = self.broker.get_ltp(
                symbol=active_symbol
            )

            if ltp:

                self._manage_open_trade(ltp)

            return

        # -----------------------------------------
        # RISK CHECK
        # -----------------------------------------

        can_trade, reason = self.risk.can_trade()

        if not can_trade:

            log.info(
                f"No trade allowed: {reason}"
            )

            return

        # -----------------------------------------
        # FIND BEST MOMENTUM STOCK
        # -----------------------------------------

        best = self.scanner.best_stock()

        if not best:

            log.info(
                "No strong momentum stocks found."
            )

            return

        symbol = best["symbol"]

        log.info(
            f"🔥 Selected stock: {symbol}"
        )

        # Save scanner results for API/dashboard
        self._save_scanner_results(best)

        # -----------------------------------------
        # FETCH CANDLES
        # -----------------------------------------

        df = self.broker.get_candles(
            symbol=symbol
        )

        if df.empty or len(df) < 60:

            log.warning(
                f"Not enough candles for {symbol}"
            )

            return

        # -----------------------------------------
        # STRATEGY SIGNAL
        # -----------------------------------------

        signal, info = self.strategy.get_signal(df)

        if signal == SIGNAL_LONG:

            self._enter_trade(

                side="BUY",

                price=info["close"],

                atr=info["atr"],

                symbol=symbol

            )

        elif signal == SIGNAL_SHORT:

            self._enter_trade(

                side="SELL",

                price=info["close"],

                atr=info["atr"],

                symbol=symbol

            )

        else:

            log.info(
                f"No signal for {symbol}"
            )

    # ---------------------------------------------------
    # ENTER TRADE
    # ---------------------------------------------------

    def _enter_trade(

        self,

        side: str,

        price: float,

        atr: float,

        symbol: str

    ):

        # -----------------------------------------
        # POSITION SIZING
        # -----------------------------------------

        if side == "BUY":

            qty, sl, tp = (
                self.risk.calculate_qty(
                    price,
                    atr
                )
            )

        else:

            qty, sl, tp = (
                self.risk.calculate_short_qty(
                    price,
                    atr
                )
            )

        if qty < 1:

            log.warning(
                f"Qty too small ({qty})"
            )

            return

        # -----------------------------------------
        # PLACE ORDER
        # -----------------------------------------

        result = self.broker.place_order(

            symbol=symbol,

            side=side,

            qty=qty,

            order_type="MKT",

            tag=f"ENTRY_{side}"

        )

        # -----------------------------------------
        # SUCCESS
        # -----------------------------------------

        if result["success"]:

            # Get actual fill price from broker
            fill_price = (
                self.broker.get_order_fill_price(
                    result["order_id"]
                )
                or price
            )

            # ---------------------------------------------------
            # STOP LOSS ORDER SIDE
            # ---------------------------------------------------

            sl_side = (
                "SELL"
                if side == "BUY"
                else "BUY"
            )

            # ---------------------------------------------------
            # PLACE EXCHANGE SL ORDER
            # ---------------------------------------------------

            sl_result = self.broker.place_sl_order(
                symbol=symbol,
                side=sl_side,
                qty=qty,
                trigger_price=sl,
                tag="AUTO_SL"
            )

            if not sl_result["success"]:
                log.error(
                    f"SL order failed: {sl_result['message']}"
                )
                return

            # ---------------------------------------------------
            # VERIFY ORDER FILLS
            # ---------------------------------------------------

            status = self.broker.get_order_status(
                result["order_id"]
            )

            if status != "COMPLETE":
                log.warning(
                    f"Order not filled: {status}"
                )
                return

            self.tracker.open_trade(
                side=side,
                symbol=symbol,
                qty=qty,
                entry_price=fill_price,
                stop_loss=sl,
                target=tp,
                order_id=result["order_id"],
                atr=atr
            )

            # Save SL order ID
            self.tracker.active_trade[
                "sl_order_id"
            ] = sl_result["order_id"]

        else:

            log.error(

                f"Entry order failed: "

                f"{result['message']}"

            )

    # ---------------------------------------------------
    # MANAGE OPEN TRADE
    # ---------------------------------------------------

    def _manage_open_trade(self, ltp: float):

        t = self.tracker.active_trade
        atr = t.get("atr", 0.0)

        trigger = self.tracker.check_sl_tp(ltp)

        log.info(

            f"Managing trade | "

            f"LTP=₹{ltp:.2f} | "

            f"{self.tracker.current_trade_info()}"

        )

        if trigger in ("SL", "TP"):

            sl_order_id = t.get("sl_order_id")
            if sl_order_id:
                self.broker.cancel_order(sl_order_id)

            close_side = "SELL" if t["side"] == "BUY" else "BUY"

            result = self.broker.place_order(
                symbol=t["symbol"],
                side=close_side,
                qty=t["qty"],
                order_type="MKT",
                tag=f"EXIT_{trigger}"
            )

            if result["success"]:

                if trigger == "SL":
                    telegram.send(
                        f"🛑 *STOP LOSS HIT*\n\n"
                        f"Symbol: {t['symbol']}\n"
                        f"Exit Price: ₹{ltp:.2f}"
                    )
                elif trigger == "TP":
                    telegram.send(
                        f"🎯 *TARGET HIT*\n\n"
                        f"Symbol: {t['symbol']}\n"
                        f"Exit Price: ₹{ltp:.2f}"
                    )

                pnl = self.tracker.close_trade(ltp, reason=trigger)
                self.risk.record_trade(pnl)
            else:
                log.error(f"Exit order failed: {result['message']}")
            return

        new_sl = self.tracker.calculate_trailing_sl(ltp, atr)
        
        if new_sl is not None:
            side = "SELL" if t["side"] == "BUY" else "BUY"
            qty = t["qty"]
            
            # Place NEW SL first (safer)
            sl_result = self.broker.place_sl_order(
                symbol=t["symbol"],
                side=side,
                qty=qty,
                trigger_price=new_sl,
                tag="TRAIL_SL"
            )
            
            if sl_result["success"]:
                # ONLY cancel old SL AFTER new one is placed
                old_sl_order_id = t.get("sl_order_id")
                if old_sl_order_id:
                    self.broker.cancel_order(old_sl_order_id)
                
                t["stop_loss"] = new_sl
                t["sl_order_id"] = sl_result["order_id"]
                self.tracker._save_active_trade()
                log.info(f"✅ Trailing SL updated: ₹{new_sl:.2f}")

    # ---------------------------------------------------
    # SQUARE OFF
    # ---------------------------------------------------

    def _square_off_and_stop(self):

        log.info(
            "⏰ Square-off time reached."
        )

        if self.tracker.has_open_trade():

            active_symbol = (
                self.tracker.active_trade["symbol"]
            )

            ltp = (

                self.broker.get_ltp(
                    symbol=active_symbol
                )

                or

                self.tracker.active_trade[
                    "entry_price"
                ]

            )

            pnl = self.tracker.close_trade(

                ltp,

                reason="SQUARE_OFF"

            )

            self.risk.record_trade(pnl)

        self.broker.square_off_all()

        self.running = False

        log.info(
            "✅ Bot stopped for today."
        )

    # ---------------------------------------------------
    # SHUTDOWN
    # ---------------------------------------------------

    def _shutdown(self):

        log.info(
            "Shutting down engine..."
        )

        self._square_off_and_stop()

    # ---------------------------------------------------
    # DAILY RESET
    # ---------------------------------------------------

    def _daily_reset(self):

        self.risk.reset_daily()

    # ---------------------------------------------------
    # SAVE SCANNER RESULTS
    # ---------------------------------------------------

    def _save_scanner_results(self, best_stock: dict):
        """Save scanner results for dashboard."""
        try:
            import os
            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
            scanner_file = os.path.join(data_dir, "scanner_results.json")
            
            os.makedirs(data_dir, exist_ok=True)
            
            # Also run full scan for top stocks
            all_results = self.scanner.scan()
            
            output = {
                "last_scan": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "current_best": best_stock,
                "results": all_results[:10] if all_results else []
            }
            
            with open(scanner_file, "w") as f:
                json.dump(output, f, indent=2)
                
        except Exception as e:
            log.warning(f"Failed to save scanner results: {e}")

    # ---------------------------------------------------
    # TIME CHECK
    # ---------------------------------------------------

    def _is_trading_time(
        self,
        now: datetime
    ) -> bool:

        h, m = now.hour, now.minute

        start = (

            settings.TRADING_START_H,

            settings.TRADING_START_M

        )

        stop = (

            settings.SQUARE_OFF_H,

            settings.SQUARE_OFF_M

        )

        current = (h, m)

        return start <= current < stop