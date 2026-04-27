"""
Vectorized Backtester—Trading System
-------------------------------------
Replays BOS + EMA + RSI signals on historical OHLCV data.
Outputs: win rate, Sharpe ratio, max drawdown, expectancy, equity curve.
Results saved to logs/backtest_results.json + logs/backtest_equity.csv

Usage:
    python backtest.py
    python backtest.py --pair XMR/USD --days 180
    python backtest.py --pair BTC/USD --days 365 --balance 5000
    python backtest.py --all-pairs
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta

import ccxt
import numpy as np
import pandas as pd
import yaml


LOG_DIR = "logs"
RESULTS_FILE = os.path.join(LOG_DIR, "backtest_results.json")
EQUITY_FILE = os.path.join(LOG_DIR, "backtest_equity.csv")


# ─── Args ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--pair", type=str, default="XMR/USD")
    p.add_argument("--days", type=int, default=180, help="Lookback days")
    p.add_argument("--balance", type=float, default=10000.0)
    p.add_argument("--risk-pct", type=float, default=0.01, help="Risk per trade (0.01=1%)")
    p.add_argument("--atr-sl-mult", type=float, default=1.5, help="ATR SL multiplier")
    p.add_argument("--rr", type=float, default=2.0, help="Reward:Risk ratio")
    p.add_argument("--all-pairs", action="store_true", help="Backtest all pairs from config")
    p.add_argument("--config", type=str, default="config/trading_config.yaml")
    return p.parse_args()


# ─── Data Fetch ────────────────────────────────────────────────────────────

def fetch_full_ohlcv(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Fetch enough candles to cover `days` of history via pagination."""
    exchange = ccxt.kraken({"enableRateLimit": True})
    tf_minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    minutes = tf_minutes.get(timeframe, 60)
    limit = min(720, (days * 24 * 60) // minutes)

    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=500)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        if len(candles) < 500:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ─── Indicators (vectorized) ───────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame, rsi_period=14, atr_period=14) -> pd.DataFrame:
    df = df.copy()

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(rsi_period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss))

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(atr_period).mean()

    # EMA
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_bull"] = df["ema20"] > df["ema50"]

    # Swing high / low (rolling 10-bar)
    df["swing_high"] = df["high"].rolling(10).max()
    df["swing_low"] = df["low"].rolling(10).min()
    df["prev_swing_high"] = df["swing_high"].shift(1)
    df["prev_swing_low"] = df["swing_low"].shift(1)

    # BOS: close breaks above swing high (bull) or below swing low (bear)
    df["bos_bull"] = df["close"] > df["prev_swing_high"]
    df["bos_bear"] = df["close"] < df["prev_swing_low"]

    # HH/HL (uptrend) LH/LL (downtrend) using 20-bar windows
    df["hh"] = df["high"].rolling(20).max() > df["high"].rolling(20).max().shift(5)
    df["hl"] = df["low"].rolling(20).min() > df["low"].rolling(20).min().shift(5)
    df["lh"] = df["high"].rolling(20).max() < df["high"].rolling(20).max().shift(5)
    df["ll"] = df["low"].rolling(20).min() < df["low"].rolling(20).min().shift(5)

    df["uptrend"] = df["hh"] & df["hl"]
    df["downtrend"] = df["lh"] & df["ll"]

    return df


# ─── Signal Generation (vectorized) ───────────────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["long_signal"] = (
        df["uptrend"] &
        df["bos_bull"] &
        df["ema_bull"] &
        (df["rsi"] < 70) &
        (df["rsi"] > 30)
    )
    df["short_signal"] = (
        df["downtrend"] &
        df["bos_bear"] &
        ~df["ema_bull"] &
        (df["rsi"] > 30) &
        (df["rsi"] < 70)
    )
    return df


