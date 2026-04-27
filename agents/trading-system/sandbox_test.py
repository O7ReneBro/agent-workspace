"""
Sandbox Test Runner
-------------------
Runs the full Multi-Agent Trading System pipeline WITHOUT:
  - Real Kraken API calls
  - Real order placement
  - Real account balance

Uses:
  - Mock exchange (ccxt sandbox or pure mock)
  - Configurable fake balance
  - All agents run normally (Scanner reads real market data via public endpoints)
  - Execution Agent logs to sandbox_trade_log.jsonl instead of placing orders
  - Telegram alerts work normally (or can be muted)

Usage:
    python sandbox_test.py
    python sandbox_test.py --balance 5000 --mute-telegram
    python sandbox_test.py --mock-signals  # skip real OHLCV, use injected signals
"""

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Optional

import yaml
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator


# ─── Argument Parser ─────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Sandbox Test Runner for Trading System")
    p.add_argument("--balance", type=float, default=10000.0,
                   help="Simulated account balance in USD (default: 10000)")
    p.add_argument("--open-positions", type=int, default=0,
                   help="Simulated number of open positions (default: 0)")
    p.add_argument("--mute-telegram", action="store_true",
                   help="Suppress Telegram alerts during sandbox run")
    p.add_argument("--mock-signals", action="store_true",
                   help="Skip real OHLCV fetch, inject predefined test signals")
    p.add_argument("--config", type=str, default="config/trading_config.yaml",
                   help="Path to trading config YAML")
    return p.parse_args()


# ─── Mock Signals (used with --mock-signals) ─────────────────────────────────

MOCK_SIGNALS = [
    {
        "symbol": "BTC/USD",
        "direction": "LONG",
        "last_price": 65000.0,
        "atr": 850.0,
        "rsi_1h": 54.2,
        "structure_4h": {"trend": "UPTREND", "bos": "BULL", "recent_high": 66200.0, "recent_low": 63500.0, "last_close": 65000.0},
        "structure_1h": {"trend": "UPTREND", "bos": "BULL", "recent_high": 65500.0, "recent_low": 64200.0, "last_close": 65000.0},
    },
    {
        "symbol": "ETH/USD",
        "direction": "SHORT",
        "last_price": 3100.0,
        "atr": 70.0,
        "rsi_1h": 68.5,
        "structure_4h": {"trend": "DOWNTREND", "bos": "BEAR", "recent_high": 3250.0, "recent_low": 3050.0, "last_close": 3100.0},
        "structure_1h": {"trend": "DOWNTREND", "bos": "BEAR", "recent_high": 3180.0, "recent_low": 3090.0, "last_close": 3100.0},
    },
    {
        "symbol": "SOL/USD",
        "direction": "NO_TRADE",
        "last_price": 145.0,
        "atr": 5.2,
        "rsi_1h": 51.0,
        "structure_4h": {"trend": "RANGING", "bos": "NONE", "recent_high": 150.0, "recent_low": 140.0, "last_close": 145.0},
        "structure_1h": {"trend": "RANGING", "bos": "NONE", "recent_high": 147.0, "recent_low": 143.0, "last_close": 145.0},
    },
]


# ─── Mock Execution (no real orders) ─────────────────────────────────────────

def mock_execute_signal(signal: dict, log_path: str = "logs/sandbox_trade_log.jsonl") -> None:
    """Log the signal as if it were executed, without touching Kraken API."""
    if not signal.get("approved"):
        print(f"[Sandbox Exec] SKIP {signal['symbol']}: {signal.get('reject_reason')}")
        return

    fake_order_id = f"SANDBOX-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{signal['symbol'].replace('/', '')}"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "SANDBOX",
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "size": signal["position_size"],
        "rr": signal["actual_rr"],
        "order_id": fake_order_id,
        "status": "SIMULATED",
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Sandbox Exec] ✓ SIMULATED {signal['symbol']} {signal['direction']} | Entry={signal['entry']} SL={signal['stop_loss']} TP={signal['take_profit']} Size={signal['position_size']} RR={signal['actual_rr']}")


# ─── State Schema ─────────────────────────────────────────────────────────────

class TradingState(TypedDict):
    config: dict
    raw_signals: list
    llm_filtered_signals: list
    validated_signals: list
    account_balance: float
    open_positions: int
    execution_results: Annotated[list, operator.add]
    sandbox_mode: bool
    mute_telegram: bool


# ─── Nodes ────────────────────────────────────────────────────────────────────

def node_scanner(state: TradingState) -> dict:
    print("\n[Sandbox] >>> Market Scanner...")
    if state.get("_mock_signals"):
        signals = state["_mock_signals"]
        print(f"[Sandbox] Using {len(signals)} injected mock signals")
    else:
        from market_scanner import run_scanner
        signals = run_scanner(state["config"])
    actionable = [s for s in signals if s["direction"] != "NO_TRADE"]
    print(f"[Sandbox] {len(actionable)}/{len(signals)} actionable signals")
    return {"raw_signals": signals, "llm_filtered_signals": actionable}


