# FYERS Algo Trading Bot

A professional-grade algorithmic trading bot for Indian stocks using the FYERS API v3. Built with Python, it features live trading, backtesting, risk management, and a beautiful FastAPI dashboard.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

### Core Trading
- **Live Trading** - Real-time order execution via FYERS API v3
- **Paper Trading** - Test strategies without real money
- **Auto-Reconnect** - REST API polling with automatic retry
- **OAuth2 Authentication** - Secure login via FYERS

### Strategy
- **EMA RSI Scalper** - EMA crossover + RSI filter + ATR stop loss
- **Momentum Scanner** - Real-time stock scanner with sentiment analysis

### Risk Management
- **Daily Loss Limits** - Auto-stop after reaching max daily loss
- **Max Trades Per Day** - Configurable trade limits
- **Consecutive Loss Protection** - Auto-block after losses

### Analytics
- **Backtesting** - Test strategies on historical data
- **Equity Curve** - Track capital growth over time
- **Trade Journal** - Full trade history with PnL analytics

### Notifications
- **Telegram Alerts** - Trade opened/closed, SL/TP hits, errors

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| API | fyers_apiv3 (FYERS API v3) |
| Data | pandas, numpy, fyers |
| Analytics | ta (technical analysis) |
| Dashboard | FastAPI + Uvicorn |
| Charts | Chart.js |
| Logging | colorlog |

## Installation

### 1. Clone the Repository

```bash
cd ~/personal
git clone https://github.com/yourusername/fyer_bot.git
cd fyer_bot
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\Activate   # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp env.example .env
# Edit .env with your credentials
```

### Required Environment Variables

```bash
# FYERS Credentials
FYERS_APP_ID=your_app_id
FYERS_SECRET_ID=your_secret_id
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html
FYERS_ACCESS_TOKEN=your_access_token

# Trading Parameters
CAPITAL=1000
RISK_PER_TRADE_PCT=1.0
MAX_TRADES_PER_DAY=5
MAX_LOSS_PER_DAY_PCT=2.0

# Telegram (optional)
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Usage

### Quick Start with API Dashboard

```bash
python3 main.py --api
```

Access at: `http://localhost:8000`

### Live Trading

```bash
python3 main.py
```

### Scanner

```bash
python3 main.py --scan
```

### Backtest

```bash
# Fetch and use cached data
python3 backtest.py --symbol SBIN-EQ --use-cached

# Fetch fresh data (last 10 days)
python3 backtest.py --symbol SBIN-EQ --days 10
```

### Fetch Data

```bash
python3 fetch_data.py --symbol SBIN-EQ
```

## Project Structure

```
fyer_bot/
├── core/                    # Core trading engine
│   ├── broker.py          # FYERS API wrapper
│   ├── engine.py         # Main trading brain
│   ├── risk_manager.py  # Risk controls
│   ├── trade_tracker.py  # Trade journal
│   ├── live_scanner.py  # Real-time scanner
│   └── sentiment.py      # News sentiment
├── strategies/            # Trading strategies
│   └── ema_rsi_scalper.py
├── config/                # Configuration
│   └── settings.py
├── utils/                 # Utilities
│   ├── logger.py
│   └── telegram.py
├── data/                  # Data storage
│   ├── candles_*.csv
│   ├── trades.csv
│   └── equity.csv
├── templates/              # Dashboard HTML
│   └── dashboard.html
├── api.py                 # FastAPI server
├── main.py               # Live trading entry
├── backtest.py           # Backtesting
├── scanner.py            # Stock scanner
└── requirements.txt     # Dependencies
```

## FYERS API Setup

### 1. Get API Credentials