# ─── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    initial_balance: float = 10000.0,
    risk_pct: float = 0.01,
    atr_sl_mult: float = 1.5,
    rr: float = 2.0,
) -> dict:
    """
    Vectorized walk-forward backtest.
    One trade at a time: once in a trade, skip new signals until trade closes.
    """
    balance = initial_balance
    equity_curve = []
    trades = []
    in_trade = False
    entry_price = sl = tp = size = direction = None

    df = df.dropna().reset_index(drop=True)

    for i, row in df.iterrows():
        # --- Manage open trade ---
        if in_trade:
            high, low, close = row["high"], row["low"], row["close"]
            if direction == "LONG":
                if low <= sl:
                    pnl = -size * abs(entry_price - sl)
                    balance += pnl
                    trades.append({"direction": "LONG", "result": "LOSS", "pnl": round(pnl, 4),
                                   "entry": entry_price, "exit": sl, "timestamp": str(row["timestamp"])})
                    in_trade = False
                elif high >= tp:
                    pnl = size * abs(tp - entry_price)
                    balance += pnl
                    trades.append({"direction": "LONG", "result": "WIN", "pnl": round(pnl, 4),
                                   "entry": entry_price, "exit": tp, "timestamp": str(row["timestamp"])})
                    in_trade = False
            elif direction == "SHORT":
                if high >= sl:
                    pnl = -size * abs(sl - entry_price)
                    balance += pnl
                    trades.append({"direction": "SHORT", "result": "LOSS", "pnl": round(pnl, 4),
                                   "entry": entry_price, "exit": sl, "timestamp": str(row["timestamp"])})
                    in_trade = False
                elif low <= tp:
                    pnl = size * abs(entry_price - tp)
                    balance += pnl
                    trades.append({"direction": "SHORT", "result": "WIN", "pnl": round(pnl, 4),
                                   "entry": entry_price, "exit": tp, "timestamp": str(row["timestamp"])})
                    in_trade = False

        # --- New signal (only if flat) ---
        if not in_trade:
            if row.get("long_signal") or row.get("short_signal"):
                atr = row["atr"]
                if atr > 0:
                    entry_price = row["close"]
                    sl_dist = atr * atr_sl_mult
                    if row["long_signal"]:
                        direction = "LONG"
                        sl = entry_price - sl_dist
                        tp = entry_price + sl_dist * rr
                    else:
                        direction = "SHORT"
                        sl = entry_price + sl_dist
                        tp = entry_price - sl_dist * rr
                    risk_amt = balance * risk_pct
                    size = risk_amt / sl_dist
                    in_trade = True

        equity_curve.append({"timestamp": str(row["timestamp"]), "equity": round(balance, 2)})

    # --- Metrics ---
    if not trades:
        return {
            "symbol": symbol, "total_trades": 0,
            "error": "No trades generated. Try longer lookback or different pair."
        }

    trade_df = pd.DataFrame(trades)
    wins = trade_df[trade_df["result"] == "WIN"]
    losses = trade_df[trade_df["result"] == "LOSS"]
    total = len(trade_df)
    win_rate = len(wins) / total * 100
    avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    equity_df = pd.DataFrame(equity_curve)
    eq = equity_df["equity"]
    peak = eq.cummax()
    drawdown = eq - peak
    max_dd = drawdown.min()
    max_dd_pct = (max_dd / peak[drawdown.idxmin()]) * 100 if not drawdown.empty else 0

    returns = eq.pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

    net_pnl = balance - initial_balance
    net_pnl_pct = (net_pnl / initial_balance) * 100

    return {
        "symbol": symbol,
        "period_days": None,
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "sharpe_ratio": round(float(sharpe), 3),
        "max_drawdown": round(float(max_dd), 2),
        "max_drawdown_pct": round(float(max_dd_pct), 2),
        "equity_curve": equity_curve,
    }


# ─── Print Report ────────────────────────────────────────────────────────────

