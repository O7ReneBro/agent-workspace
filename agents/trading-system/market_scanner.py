"""
Market Scanner Agent
- Fetches OHLCV data for multiple pairs via ccxt (Kraken)
- Detects market structure: BOS, HH/HL, LH/LL
- Generates structured signal dict for Supervisor
"""

import ccxt
import pandas as pd
import numpy as np
from typing import Optional
import yaml
import os


def load_config(path: str = "config/trading_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def fetch_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    """Fetch OHLCV candles and return as DataFrame."""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def detect_structure(df: pd.DataFrame) -> dict:
    """
    Detect market structure: HH/HL (uptrend), LH/LL (downtrend), BOS.
    Uses swing high/low logic on last 20 candles.
    """
    highs = df["high"].values[-20:]
    lows = df["low"].values[-20:]
    closes = df["close"].values

    recent_high = np.max(highs)
    prev_high = np.max(highs[:-5])
    recent_low = np.min(lows)
    prev_low = np.min(lows[:-5])

    hh = recent_high > prev_high
    hl = recent_low > prev_low
    lh = recent_high < prev_high
    ll = recent_low < prev_low

    if hh and hl:
        trend = "UPTREND"
    elif lh and ll:
        trend = "DOWNTREND"
    else:
        trend = "RANGING"

    # Simple BOS: last close broke above recent swing high (bull) or below swing low (bear)
    last_close = closes[-1]
    bos_bull = last_close > recent_high
    bos_bear = last_close < recent_low
    bos = "BULL" if bos_bull else ("BEAR" if bos_bear else "NONE")

    return {
        "trend": trend,
        "bos": bos,
        "recent_high": float(recent_high),
        "recent_low": float(recent_low),
        "last_close": float(last_close),
    }


def compute_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Simple RSI calculation."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range for volatility / stop-loss sizing."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def scan_pair(exchange: ccxt.Exchange, symbol: str) -> dict:
    """Full scan for one symbol: 4H structure + 1H BOS + 15M entry context."""
    df_4h = fetch_ohlcv(exchange, symbol, "4h", 100)
    df_1h = fetch_ohlcv(exchange, symbol, "1h", 100)
    df_15m = fetch_ohlcv(exchange, symbol, "15m", 60)

    structure_4h = detect_structure(df_4h)
    structure_1h = detect_structure(df_1h)
    rsi_1h = compute_rsi(df_1h)
    atr_1h = compute_atr(df_1h)
    last_price = float(df_15m["close"].iloc[-1])

    # Signal logic: HTF trend aligned + 1H BOS confirmed
    long_signal = (
        structure_4h["trend"] == "UPTREND"
        and structure_1h["bos"] == "BULL"
        and rsi_1h < 70
    )
    short_signal = (
        structure_4h["trend"] == "DOWNTREND"
        and structure_1h["bos"] == "BEAR"
        and rsi_1h > 30
    )

    direction = "LONG" if long_signal else ("SHORT" if short_signal else "NO_TRADE")

    return {
        "symbol": symbol,
        "direction": direction,
        "last_price": last_price,
        "atr": atr_1h,
        "rsi_1h": rsi_1h,
        "structure_4h": structure_4h,
        "structure_1h": structure_1h,
    }


def run_scanner(config: dict) -> list[dict]:
    """Scan all configured pairs and return list of signal dicts."""
    exchange = ccxt.kraken({
        "apiKey": config["kraken"]["api_key"],
        "secret": config["kraken"]["api_secret"],
        "enableRateLimit": True,
    })
    results = []
    for symbol in config["trading"]["pairs"]:
        try:
            signal = scan_pair(exchange, symbol)
            results.append(signal)
            print(f"[Scanner] {symbol}: {signal['direction']} | RSI={signal['rsi_1h']:.1f} | ATR={signal['atr']:.4f}")
        except Exception as e:
            print(f"[Scanner] ERROR on {symbol}: {e}")
    return results


if __name__ == "__main__":
    cfg = load_config()
    signals = run_scanner(cfg)
    for s in signals:
        print(s)
