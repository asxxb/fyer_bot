# Shoonya Algo Trading Bot

A professional-grade algorithmic trading bot for Indian stocks using the Shoonya (Finvasia) API. Built with Python, it features live trading, backtesting, risk management, and a beautiful Streamlit dashboard.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

### Core Trading
- **Live Trading** - Real-time order execution via Shoonya API
- **Paper Trading** - Test strategies without real money
- **Exchange-Side Stop Loss** - SL-M orders that survive bot crashes
- **Auto-Reconnect** - WebSocket heartbeat monitoring with auto-reconnect

### Strategy
- **EMA RSI Scalper** - EMA crossover + RSI filter + ATR stop loss
- **Momentum Scanner** - Real-time stock scanner with sentiment analysis

### Risk Management
- **Daily Loss Limits** - Auto-stop after reaching max daily loss
- **Max Trades Per Day** - Configurable trade limits
- **Consecutive Loss Protection** - Auto-block after 3 consecutive losses

### Analytics
- **Backtesting** - Test strategies on historical data
- **Equity Curve** - Track capital growth over time
- **Trade Journal** - Full trade history with PnL analytics

### Notifications
- **Telegram Alerts** - Trade opened/closed, SL/TP hits, errors

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| API | NorenRestApiPy (Shoonya/Finvasia) |
| Data | pandas, numpy, yfinance |
| Analytics | ta (technical analysis) |
| Dashboard | Streamlit |
| Charts | Plotly |
| Logging | colorlog |

## Installation

### 1. Clone the Repository

```bash
cd ~/personal
git clone https://github.com/yourusername/shoonya_bot.git
cd shoonya_bot
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
# Shoonya Credentials
SHOONYA_USER=your_user_id
SHOONYA_PASSWORD=your_password
SHOONYA_TOTP_SECRET=your_totp_secret
SHOONYA_VENDOR_CODE=your_vendor_code
SHOONYA_API_SECRET=your_api_secret

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

### Dashboard (Recommended)

Launch the visual dashboard for trading, scanning, and backtesting:

```bash
streamlit run dashboard.py
```

Access at: `http://localhost:8501`

### Live Trading

Run the trading bot:

```bash
python3 main.py
```

### Scanner

Run the momentum scanner:

```bash
python3 scanner.py
```

### Backtest

Test strategies on historical data:

```bash
# Fetch and use cached data
python3 backtest.py --symbol SBIN-EQ --use-cached

# Fetch fresh data (last 10 days)
python3 backtest.py --symbol SBIN-EQ --days 10
```

### Fetch Data

Download historical candle data:

```bash
python3 fetch_data.py --symbol SBIN-EQ
```

## Project Structure

```
shoonya_bot/
├── core/                    # Core trading engine
│   ├── broker.py          # Shoonya API wrapper
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
├── dashboard.py           # Streamlit dashboard
├── main.py               # Live trading entry
├── backtest.py           # Backtesting
├── scanner.py            # Stock scanner
└── requirements.txt     # Dependencies
```

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
| CAPITAL | 1000 | Trading capital (₹) |
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

## Risk Management

The bot automatically:
- Blocks trading after daily loss limit
- Blocks trading after 3 consecutive losses
- Places exchange-side SL-M orders (crash-safe)
- Cancels SL orders when TP hits

## Telegram Notifications

When enabled, you'll receive:
- ✅ Trade opened
- 📕 Trade closed
- 🛑 Stop loss hit
- 🎯 Target hit
- ⚠️ WebSocket heartbeat lost
- ⚠️ Error alerts

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
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Shoonya API Issues
- Verify credentials in `.env`
- Check TOTP secret is correct
- Ensure market is open (IST 9:15 AM - 3:30 PM)

### WebSocket Issues
- Check internet connection
- Verify API credentials
- Restart the bot

### Dashboard Issues
```bash
# Clear Streamlit cache
streamlit clear cache

# Or run with fresh port
streamlit run dashboard.py --server.port 8502
```

## Safety Features

⚠️ **Always use paper trading first**

The bot includes multiple safety layers:
1. Paper trading mode (default)
2. Daily loss limits
3. Max trades per day
4. Consecutive loss protection
5. Exchange-side stop losses
6. WebSocket heartbeat monitoring

## License

MIT License - Use at your own risk.

## Disclaimer

This software is for educational purposes. Trading stocks involves substantial risk. Past performance does not guarantee future results. Use paper trading to test thoroughly before using real money.

---

**Happy Trading! 🚀**