def print_report(r: dict) -> None:
    if r.get("error"):
        print(f"\n[Backtest] {r['symbol']}: {r['error']}")
        return
    verdict = ""
    if r["sharpe_ratio"] > 1.0 and r["win_rate_pct"] > 50:
        verdict = "✅ STRATEGY VIABLE"
    elif r["net_pnl_pct"] > 0:
        verdict = "🟡 MARGINAL — refine entry rules"
    else:
        verdict = "❌ UNPROFITABLE — do not trade live"

    print("\n" + "═" * 56)
    print(f"  BACKTEST REPORT — {r['symbol']}")
    print("═" * 56)
    print(f"  Balance:      ${r['initial_balance']:>10,.2f} → ${r['final_balance']:>10,.2f}")
    print(f"  Net P&L:      ${r['net_pnl']:>+10,.2f}  ({r['net_pnl_pct']:+.1f}%)")
    print(f"  Total Trades: {r['total_trades']}  (W:{r['wins']} / L:{r['losses']})")
    print(f"  Win Rate:     {r['win_rate_pct']:.1f}%")
    print(f"  Avg Win:      ${r['avg_win']:,.2f}")
    print(f"  Avg Loss:     ${r['avg_loss']:,.2f}")
    print(f"  Expectancy:   ${r['expectancy']:,.2f} per trade")
    print(f"  Sharpe Ratio: {r['sharpe_ratio']:.3f}")
    print(f"  Max DD:       ${r['max_drawdown']:,.2f}  ({r['max_drawdown_pct']:.1f}%)")
    print("═" * 56)
    print(f"  {verdict}")
    print("═" * 56 + "\n")


# ─── Save Results ────────────────────────────────────────────────────────────

def save_results(results: list, equity_curves: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    # Save JSON summary (without equity curve to keep it compact)
    summary = [{k: v for k, v in r.items() if k != "equity_curve"} for r in results]
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "results": summary,
        }, f, indent=2)
    print(f"[Backtest] Results saved to {RESULTS_FILE}")

    # Save equity curves as CSV
    dfs = []
    for symbol, curve in equity_curves.items():
        eq_df = pd.DataFrame(curve)
        eq_df["symbol"] = symbol
        dfs.append(eq_df)
    if dfs:
        pd.concat(dfs).to_csv(EQUITY_FILE, index=False)
        print(f"[Backtest] Equity curve saved to {EQUITY_FILE}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    try:
        with open(args.config) as f:
            config = yaml.safe_load(f)
        pairs = config["trading"]["pairs"] if args.all_pairs else [args.pair]
        risk_pct = config["risk"].get("risk_per_trade", args.risk_pct)
        atr_mult = config["risk"].get("atr_sl_multiplier", args.atr_sl_mult)
        min_rr = config["risk"].get("min_rr", args.rr)
    except Exception:
        pairs = [args.pair]
        risk_pct = args.risk_pct
        atr_mult = args.atr_sl_mult
        min_rr = args.rr

    all_results = []
    equity_curves = {}

    for pair in pairs:
        print(f"\n[Backtest] Fetching {pair} 1H data ({args.days} days)...")
        try:
            df = fetch_full_ohlcv(pair, "1h", args.days)
            print(f"[Backtest] {len(df)} candles fetched")
            df = add_indicators(df)
            df = generate_signals(df)

            long_signals = df["long_signal"].sum()
            short_signals = df["short_signal"].sum()
            print(f"[Backtest] Signals: {long_signals} LONG, {short_signals} SHORT")

            result = run_backtest(
                df, symbol=pair,
                initial_balance=args.balance,
                risk_pct=risk_pct,
                atr_sl_mult=atr_mult,
                rr=min_rr,
            )
            result["period_days"] = args.days
            all_results.append(result)
            equity_curves[pair] = result.pop("equity_curve", [])
            print_report(result)

        except Exception as e:
            print(f"[Backtest] ERROR on {pair}: {e}")
            all_results.append({"symbol": pair, "error": str(e)})

    save_results(all_results, equity_curves)

    # Multi-pair summary
    if len(all_results) > 1:
        print("\n" + "═" * 56)
        print("  MULTI-PAIR SUMMARY")
        print("═" * 56)
        print(f"  {'Pair':<12} {'Win%':>6} {'Sharpe':>8} {'MaxDD%':>8} {'NetPnL%':>9}")
        print(f"  {'-'*52}")
        for r in all_results:
            if r.get("error"):
                print(f"  {r['symbol']:<12} ERROR: {r['error'][:30]}")
            else:
                print(f"  {r['symbol']:<12} {r['win_rate_pct']:>5.1f}% {r['sharpe_ratio']:>8.3f} "
                      f"{r['max_drawdown_pct']:>7.1f}% {r['net_pnl_pct']:>+8.1f}%")
        print("═" * 56)
