#!/usr/bin/env python3
"""
core/broker.py
FYERS API v3 wrapper using official fyers_apiv3 SDK.
Handles login, websocket, order placement,
position management, and market data.
"""

import time
import json
import pandas as pd
from datetime import datetime, timedelta
import pytz
from typing import Optional

import websocket

from config import settings
from utils.logger import get_logger

log = get_logger()

IST = pytz.timezone("Asia/Kolkata")

FYERS_BASE_URL = "https://api-t1.fyers.in"
FYERS_WS_URL = "wss://ws-t1.fyers.in"


class FyersBroker:

    """
    Wraps FYERS API v3 with:
    - Paper trade support
    - WebSocket support
    - Order placement
    - Historical candles
    - Position management
    """

    def __init__(self):

        self.app_id = settings.FYERS_APP_ID
        self.secret_id = settings.FYERS_SECRET_ID
        self.redirect_uri = settings.FYERS_REDIRECT_URI
        self.access_token = settings.FYERS_ACCESS_TOKEN
        self.refresh_token = None

        self.logged_in = False

        self._paper_orders = []
        self._paper_order_id = 1000

        self.live_ticks = {}
        self.last_tick_time = datetime.now(IST)

        self.reconnecting = False
        self.websocket_connected = False

        self.token_symbol_map = {}

        self.ws = None
        self.ws_thread = None

        self.fyers = None
        self.session = None

    def generate_auth_url(self) -> str:
        """Generate the OAuth URL for user to login."""
        state = "state123"
        auth_url = (
            f"{FYERS_BASE_URL}/api/v3/generate-authcode"
            f"?client_id={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&state={state}"
        )
        log.info(f"Open this URL in browser to login:")
        log.info(f"{auth_url}")
        log.info("After login, copy the 'code' from redirect URL and use:")
        log.info("  python main.py --login <code>")
        return auth_url

    def login(self, auth_code: str = None) -> bool:

        if not self.access_token and not auth_code:
            log.error("No access token or auth code provided.")
            self.generate_auth_url()
            return False

        try:
            from fyers_apiv3 import fyersModel

            self.session = fyersModel.SessionModel(
                client_id=self.app_id,
                secret_key=self.secret_id,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )

            if auth_code:
                self.session.set_token(auth_code)
                response = self.session.generate_token()
                
                log.info(f"Token response: {response}")
                
                if response.get("s") == "ok" or response.get("code") == 200:
                    self.access_token = response.get("access_token", "")
                    self.refresh_token = response.get("refresh_token", "")
                    self.session.set_token(self.access_token)
                    
                    log.info(f"Access token saved")
                else:
                    log.error(f"❌ Token generation failed: {response}")
                    return False
            else:
                self.session.set_token(self.access_token)

            self.fyers = fyersModel.FyersModel(
                client_id=self.app_id,
                is_async=False, 
                token=self.access_token,
                log_path=""
            )

            profile = self.fyers.get_profile()
            
            if profile.get("s") == "ok":
                self.logged_in = True
                log.info("✅ Login successful")
                log.info(f"Profile: {profile.get('d', {}).get('name', 'User')}")
                return True
            else:
                log.error(f"❌ Profile fetch failed: {profile}")
                return False

        except ImportError:
            log.error("fyers_apiv3 not installed. Run: pip install fyers_apiv3")
            return False
        except Exception as e:
            log.error(f"Login error: {e}")
            import traceback
            log.error(traceback.format_exc())
            return False

    def _start_websocket(self):

        try:
            ws_url = FYERS_WS_URL

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    self._handle_tick(data)
                except:
                    pass

            def on_open(ws):
                log.info("✅ FYERS WebSocket connected")
                self.websocket_connected = True
                self._subscribe_watchlist()

            def on_close(ws):
                log.warning("⚠️ FYERS WebSocket disconnected")
                self.websocket_connected = False

            def on_error(ws, error):
                log.error(f"WebSocket error: {error}")

            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_open=on_open,
                on_close=on_close,
                on_error=on_error,
                header={"Authorization": f"{self.app_id}:{self.access_token}"}
            )

            def run_ws():
                self.ws.run_forever(ping_interval=30)

            import threading
            self.ws_thread = threading.Thread(target=run_ws, daemon=True)
            self.ws_thread.start()

            time.sleep(3)

        except Exception as e:
            log.error(f"WebSocket start error: {e}")

    def _handle_tick(self, tick_data):

        try:
            symbol = tick_data.get("symbol", "")
            ltp = tick_data.get("lp", 0)

            if not ltp:
                return

            self.live_ticks[symbol] = {
                "ltp": float(ltp),
                "time": datetime.now(IST)
            }

            self.last_tick_time = datetime.now(IST)

            log.debug(f"TICK: {symbol} -> {ltp}")

        except Exception as e:
            log.error(f"Tick update error: {e}")

    def _subscribe_watchlist(self):

        if not self.ws or not self.websocket_connected:
            return

        symbols = settings.WATCHLIST
        subscribe_data = {
            "T": "t",
            "v": {"symbols": [f"NSE:{s}" for s in symbols]}
        }
        self.ws.send(json.dumps(subscribe_data))

    def get_live_tick(self, symbol: str) -> Optional[float]:

        tick = self.live_ticks.get(symbol)
        if not tick:
            return None
        return tick.get("ltp")

    def websocket_alive(self) -> bool:

        diff = (datetime.now(IST) - self.last_tick_time).seconds
        return diff < 30

    def get_quote(self, symbol: str = None, exchange: str = None) -> Optional[dict]:

        if not self.fyers:
            log.error("Not logged in")
            return None

        sym = symbol or settings.SYMBOL

        try:
            response = self.fyers.quotes({
                "symbol": f"NSE:{sym}"
            })

            if response.get("s") == "ok":
                d = response.get("d", [])[0]
                return {
                    "ltp": float(d.get("lp", 0)),
                    "open": float(d.get("o", 0)),
                    "high": float(d.get("h", 0)),
                    "low": float(d.get("l", 0)),
                    "close": float(d.get("c", 0)),
                    "volume": int(d.get("v", 0)),
                }
            else:
                log.error(f"Quote error: {response}")

        except Exception as e:
            log.error(f"get_quote error: {e}")

        return None

    def get_ltp(self, symbol: str = None, exchange: str = None) -> Optional[float]:

        sym = symbol or settings.SYMBOL
        tick_ltp = self.get_live_tick(sym)

        if tick_ltp:
            return tick_ltp

        q = self.get_quote(sym, exchange)
        return q["ltp"] if q else None

    def get_candles(
        self,
        symbol: str = None,
        exchange: str = None,
        interval: int = None,
        lookback_days: int = 5
    ) -> pd.DataFrame:

        sym = symbol or settings.SYMBOL
        ivl = interval or settings.CANDLE_INTERVAL

        end_dt = datetime.now(IST)
        start_dt = end_dt - timedelta(days=lookback_days)

        try:
            response = self.fyers.history({
                "symbol": f"NSE:{sym}",
                "resolution": str(ivl),
                "date_format": "1",
                "range_from": start_dt.strftime("%Y-%m-%d"),
                "range_to": end_dt.strftime("%Y-%m-%d"),
                "cont_flag": "1"
            })

            if response.get("s") == "ok":
                candles = response.get("candles", [])
                rows = []
                for c in candles:
                    rows.append({
                        "datetime": datetime.fromtimestamp(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": int(c[5]) if len(c) > 5 else 0,
                    })

                df = pd.DataFrame(rows)
                df = df.sort_values("datetime")
                df = df.reset_index(drop=True)
                log.debug(f"Fetched {len(df)} candles for {sym}")
                return df
            else:
                log.error(f"History error: {response}")

        except Exception as e:
            log.error(f"get_candles error: {e}")

        return pd.DataFrame()

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "MKT",
        tag: str = ""
    ):

        if settings.PAPER_TRADE:

            paper_order_id = f"PAPER_{int(time.time())}"
            fill_price = self.get_ltp(symbol) or 0.0

            log.info(f"[PAPER] {side} {qty} {symbol} @ ₹{fill_price}")

            self._paper_orders.append({
                "order_id": paper_order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "fill_price": fill_price,
                "tag": tag,
                "time": datetime.now(IST).isoformat(),
            })

            return {
                "success": True,
                "order_id": paper_order_id,
                "message": "Paper trade executed",
                "fill_price": fill_price
            }

        if not self.fyers:
            return {"success": False, "message": "Not logged in"}

        side_map = {"BUY": 1, "SELL": 2}
        order_type_map = {"MKT": 2, "LIMIT": 1}

        order_payload = {
            "symbol": f"NSE:{symbol}",
            "qty": qty,
            "type": order_type_map.get(order_type, 2),
            "side": side_map.get(side, 1),
            "productType": "INTRADAY",
            "limitPrice": 0,
            "stopPrice": 0,
            "disclosedQty": 0,
            "validity": "DAY",
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0
        }

        try:
            response = self.fyers.place_order(order_payload)

            if response.get("s") == "ok":
                log.info(f"✅ LIVE ORDER: {side} {qty} {symbol}")
                return {
                    "success": True,
                    "order_id": response.get("id", ""),
                    "message": "Live order placed"
                }

            log.error(f"place_order failed: {response}")
            return {
                "success": False,
                "message": str(response)
            }

        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    def place_sl_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        trigger_price: float,
        tag: str = "SL_ORDER"
    ):

        if settings.PAPER_TRADE:
            return {
                "success": True,
                "order_id": f"PAPER_SL_{int(time.time())}",
                "message": "Paper SL order"
            }

        if not self.fyers:
            return {"success": False, "message": "Not logged in"}

        side_map = {"BUY": 1, "SELL": 2}

        order_payload = {
            "symbol": f"NSE:{symbol}",
            "qty": qty,
            "type": 3,
            "side": side_map.get(side, 1),
            "productType": "INTRADAY",
            "limitPrice": 0,
            "stopPrice": trigger_price,
            "disclosedQty": 0,
            "validity": "DAY",
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0
        }

        try:
            response = self.fyers.place_order(order_payload)

            if response.get("s") == "ok":
                log.info(f"✅ SL ORDER: {symbol} @ {trigger_price}")
                return {
                    "success": True,
                    "order_id": response.get("id", ""),
                    "message": "SL order placed"
                }

            return {
                "success": False,
                "message": str(response)
            }

        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    def cancel_order(self, order_id: str) -> bool:

        if settings.PAPER_TRADE:
            log.info(f"[PAPER] Cancel order {order_id}")
            return True

        if not self.fyers:
            return False

        try:
            response = self.fyers.cancel_order({"id": order_id})
            return response.get("s") == "ok"

        except Exception:
            return False

    def get_order_status(self, order_id: str) -> Optional[str]:

        if settings.PAPER_TRADE:
            return "COMPLETE"

        if not self.fyers:
            return None

        try:
            response = self.fyers.orderbook()

            if response.get("s") == "ok":
                orders = response.get("d", [])
                for o in orders:
                    if o.get("id") == order_id:
                        return o.get("status", "")

        except Exception as e:
            log.error(f"Order status error: {e}")

        return None

    def get_order_fill_price(self, order_id: str) -> Optional[float]:

        if settings.PAPER_TRADE:
            for o in self._paper_orders:
                if o["order_id"] == order_id:
                    return o["fill_price"]
            return None

        if not self.fyers:
            return None

        try:
            response = self.fyers.orderbook()

            if response.get("s") == "ok":
                orders = response.get("d", [])
                for o in orders:
                    if o.get("id") == order_id:
                        return float(o.get("avgPrc", 0))

        except Exception as e:
            log.error(f"Fill price error: {e}")

        return None

    def get_positions(self) -> list[dict]:

        if settings.PAPER_TRADE:
            return self._paper_positions()

        if not self.fyers:
            return []

        try:
            response = self.fyers.positions()

            if response.get("s") == "ok":
                positions = []
                for p in response.get("d", []):
                    qty = int(p.get("netQty", 0))
                    if qty == 0:
                        continue

                    positions.append({
                        "symbol": p.get("sym", ""),
                        "qty": qty,
                        "avg_price": float(p.get("avgCost", 0)),
                        "side": "BUY" if qty > 0 else "SELL",
                        "pnl": float(p.get("urPnl", 0)),
                    })

                return positions

        except Exception as e:
            log.error(f"get_positions error: {e}")

        return []

    def get_order_book(self) -> list[dict]:

        if settings.PAPER_TRADE:
            return self._paper_orders.copy()

        if not self.fyers:
            return []

        try:
            response = self.fyers.orderbook()

            if response.get("s") == "ok":
                return response.get("d", [])

        except Exception as e:
            log.error(f"get_order_book error: {e}")

        return []

    def get_funds(self) -> dict:

        if not self.fyers:
            return {}

        try:
            response = self.fyers.funds()

            if response.get("s") == "ok":
                return response.get("d", {})

        except Exception as e:
            log.error(f"get_funds error: {e}")

        return {}

    def square_off_all(self):

        positions = self.get_positions()

        if not positions:
            log.info("No open positions to square off.")
            return

        for pos in positions:
            side = "SELL" if pos["side"] == "BUY" else "BUY"
            self.place_order(
                side=side,
                qty=abs(pos["qty"]),
                symbol=pos["symbol"],
                tag="SQUARE_OFF"
            )

    def _paper_positions(self) -> list[dict]:

        net = {}

        for o in self._paper_orders:
            sym = o["symbol"]
            qty = o["qty"] if o["side"] == "BUY" else -o["qty"]

            if sym not in net:
                net[sym] = {"qty": 0, "cost": 0.0}

            net[sym]["qty"] += qty
            net[sym]["cost"] += qty * o["fill_price"]

        result = []

        for sym, data in net.items():
            if data["qty"] == 0:
                continue

            avg = abs(data["cost"] / data["qty"])

            result.append({
                "symbol": sym,
                "qty": data["qty"],
                "avg_price": avg,
                "side": "BUY" if data["qty"] > 0 else "SELL",
                "pnl": 0.0,
            })

        return result