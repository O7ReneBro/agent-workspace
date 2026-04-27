"""
Live Test Runner — XMR/USD
---------------------------
Fetches REAL Kraken market data for XMR/USD.
Runs full pipeline: Scanner -> LLM Filter -> Risk Manager -> Report.
NO real orders placed. Uses sandbox execution + logs to live_test_log.jsonl.

Usage:
    python live_test_xmr.py
    python live_test_xmr.py --balance 10000 --mute-telegram
    python live_test_xmr.py --skip-llm   # bypass Ollama if not running
"""

import argparse
import json
import os
from datetime import datetime, timezone

import yaml
import ccxt
import pandas as pd
import numpy as np


PAIR = "XMR/USD"
LOG_PATH = "logs/live_test_log.jsonl"


# ─── Args ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Live Test — XMR/USD")
    p.add_argument("--balance", type=float, default=10000.0)
    p.add_argument("--mute-telegram", action="store_true")
    p.add_argument("--skip-llm", action="store_true", help="Skip Ollama LLM filter")
    p.add_argument("--config", type=str, default="config/trading_config.yaml")
    return p.parse_args()


# ─── Market Data ────────────────────────────────────────────────────────────

def get_exchange() -> ccxt.Exchange:
    """Public endpoint only — no API key needed for OHLCV."""
    return ccxt.kraken({"enableRateLimit": True})


def fetch_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def detect_structure(df: pd.DataFrame) -> dict:
    highs = df["high"].values[-20:]
    lows = df["low"].values[-20:]
    recent_high = float(np.max(highs))
    prev_high = float(np.max(highs[:-5]))
    recent_low = float(np.min(lows))
    prev_low = float(np.min(lows[:-5]))
    last_close = float(df["close"].iloc[-1])

    hh, hl = recent_high > prev_high, recent_low > prev_low
    lh, ll = recent_high < prev_high, recent_low < prev_low

    if hh and hl:
        trend = "UPTREND"
    elif lh and ll:
        trend = "DOWNTREND"
    else:
        trend = "RANGING"

    bos = "BULL" if last_close > recent_high else ("BEAR" if last_close < recent_low else "NONE")
    return {
        "trend": trend, "bos": bos,
        "recent_high": recent_high, "recent_low": recent_low, "last_close": last_close
    }


def compute_rsi(df: pd.DataFrame, period: int = 14) -> float:
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss
    return float((100 - (100 / (1 + rs))).iloc[-1])


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def compute_ema(df: pd.DataFrame, span: int) -> float:
    return float(df["close"].ewm(span=span, adjust=False).mean().iloc[-1])


def compute_volume_sma(df: pd.DataFrame, period: int = 20) -> dict:
    avg_vol = float(df["volume"].rolling(period).mean().iloc[-1])
    last_vol = float(df["volume"].iloc[-1])
    return {"avg": avg_vol, "last": last_vol, "above_avg": last_vol > avg_vol}


def scan_xmr(exchange: ccxt.Exchange) -> dict:
    print(f"[LiveTest] Fetching {PAIR} candles from Kraken...")
    df_4h = fetch_ohlcv(exchange, PAIR, "4h", 100)
    df_1h = fetch_ohlcv(exchange, PAIR, "1h", 100)
    df_15m = fetch_ohlcv(exchange, PAIR, "15m", 60)

    s4h = detect_structure(df_4h)
    s1h = detect_structure(df_1h)
    s15m = detect_structure(df_15m)

    rsi_4h = compute_rsi(df_4h)
    rsi_1h = compute_rsi(df_1h)
    rsi_15m = compute_rsi(df_15m)

    atr_1h = compute_atr(df_1h)
    ema20_1h = compute_ema(df_1h, 20)
    ema50_1h = compute_ema(df_1h, 50)
    volume_1h = compute_volume_sma(df_1h)

    last_price = float(df_15m["close"].iloc[-1])
    prev_close_4h = float(df_4h["close"].iloc[-2])
    change_pct = ((last_price - prev_close_4h) / prev_close_4h) * 100

    long_signal = (
        s4h["trend"] == "UPTREND"
        and s1h["bos"] == "BULL"
        and rsi_1h < 70
        and ema20_1h > ema50_1h
    )
    short_signal = (
        s4h["trend"] == "DOWNTREND"
        and s1h["bos"] == "BEAR"
        and rsi_1h > 30
        and ema20_1h < ema50_1h
    )
    direction = "LONG" if long_signal else ("SHORT" if short_signal else "NO_TRADE")

    return {
        "symbol": PAIR,
        "direction": direction,
        "last_price": last_price,
        "change_pct": round(change_pct, 2),
        "atr": atr_1h,
        "rsi_4h": round(rsi_4h, 1),
        "rsi_1h": round(rsi_1h, 1),
        "rsi_15m": round(rsi_15m, 1),
        "ema20_1h": round(ema20_1h, 4),
        "ema50_1h": round(ema50_1h, 4),
        "ema_cross": "BULL" if ema20_1h > ema50_1h else "BEAR",
        "volume_above_avg": volume_1h["above_avg"],
        "structure_4h": s4h,
        "structure_1h": s1h,
        "structure_15m": s15m,
    }


