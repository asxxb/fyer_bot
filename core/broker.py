#!/usr/bin/env python3
"""
core/broker.py
FYERS API v3 wrapper for trading.
Handles login, websocket, order placement,
position management, and market data.
"""

import time
import hashlib
import json
import pandas as pd
import requests
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

    def _get_app_id_hash(self) -> str:
        combined = f"{self.app_id}:{self.secret_id}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def generate_auth_code(self) -> str:
        auth_url = (
            f"{FYERS_BASE_URL}/api/v3/generate-authcode"
            f"?client_id={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&state=sample_state"
        )
        log.info(f"Open this URL to login: {auth_url}")
        return auth_url

    def login(self) -> bool:

        if not self.access_token:
            log.error("No access token. Generate it from FYERS web dashboard.")
            log.info("1. Go to https://myapi.fyers.in/")
            log.info("2. Create an app to get app_id and secret_id")
            log.info("3. Generate access token from web dashboard")
            return False

        try:
            headers = {
                "Authorization": f"{self.app_id}:{self.access_token}"
            }

            response = requests.get(
                f"{FYERS_BASE_URL}/api/v3/profile",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    self.logged_in = True
                    log.info("✅ Login successful")
                    self._start_websocket()
                    return True
                else:
                    log.error(f"❌ Login failed: {data}")
                    return False
            else:
                log.error(f"❌ Login HTTP {response.status_code}: {response.text}")
                return False

        except Exception as e:
            log.error(f"Login error: {e}")
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
                header={
                    "Authorization": f"{self.app_id}:{self.access_token}"
                }
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

        sym = symbol or settings.SYMBOL
        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/data/quotes/",
                params={"symbols": f"NSE:{sym}"},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    d = data.get("d", [])[0]
                    return {
                        "ltp": float(d.get("lp", 0)),
                        "open": float(d.get("o", 0)),
                        "high": float(d.get("h", 0)),
                        "low": float(d.get("l", 0)),
                        "close": float(d.get("c", 0)),
                        "volume": int(d.get("v", 0)),
                    }

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
        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        end_dt = datetime.now(IST)
        start_dt = end_dt - timedelta(days=lookback_days)

        params = {
            "symbol": f"NSE:{sym}",
            "resolution": ivl,
            "date_format": "1",
            "range_from": start_dt.strftime("%Y-%m-%d"),
            "range_to": end_dt.strftime("%Y-%m-%d"),
            "cont_flag": "1"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/data/history",
                params=params,
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    candles = data.get("candles", [])
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

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}",
            "Content-Type": "application/json"
        }

        side_map = {"BUY": 1, "SELL": 2}

        order_payload = {
            "symbol": f"NSE:{symbol}",
            "qty": qty,
            "type": 2 if order_type == "MKT" else 1,
            "side": side_map.get(side, 1),
            "productType": "INTRADAY",
            "limitPrice": 0 if order_type == "MKT" else 0,
            "stopPrice": 0,
            "disclosedQty": 0,
            "validity": "DAY",
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0
        }

        try:
            response = requests.post(
                f"{FYERS_BASE_URL}/api/v3/orders/sync",
                json=order_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    log.info(f"✅ LIVE ORDER: {side} {qty} {symbol}")
                    return {
                        "success": True,
                        "order_id": data.get("id", ""),
                        "message": "Live order placed"
                    }

            log.error(f"place_order failed: {response.text}")
            return {
                "success": False,
                "message": str(response.text)
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

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}",
            "Content-Type": "application/json"
        }

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
            response = requests.post(
                f"{FYERS_BASE_URL}/api/v3/orders/sync",
                json=order_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    log.info(f"✅ SL ORDER: {symbol} @ {trigger_price}")
                    return {
                        "success": True,
                        "order_id": data.get("id", ""),
                        "message": "SL order placed"
                    }

            return {
                "success": False,
                "message": str(response.text)
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

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.delete(
                f"{FYERS_BASE_URL}/api/v3/orders/sync",
                json={"id": order_id},
                headers=headers,
                timeout=10
            )

            return response.status_code == 200

        except Exception:
            return False

    def get_order_status(self, order_id: str) -> Optional[str]:

        if settings.PAPER_TRADE:
            return "COMPLETE"

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/api/v3/orders",
                params={"id": order_id},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    orders = data.get("d", [])
                    if orders:
                        return orders[0].get("status", "")

        except Exception as e:
            log.error(f"Order status error: {e}")

        return None

    def get_order_fill_price(self, order_id: str) -> Optional[float]:

        if settings.PAPER_TRADE:
            for o in self._paper_orders:
                if o["order_id"] == order_id:
                    return o["fill_price"]
            return None

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/api/v3/orders",
                params={"id": order_id},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    orders = data.get("d", [])
                    if orders:
                        return float(orders[0].get("avgPrc", 0))

        except Exception as e:
            log.error(f"Fill price error: {e}")

        return None

    def get_positions(self) -> list[dict]:

        if settings.PAPER_TRADE:
            return self._paper_positions()

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/api/v3/positions",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    positions = []
                    for p in data.get("d", []):
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

        headers = {
            "Authorization": f"{self.app_id}:{self.access_token}"
        }

        try:
            response = requests.get(
                f"{FYERS_BASE_URL}/api/v3/orders",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("s") == 1:
                    return data.get("d", [])

        except Exception as e:
            log.error(f"get_order_book error: {e}")

        return []

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