def node_llm_filter(state: TradingState) -> dict:
    print("\n[Sandbox] >>> Ollama LLM filter...")
    import requests, json as _json
    cfg = state["config"]
    model = cfg.get("ollama", {}).get("model", "llama3")
    host = cfg.get("ollama", {}).get("host", "http://localhost:11434")
    passed = []

    for signal in state["llm_filtered_signals"]:
        prompt = f"""You are a professional trading risk analyst.
Evaluate this trade signal and respond with only JSON: {{"pass": true/false, "reason": "short reason"}}

Signal:
- Symbol: {signal['symbol']}
- Direction: {signal['direction']}
- 4H Trend: {signal['structure_4h']['trend']}
- 1H BOS: {signal['structure_1h']['bos']}
- RSI (1H): {signal['rsi_1h']:.1f}
- ATR: {signal['atr']:.4f}

Rules: Only UPTREND+LONG or DOWNTREND+SHORT. RSI not >75 or <25. BOS must match. Reject RANGING.
Respond ONLY with JSON."""
        try:
            resp = requests.post(f"{host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False}, timeout=30)
            raw = resp.json().get("response", "")
            start, end = raw.find("{"), raw.rfind("}") + 1
            result = _json.loads(raw[start:end])
            if result.get("pass", False):
                passed.append(signal)
                print(f"[LLM] PASS {signal['symbol']}: {result.get('reason')}")
            else:
                print(f"[LLM] REJECT {signal['symbol']}: {result.get('reason')}")
        except Exception as e:
            print(f"[LLM] Error on {signal['symbol']}: {e} — passing through")
            passed.append(signal)
    return {"llm_filtered_signals": passed}


def node_risk_manager(state: TradingState) -> dict:
    print("\n[Sandbox] >>> Risk Manager...")
    from risk_manager import validate_signal
    validated = []
    for signal in state["llm_filtered_signals"]:
        result = validate_signal(
            signal=signal,
            config=state["config"],
            account_balance=state["account_balance"],
            open_positions=state["open_positions"],
        )
        tag = "APPROVED ✓" if result["approved"] else f"REJECTED: {result['reject_reason']}"
        print(f"[Risk] {signal['symbol']}: {tag}")
        validated.append(result)
    return {"validated_signals": validated}


def node_telegram_alerts(state: TradingState) -> dict:
    if state.get("mute_telegram"):
        print("\n[Sandbox] >>> Telegram alerts MUTED")
        return {}
    print("\n[Sandbox] >>> Telegram alerts...")
    from telegram_alert import send_message, format_signal_message
    for signal in state["validated_signals"]:
        msg = format_signal_message(signal)
        send_message(msg)
    return {}


def node_execution(state: TradingState) -> dict:
    print("\n[Sandbox] >>> Execution (SIMULATED — no real orders)...")
    results = []
    for signal in state["validated_signals"]:
        mock_execute_signal(signal)
        results.append({
            "symbol": signal["symbol"],
            "approved": signal["approved"],
            "direction": signal.get("direction"),
        })
    return {"execution_results": results}


def node_telegram_summary(state: TradingState) -> dict:
    if state.get("mute_telegram"):
        return {}
    from telegram_alert import send_message, format_run_summary
    msg = format_run_summary(state["execution_results"])
    send_message(msg)
    return {}


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_sandbox_graph() -> StateGraph:
    g = StateGraph(TradingState)
    g.add_node("scanner", node_scanner)
    g.add_node("llm_filter", node_llm_filter)
    g.add_node("risk_manager", node_risk_manager)
    g.add_node("telegram_alerts", node_telegram_alerts)
    g.add_node("execution", node_execution)
    g.add_node("telegram_summary", node_telegram_summary)

    g.set_entry_point("scanner")
    g.add_edge("scanner", "llm_filter")
    g.add_edge("llm_filter", "risk_manager")
    g.add_edge("risk_manager", "telegram_alerts")
    g.add_edge("telegram_alerts", "execution")
    g.add_edge("execution", "telegram_summary")
    g.add_edge("telegram_summary", END)

    return g.compile()


# ─── Print Report ─────────────────────────────────────────────────────────────

def print_report(final_state: dict) -> None:
    print("\n" + "=" * 52)
    print("  SANDBOX RUN REPORT")
    print("=" * 52)
    print(f"  Balance used:    ${final_state['account_balance']:,.2f} (simulated)")
    print(f"  Open positions:  {final_state['open_positions']} (simulated)")
    print(f"  Pairs scanned:   {len(final_state['raw_signals'])}")
    print(f"  Signals found:   {sum(1 for s in final_state['raw_signals'] if s['direction'] != 'NO_TRADE')}")
    print(f"  After LLM filter:{len(final_state['llm_filtered_signals'])}")
    approved = [s for s in final_state['validated_signals'] if s.get('approved')]
    rejected = [s for s in final_state['validated_signals'] if not s.get('approved')]
    print(f"  Approved:        {len(approved)}")
    print(f"  Rejected:        {len(rejected)}")
    print("=" * 52)
    for s in approved:
        print(f"  ✓ {s['symbol']:12} {s['direction']:6} | Entry={s['entry']} SL={s['stop_loss']} TP={s['take_profit']} Size={s['position_size']} RR={s['actual_rr']}")
    for s in rejected:
        print(f"  ✗ {s['symbol']:12} REJECTED: {s.get('reject_reason')}")
    print("=" * 52)
    print("  Trade log: logs/sandbox_trade_log.jsonl")
    print("=" * 52 + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    mock_signals = MOCK_SIGNALS if args.mock_signals else None

    print(f"""
╔══════════════════════════════════════════════════╗
║        TRADING SYSTEM — SANDBOX MODE            ║
║  Balance: ${args.balance:>10,.2f} (simulated)        ║
║  Orders:  NO REAL ORDERS WILL BE PLACED         ║
╚══════════════════════════════════════════════════╝""")

    graph = build_sandbox_graph()
    initial_state = {
        "config": config,
        "raw_signals": [],
        "llm_filtered_signals": [],
        "validated_signals": [],
        "account_balance": args.balance,
        "open_positions": args.open_positions,
        "execution_results": [],
        "sandbox_mode": True,
        "mute_telegram": args.mute_telegram,
    }
    if mock_signals:
        initial_state["_mock_signals"] = mock_signals

    final_state = graph.invoke(initial_state)
    print_report(final_state)