# ─── LLM Filter ─────────────────────────────────────────────────────────────

def llm_filter(signal: dict, config: dict) -> dict:
    import requests, json as _json
    model = config.get("ollama", {}).get("model", "llama3")
    host = config.get("ollama", {}).get("host", "http://localhost:11434")

    prompt = f"""You are a professional crypto trading analyst specializing in XMR (Monero).
Evaluate this live trade signal and respond ONLY with JSON: {{"pass": true/false, "confidence": 1-10, "reason": "brief reason"}}

Live Signal — {signal['symbol']}:
- Direction:    {signal['direction']}
- Price:        {signal['last_price']} (change: {signal['change_pct']}% vs prev 4H close)
- 4H Trend:     {signal['structure_4h']['trend']} | BOS: {signal['structure_4h']['bos']}
- 1H Trend:     {signal['structure_1h']['trend']} | BOS: {signal['structure_1h']['bos']}
- 15M Trend:    {signal['structure_15m']['trend']} | BOS: {signal['structure_15m']['bos']}
- RSI 4H/1H/15M:{signal['rsi_4h']} / {signal['rsi_1h']} / {signal['rsi_15m']}
- EMA20/50 (1H):{signal['ema20_1h']} / {signal['ema50_1h']} → {signal['ema_cross']} cross
- Volume:       {'ABOVE' if signal['volume_above_avg'] else 'BELOW'} average
- ATR (1H):     {signal['atr']:.4f}

Validation Rules:
- Only LONG on UPTREND + BULL BOS + EMA BULL cross
- Only SHORT on DOWNTREND + BEAR BOS + EMA BEAR cross
- RSI 4H must not be >78 (overbought) or <22 (oversold)
- Reject if all timeframes show RANGING
- Higher confidence if volume is above average

Respond ONLY with JSON."""

    try:
        resp = requests.post(f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}, timeout=45)
        raw = resp.json().get("response", "")
        start, end = raw.find("{"), raw.rfind("}") + 1
        result = _json.loads(raw[start:end])
        return result
    except Exception as e:
        print(f"[LLM] Error: {e} — defaulting to pass")
        return {"pass": True, "confidence": 5, "reason": "LLM unavailable — rule-based only"}


# ─── Risk Validation ─────────────────────────────────────────────────────────

def risk_validate(signal: dict, config: dict, balance: float) -> dict:
    from risk_manager import validate_signal
    return validate_signal(
        signal=signal,
        config=config,
        account_balance=balance,
        open_positions=0,
    )


# ─── Sandbox Log ────────────────────────────────────────────────────────────

