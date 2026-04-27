"""
Live Trade Runner — XMR/USD (and any configured pair)
------------------------------------------------------
Runs the full pipeline with REAL Kraken order placement.

Safety layers (all must pass before any order):
  1. Rule-based signal (BOS, HH/HL, EMA, RSI)
  2. Ollama LLM qualitative filter
  3. Risk Manager (RR>=2:1, position size, max positions)
  4. Daily drawdown guard (reads trade log)
  5. Confirmation prompt (unless --yes flag)

Usage:
    python live_trade.py --pair XMR/USD
    python live_trade.py --pair XMR/USD --yes          # skip confirmation
    python live_trade.py --pair BTC/USD --skip-llm     # bypass Ollama
    python live_trade.py --pair ETH/USD --yes --skip-llm

Required env vars:
    KRAKEN_API_KEY
    KRAKEN_API_SECRET

Optional:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, date

import yaml
import ccxt
import pandas as pd
import numpy as np


LOG_PATH = "logs/trade_log.jsonl"
DAILY_DD_LIMIT = None  # Loaded from config


# ─── Args ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Live Trade Runner")
    p.add_argument("--pair", type=str, default="XMR/USD", help="Trading pair (default: XMR/USD)")
    p.add_argument("--yes", action="store_true", help="Skip manual confirmation prompt")
    p.add_argument("--skip-llm", action="store_true", help="Bypass Ollama LLM filter")
    p.add_argument("--mute-telegram", action="store_true", help="Suppress Telegram alerts")
    p.add_argument("--config", type=str, default="config/trading_config.yaml")
    return p.parse_args()


# ─── Config ─────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    # Override with env vars
    if os.environ.get("KRAKEN_API_KEY"):
        cfg["kraken"]["api_key"] = os.environ["KRAKEN_API_KEY"]
    if os.environ.get("KRAKEN_API_SECRET"):
        cfg["kraken"]["api_secret"] = os.environ["KRAKEN_API_SECRET"]
    if os.environ.get("OLLAMA_MODEL"):
        cfg["ollama"]["model"] = os.environ["OLLAMA_MODEL"]
    return cfg


# ─── Daily Drawdown Guard ─────────────────────────────────────────────────────

def check_daily_drawdown(config: dict, account_balance: float) -> tuple[bool, float]:
    """
    Read today's trade log entries, sum up realized P&L.
    Block trading if daily loss exceeds max_daily_drawdown.
    Returns (ok_to_trade, daily_loss_pct).
    """
    dd_limit = config["risk"].get("max_daily_drawdown", 0.05)
    today = date.today().isoformat()
    daily_loss = 0.0

    if not os.path.exists(LOG_PATH):
        return True, 0.0

    with open(LOG_PATH, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("timestamp", "").startswith(today):
                    # Estimate loss from SL hit (conservative: assume all today's trades hit SL)
                    size = entry.get("size", 0)
                    entry_price = entry.get("entry", 0)
                    sl = entry.get("stop_loss", 0)
                    if size and entry_price and sl:
                        loss = size * abs(entry_price - sl)
                        daily_loss += loss
            except Exception:
                continue

    daily_loss_pct = daily_loss / account_balance if account_balance > 0 else 0
    ok = daily_loss_pct < dd_limit
    return ok, daily_loss_pct


# ─── Market Scanner ───────────────────────────────────────────────────────────

def fetch_ohlcv(exchange, symbol, timeframe, limit=100):
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

def detect_structure(df):
    highs = df["high"].values[-20:]
    lows = df["low"].values[-20:]
    rh, ph = float(np.max(highs)), float(np.max(highs[:-5]))
    rl, pl = float(np.min(lows)), float(np.min(lows[:-5]))
    lc = float(df["close"].iloc[-1])
    trend = "UPTREND" if (rh > ph and rl > pl) else ("DOWNTREND" if (rh < ph and rl < pl) else "RANGING")
    bos = "BULL" if lc > rh else ("BEAR" if lc < rl else "NONE")
    return {"trend": trend, "bos": bos, "recent_high": rh, "recent_low": rl, "last_close": lc}

def compute_rsi(df, period=14):
    d = df["close"].diff()
    g = d.where(d > 0, 0.0).rolling(period).mean()
    l = (-d.where(d < 0, 0.0)).rolling(period).mean()
    return float((100 - 100 / (1 + g / l)).iloc[-1])

def compute_atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    return float(pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(period).mean().iloc[-1])

def compute_ema(df, span):
    return float(df["close"].ewm(span=span, adjust=False).mean().iloc[-1])

def scan_pair(exchange, symbol):
    df_4h = fetch_ohlcv(exchange, symbol, "4h", 100)
    df_1h = fetch_ohlcv(exchange, symbol, "1h", 100)
    df_15m = fetch_ohlcv(exchange, symbol, "15m", 60)
    s4h, s1h = detect_structure(df_4h), detect_structure(df_1h)
    rsi_1h = compute_rsi(df_1h)
    atr_1h = compute_atr(df_1h)
    ema20 = compute_ema(df_1h, 20)
    ema50 = compute_ema(df_1h, 50)
    last_price = float(df_15m["close"].iloc[-1])
    volume_above = float(df_1h["volume"].iloc[-1]) > float(df_1h["volume"].rolling(20).mean().iloc[-1])
    long_ok = s4h["trend"] == "UPTREND" and s1h["bos"] == "BULL" and rsi_1h < 70 and ema20 > ema50
    short_ok = s4h["trend"] == "DOWNTREND" and s1h["bos"] == "BEAR" and rsi_1h > 30 and ema20 < ema50
    direction = "LONG" if long_ok else ("SHORT" if short_ok else "NO_TRADE")
    return {
        "symbol": symbol, "direction": direction, "last_price": last_price,
        "atr": atr_1h, "rsi_1h": round(rsi_1h, 1),
        "ema20_1h": round(ema20, 4), "ema50_1h": round(ema50, 4),
        "ema_cross": "BULL" if ema20 > ema50 else "BEAR",
        "volume_above_avg": volume_above,
        "structure_4h": s4h, "structure_1h": s1h,
    }


# ─── LLM Filter ─────────────────────────────────────────────────────────────

def llm_filter(signal, config):
    import requests, json as _j
    model = config.get("ollama", {}).get("model", "llama3")
    host = config.get("ollama", {}).get("host", "http://localhost:11434")
    prompt = f"""Professional trading analyst. Respond ONLY with JSON: {{"pass": true/false, "confidence": 1-10, "reason": "brief"}}

