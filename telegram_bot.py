#!/usr/bin/env python3
import os, sys, requests, time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config import settings
from utils.logger import get_logger

log = get_logger()
API_BASE = "http://localhost:8000"

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
CHAT_ID = settings.TELEGRAM_CHAT_ID

class TelegramBot:
    def __init__(self):
        self.last_update_id = 0
        
    def send(self, text):
        url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
    
    def handle_command(self, cmd):
        cmd = cmd.strip().lower()
        
        if cmd == "/start":
            return "Bot Online! /help for commands"
        
        if cmd == "/status":
            r = requests.get(API_BASE + "/api/status", timeout=5).json()
            mode = r.get("mode", "unknown").upper()
            status = "RUNNING" if r.get("bot_running") else "STOPPED"
            symbol = str(r.get("current_symbol") or "None")
            return "Status\nMode: " + mode + "\nBot: " + status + "\nSymbol: " + symbol
        
        if cmd == "/pnl":
            r = requests.get(API_BASE + "/api/pnl", timeout=5).json()
            pnl = r.get("realized_pnl", 0)
            trades = r.get("trades_today", 0)
            emoji = "🟢" if pnl >= 0 else "🔴"
            return "Day P&L\n" + emoji + " Rs" + str(round(pnl, 2)) + "\nTrades: " + str(trades)
        
        if cmd == "/positions":
            r = requests.get(API_BASE + "/api/trade", timeout=5).json()
            if r.get("active"):
                t = r["trade"]
                return "Open Position\n" + str(t.get("symbol","")) + " " + str(t.get("side","")) + "\nEntry: Rs" + str(t.get("entry_price","")) + "\nSL: Rs" + str(t.get("stop_loss","")) + "\nTP: Rs" + str(t.get("target",""))
            return "No open positions"
        
        if cmd == "/trades":
            r = requests.get(API_BASE + "/api/latest-trades?limit=5", timeout=5).json()
            if not r: return "No trades today"
            lines = ["Recent Trades"]
            for t in r[:5]:
                pnl = t.get("pnl", 0)
                emoji = "🟢" if pnl >= 0 else "🔴"
                sym = str(t.get("symbol", "N/A"))
                reason = str(t.get("exit_reason", ""))
                lines.append(emoji + " " + sym + " Rs" + str(round(pnl, 2)) + " (" + reason + ")")
            return "\n".join(lines)
        
        if cmd == "/health":
            try:
                r = requests.get(API_BASE + "/api/system", timeout=5).json()
                mem = r.get("mem_available", r.get("mem_free", "N/A"))
                uptime = r.get("uptime", "N/A")
                cpu = r.get("cpu_cores", "N/A")
                disk = r.get("disk_free", "N/A")
                return "System\nRAM: " + str(mem) + "\nCPU: " + str(cpu) + " cores\nUptime: " + str(uptime) + "\nDisk: " + str(disk)
            except Exception as e:
                return "Error: " + str(e)
        
        if cmd == "/pause":
            requests.post(API_BASE + "/api/mode", json={"mode": "paper"}, timeout=5)
            return "⏸️ Paused (PAPER mode)"
        
        if cmd == "/resume":
            requests.post(API_BASE + "/api/mode", json={"mode": "live"}, timeout=5)
            return "▶️ Resumed (LIVE mode)"
        
        if cmd == "/shutdown":
            log.warning("Shutdown via Telegram")
            os.system("pkill -f python3 main.py")
            return "🛑 Bot stopped"
        
        if cmd == "/watchlist":
            r = requests.get(API_BASE + "/api/scanner", timeout=5).json()
            results = r.get("results", [])[:5]
            if not results: return "No scanner results"
            return "Top Stocks\n" + "\n".join(["- " + str(s.get("symbol","N/A")) for s in results])
        
        if cmd == "/logs":
            try:
                with open(PROJECT_ROOT + "/bot.log", "r") as f:
                    lines = f.readlines()[-3:]
                return "Recent\n" + "".join(lines)
            except:
                return "Could not read logs"
        
        if cmd == "/help":
            return "Commands:\n/status - Bot status\n/pnl - Day P&L\n/positions - Open trades\n/trades - Recent trades\n/health - System\n/pause - Pause\n/resume - Resume\n/shutdown - Stop\n/watchlist - Top stocks\n/logs - Recent logs"
        
        return "Unknown. /help for commands"
    
    def poll(self):
        if not BOT_TOKEN or not CHAT_ID:
            log.error("Telegram not configured"); return
        
        log.info("Telegram command bot ready")
        
        while True:
            try:
                url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates?offset=" + str(self.last_update_id)
                r = requests.get(url, timeout=10)
                data = r.json()
                
                if data.get("ok"):
                    for upd in data.get("result", []):
                        update_id = upd.get("update_id", 0)
                        
                        if update_id >= self.last_update_id:
                            msg = upd.get("message", {})
                            text = msg.get("text", "")
                            
                            if text.startswith("/"):
                                log.info("Cmd: " + text)
                                reply = self.handle_command(text)
                                self.send(reply)
                            
                            self.last_update_id = update_id + 1
                
                time.sleep(2)
                
            except Exception as e:
                log.error("Error: " + str(e))
                time.sleep(5)

if __name__ == "__main__":
    TelegramBot().poll()