1. Login to [FYERS Dashboard](https://dashboard.fyers.in/)
2. Go to App Management → Create App
3. Copy your App ID and Secret ID
4. Set redirect URI

### 2. Generate Access Token

First run:
```bash
python3 main.py --login
```

This will show a URL. Open it in browser, login, then copy the code from redirect URL:
```bash
python3 main.py --login <code_from_redirect>
```

The token will be saved to `.env`.

## Strategy: EMA RSI Scalper

### Buy Signal (LONG)
- Fast EMA crosses above Slow EMA
- RSI > 50 AND RSI < 70 (overbought)

### Sell Signal (SHORT)
- Fast EMA crosses below Slow EMA
- RSI < 50 AND RSI > 30 (oversold)

### Stop Loss
- ATR-based (configurable multiplier)

### Take Profit
- 2:1 Risk:Reward ratio

## Configuration

Edit `config/settings.py` or use environment variables:

| Parameter | Default | Description |
|----------|---------|-------------|
| CAPITAL | 1000 | Trading capital (INR) |
| RISK_PER_TRADE_PCT | 1.0 | Risk per trade (%) |
| MAX_TRADES_PER_DAY | 5 | Max trades per day |
| MAX_LOSS_PER_DAY_PCT | 2.0 | Max daily loss (%) |
| EMA_FAST | 9 | Fast EMA period |
| EMA_SLOW | 21 | Slow EMA period |
| RSI_PERIOD | 14 | RSI period |
| RSI_OVERBOUGHT | 70 | RSI overbought level |
| RSI_OVERSOLD | 30 | RSI oversold level |
| ATR_MULTIPLIER | 1.5 | ATR stop loss multiplier |
| CANDLE_INTERVAL | 5 | Candle interval (minutes) |

## Server Deployment

### Bot Control Script

Once deployed, use the `botctl` script to control the bot:

```bash
botctl start    # Start the bot (manual)
botctl stop     # Stop the bot (manual)
botctl restart  # Restart the bot
botctl status   # Check status
botctl logs    # View live logs
botctl dash    # Open dashboard in browser
```

The bot also auto-starts at 9 AM and auto-stops at 3:15 PM on weekdays via cron.

### Manual Setup (Any VPS/Server)

```bash
# SSH to server
ssh root@your_server_ip

# Clone and setup
cd /root
git clone your_repo.git
cd fyer_bot

# Install dependencies
pip3 install -r requirements.txt

# Configure
cp env.example .env
nano .env  # Add your FYERS credentials

# Run with API dashboard
python3 main.py --api
```

### Systemd Service (Recommended)

Create `/etc/systemd/system/fyerbot.service`:

```ini
[Unit]
Description=FYERS Trading Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/fyer_bot
ExecStart=/usr/bin/python3 /root/fyer_bot/main.py --api
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
# Enable and start
systemctl daemon-reload
systemctl enable fyerbot
systemctl start fyerbot

# View logs
journalctl -u fyerbot -f

# Restart after changes
systemctl restart fyerbot
```

### Accessing the Dashboard

- Local: `http://localhost:8000`
- Server: `http://your_server_ip:8000`

### Firewall (if needed)

```bash
# Allow port 8000
ufw allow 8000/tcp
# Or with iptables
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

## Risk Management

The bot automatically:
- Blocks trading after daily loss limit
- Blocks trading after consecutive losses
- Tracks all positions
- Cancels orders when TP hits

## Telegram Notifications

When enabled, you'll receive:
- Trade opened
- Trade closed
- Stop loss hit
- Target hit
- Error alerts

## Data Files

| File | Description |
|------|-------------|
| `data/candles_<SYMBOL>.csv` | OHLCV candle data |
| `data/trades.csv` | Trade history journal |
| `data/equity.csv` | Capital growth over time |
| `data/status.json` | Bot status (for dashboard) |

## Troubleshooting

### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### FYERS API Issues
- Verify credentials in `.env`
- Regenerate access token: `python3 main.py --login`
- Ensure market is open (IST 9:15 AM - 3:30 PM)

### Dashboard Issues
```bash
# Check if port is in use
sudo ss -tlnp | grep 8000

# Restart service
systemctl restart fyerbot
```

## Safety Features

Always use paper trading first:

```bash
# In .env
PAPER_TRADE=true
```

The bot includes multiple safety layers:
1. Paper trading mode (default)
2. Daily loss limits
3. Max trades per day
4. Consecutive loss protection

## License

MIT License - Use at your own risk.

## Disclaimer

This software is for educational purposes. Trading stocks involves substantial risk. Past performance does not guarantee future results. Use paper trading to test thoroughly before using real money.

---

**Happy Trading!**