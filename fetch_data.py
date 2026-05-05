import yfinance as yf
import pandas as pd
import os

symbol = "SBIN.NS"

df = yf.download(
    symbol,
    interval="5m",
    period="1mo",
    progress=False
)

# Flatten columns if MultiIndex
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df.reset_index(inplace=True)

# Rename properly
df.rename(columns={
    "Datetime": "datetime",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume"
}, inplace=True)

# Keep only required columns
df = df[[
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume"
]]

# Convert numeric columns
for col in ["open", "high", "low", "close", "volume"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Remove bad rows
df.dropna(inplace=True)

os.makedirs("data", exist_ok=True)

path = "data/candles_SBIN_EQ.csv"

df.to_csv(path, index=False)

print(df.head())
print(f"\nSaved {len(df)} candles to {path}")