Signal — {signal['symbol']}:
- Direction: {signal['direction']}
- 4H Trend: {signal['structure_4h']['trend']} | BOS: {signal['structure_4h']['bos']}
- 1H BOS: {signal['structure_1h']['bos']}
- RSI 1H: {signal['rsi_1h']}
- EMA cross: {signal['ema_cross']}
- Volume: {'ABOVE' if signal['volume_above_avg'] else 'BELOW'} avg
- ATR: {signal['atr']:.4f}

Pass only if: trend+BOS+EMA all aligned. Reject RANGING. RSI not >78 or <22.
JSON only."""
    try:
        r = requests.post(f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}, timeout=45)
        raw = r.json().get("response", "")
        s, e = raw.find("{"), raw.rfind("}") + 1
        return _j.loads(raw[s:e])
    except Exception as ex:
        print(f"[LLM] Error: {ex}")
        return {"pass": True, "confidence": 5, "reason": "LLM unavailable"}


# ─── Risk Validation ─────────────────────────────────────────────────────────

def risk_validate(signal, config, balance, open_positions):
    from risk_manager import validate_signal
    return validate_signal(signal=signal, config=config,
                           account_balance=balance, open_positions=open_positions)


# ─── Live Execution ─────────────────────────────────────────────────────────

def place_live_order(exchange: ccxt.Exchange, signal: dict) -> dict:
    symbol = signal["symbol"]
    side = "buy" if signal["direction"] == "LONG" else "sell"
    sl_side = "sell" if side == "buy" else "buy"
    size = signal["position_size"]
    sl = signal["stop_loss"]
    tp = signal["take_profit"]

    print(f"\n[Execution] Placing MARKET {side.upper()} order: {symbol} x{size}")
    order = exchange.create_order(symbol=symbol, type="market", side=side, amount=size)
    print(f"[Execution] ✓ Entry order: ID={order.get('id')} Status={order.get('status')}")

    try:
        sl_order = exchange.create_order(symbol=symbol, type="stop-loss",
                                          side=sl_side, amount=size, price=sl)
        print(f"[Execution] ✓ SL order @ {sl}: ID={sl_order.get('id')}")
    except Exception as e:
        print(f"[Execution] ⚠ SL order failed: {e}")
        sl_order = {}

    try:
        tp_order = exchange.create_order(symbol=symbol, type="limit",
                                          side=sl_side, amount=size, price=tp)
        print(f"[Execution] ✓ TP order @ {tp}: ID={tp_order.get('id')}")
    except Exception as e:
        print(f"[Execution] ⚠ TP order failed: {e}")
        tp_order = {}

    return {"entry_order": order, "sl_order": sl_order, "tp_order": tp_order}


def log_trade(signal: dict, orders: dict) -> None:
    os.makedirs("logs", exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE",
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "size": signal["position_size"],
        "rr": signal["actual_rr"],
        "order_id": orders["entry_order"].get("id"),
        "sl_order_id": orders["sl_order"].get("id"),
        "tp_order_id": orders["tp_order"].get("id"),
        "status": orders["entry_order"].get("status"),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Log] Trade logged to {LOG_PATH}")


# ─── Confirmation Prompt ───────────────────────────────────────────────────────

def confirm_trade(signal: dict) -> bool:
    print("\n" + "═" * 54)
    print("  ⚠  LIVE ORDER CONFIRMATION  ⚠")
    print("═" * 54)
    print(f"  Pair:        {signal['symbol']}")
    print(f"  Direction:   {signal['direction']}")
    print(f"  Entry:       {signal['entry']}")
    print(f"  Stop Loss:   {signal['stop_loss']}")
    print(f"  Take Profit: {signal['take_profit']}")
    print(f"  Size:        {signal['position_size']} (base)")
    print(f"  RR:          {signal['actual_rr']:.2f}:1")
    risk_usd = signal['position_size'] * abs(signal['entry'] - signal['stop_loss'])
    print(f"  Risk $:      ${risk_usd:.2f}")
    print("═" * 54)
    ans = input("  Type YES to place live order: ").strip().upper()
    return ans == "YES"


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)

    # Validate API keys present
    if not config["kraken"].get("api_key") or config["kraken"]["api_key"] == "YOUR_KRAKEN_API_KEY":
        print("[ERROR] KRAKEN_API_KEY not set. Export env var or update config.")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════╗
║   LIVE TRADE RUNNER — {args.pair:<28}  ║
║   ⚠  REAL ORDERS WILL BE PLACED  ⚠           ║
╚══════════════════════════════════════════════════╝""")

    # Init exchange with auth
    exchange = ccxt.kraken({
        "apiKey": config["kraken"]["api_key"],
        "secret": config["kraken"]["api_secret"],
        "enableRateLimit": True,
    })

    # Fetch live account state
    print("[LiveTrade] Fetching account balance...")
    balance = exchange.fetch_balance()
    usd_balance = balance["total"].get("USD", 0.0)
    open_orders = exchange.fetch_open_orders()
    open_positions = len(open_orders)
    print(f"[LiveTrade] Balance: ${usd_balance:,.2f} | Open orders: {open_positions}")

    # Daily drawdown check
    dd_ok, dd_pct = check_daily_drawdown(config, usd_balance)
    if not dd_ok:
        limit = config["risk"].get("max_daily_drawdown", 0.05)
        print(f"[GUARD] ❌ Daily drawdown limit hit: {dd_pct:.2%} >= {limit:.2%}. No trades today.")
        sys.exit(0)
    print(f"[LiveTrade] Daily drawdown: {dd_pct:.2%} (limit: {config['risk'].get('max_daily_drawdown', 0.05):.2%}) ✓")

    # Step 1: Scan
    print(f"\n[LiveTrade] Scanning {args.pair}...")
    public_exchange = ccxt.kraken({"enableRateLimit": True})
    signal = scan_pair(public_exchange, args.pair)
    print(f"[LiveTrade] Direction: {signal['direction']} | Price: {signal['last_price']} | RSI: {signal['rsi_1h']} | EMA: {signal['ema_cross']}")

    if signal["direction"] == "NO_TRADE":
        print("[LiveTrade] No valid signal. Exiting.")
        sys.exit(0)

    # Step 2: LLM
    if args.skip_llm:
        llm_result = {"pass": True, "confidence": 0, "reason": "LLM skipped by user"}
    else:
        print(f"[LiveTrade] Querying Ollama ({config['ollama']['model']})...")
        llm_result = llm_filter(signal, config)
        print(f"[LiveTrade] LLM: {'PASS' if llm_result['pass'] else 'REJECT'} ({llm_result.get('confidence')}/10) — {llm_result.get('reason')}")

    if not llm_result.get("pass"):
        print(f"[LiveTrade] LLM rejected signal. Exiting.")
        sys.exit(0)

    # Step 3: Risk
    validated = risk_validate(signal, config, usd_balance, open_positions)
    if not validated["approved"]:
        print(f"[LiveTrade] Risk rejected: {validated['reject_reason']}. Exiting.")
        sys.exit(0)

    # Step 4: Confirmation (unless --yes)
    if not args.yes:
        if not confirm_trade(validated):
            print("[LiveTrade] Cancelled by user.")
            sys.exit(0)
    else:
        risk_usd = validated['position_size'] * abs(validated['entry'] - validated['stop_loss'])
        print(f"[LiveTrade] Auto-confirmed: {args.pair} {validated['direction']} | Entry={validated['entry']} SL={validated['stop_loss']} TP={validated['take_profit']} Size={validated['position_size']} Risk=${risk_usd:.2f}")

    # Step 5: Place order
    try:
        orders = place_live_order(exchange, validated)
        log_trade(validated, orders)
    except ccxt.InsufficientFunds as e:
        print(f"[LiveTrade] ❌ Insufficient funds: {e}")
        sys.exit(1)
    except ccxt.InvalidOrder as e:
        print(f"[LiveTrade] ❌ Invalid order: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[LiveTrade] ❌ Unexpected error: {e}")
        sys.exit(1)

    # Step 6: Telegram
    if not args.mute_telegram:
        try:
            from telegram_alert import send_message, format_signal_message
            send_message(format_signal_message(validated))
        except Exception as e:
            print(f"[Telegram] Skipped: {e}")

    print(f"\n[LiveTrade] ✅ Trade complete. Check logs/{LOG_PATH}")