def log_result(signal: dict, llm_result: dict, validated: dict) -> None:
    os.makedirs("logs", exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE_TEST",
        **{k: v for k, v in signal.items() if k not in ("structure_4h", "structure_1h", "structure_15m")},
        "llm_pass": llm_result.get("pass"),
        "llm_confidence": llm_result.get("confidence"),
        "llm_reason": llm_result.get("reason"),
        "approved": validated.get("approved"),
        "entry": validated.get("entry"),
        "stop_loss": validated.get("stop_loss"),
        "take_profit": validated.get("take_profit"),
        "position_size": validated.get("position_size"),
        "actual_rr": validated.get("actual_rr"),
        "reject_reason": validated.get("reject_reason"),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ─── Print Report ────────────────────────────────────────────────────────────

def print_report(signal: dict, llm_result: dict, validated: dict) -> None:
    approved = validated.get("approved", False)
    status = "✅ TRADE SIGNAL APPROVED" if approved else "❌ NO TRADE"

    print("\n" + "═" * 56)
    print(f"  XMR/USD LIVE TEST REPORT")
    print("═" * 56)
    print(f"  Time:        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Price:       ${signal['last_price']:,.4f}  ({signal['change_pct']:+.2f}% vs prev 4H)")
    print()
    print(f"  ┌ {'MARKET STRUCTURE':^50} ┐")
    print(f"  │ {'Timeframe':<8} {'Trend':<12} {'BOS':<8} {'RSI':>6} │")
    print(f"  ├ {'-'*50} ┤")
    print(f"  │ {'4H':<8} {signal['structure_4h']['trend']:<12} {signal['structure_4h']['bos']:<8} {signal['rsi_4h']:>6.1f} │")
    print(f"  │ {'1H':<8} {signal['structure_1h']['trend']:<12} {signal['structure_1h']['bos']:<8} {signal['rsi_1h']:>6.1f} │")
    print(f"  │ {'15M':<8} {signal['structure_15m']['trend']:<12} {signal['structure_15m']['bos']:<8} {signal['rsi_15m']:>6.1f} │")
    print(f"  └ {'-'*50} ┘")
    print()
    print(f"  EMA20/50 (1H): {signal['ema20_1h']} / {signal['ema50_1h']}  →  {signal['ema_cross']} cross")
    print(f"  ATR (1H):      {signal['atr']:.4f}")
    print(f"  Volume:        {'ABOVE ⬆' if signal['volume_above_avg'] else 'BELOW ⬇'} average")
    print()
    print(f"  Direction:     {signal['direction']}")
    print()
    print(f"  LLM Filter:    {'PASS ✓' if llm_result.get('pass') else 'REJECT ✗'}  "
          f"(confidence: {llm_result.get('confidence', 'N/A')}/10)")
    print(f"  LLM Reason:    {llm_result.get('reason', 'N/A')}")
    print()
    print("═" * 56)
    print(f"  {status}")
    print("═" * 56)
    if approved:
        print(f"  Entry:         {validated['entry']}")
        print(f"  Stop Loss:     {validated['stop_loss']}")
        print(f"  Take Profit:   {validated['take_profit']}")
        print(f"  Size:          {validated['position_size']} XMR")
        print(f"  RR:            {validated['actual_rr']:.2f}:1")
        print(f"  Risk $:        ${validated['position_size'] * abs(validated['entry'] - validated['stop_loss']):.2f}")
    else:
        print(f"  Reason:        {validated.get('reject_reason', signal['direction'])}")
    print("═" * 56)
    print(f"  Log:           {LOG_PATH}")
    print("═" * 56 + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    print("""
╔══════════════════════════════════════════════════╗
║   XMR/USD LIVE TEST — SANDBOX EXECUTION           ║
║   Real market data • No real orders               ║
╚══════════════════════════════════════════════════╝""")

    # Step 1: Fetch live market data
    exchange = get_exchange()
    signal = scan_xmr(exchange)

    print(f"[LiveTest] Direction detected: {signal['direction']}")
    print(f"[LiveTest] Price: ${signal['last_price']:,.4f} | ATR: {signal['atr']:.4f} | RSI 1H: {signal['rsi_1h']}")

    # Step 2: LLM filter
    if args.skip_llm or signal["direction"] == "NO_TRADE":
        llm_result = {"pass": signal["direction"] != "NO_TRADE", "confidence": 0, "reason": "LLM skipped"}
        print(f"[LiveTest] LLM skipped")
    else:
        print(f"[LiveTest] Querying Ollama ({config.get('ollama', {}).get('model', 'llama3')})...")
        llm_result = llm_filter(signal, config)
        print(f"[LiveTest] LLM: {'PASS' if llm_result.get('pass') else 'REJECT'} (confidence {llm_result.get('confidence')}/10) — {llm_result.get('reason')}")

    # Step 3: Risk validation
    if llm_result.get("pass") and signal["direction"] != "NO_TRADE":
        validated = risk_validate(signal, config, args.balance)
    else:
        validated = {**signal, "approved": False, "reject_reason": llm_result.get("reason", "LLM rejected or NO_TRADE")}

    # Step 4: Telegram alert
    if not args.mute_telegram and validated.get("approved"):
        try:
            from telegram_alert import send_message, format_signal_message
            send_message(format_signal_message(validated))
        except Exception as e:
            print(f"[Telegram] Skipped: {e}")

    # Step 5: Log + Report
    log_result(signal, llm_result, validated)
    print_report(signal, llm_result, validated)
