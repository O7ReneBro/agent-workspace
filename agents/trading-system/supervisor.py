"""
Supervisor — LangGraph-based Multi-Agent Trading Orchestrator
Flow:
  1. Market Scanner → signals
  2. Ollama LLM review (optional qualitative filter)
  3. Risk Manager → validated signals
  4. Execution Agent → live orders

Requires: langgraph, ollama, ccxt, pyyaml
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator
import yaml
import requests
import json

from market_scanner import run_scanner
from risk_manager import validate_signal, load_config
from execution_agent import execute_signal


# ─── State Schema ────────────────────────────────────────────────────────────

class TradingState(TypedDict):
    config: dict
    raw_signals: list
    llm_filtered_signals: list
    validated_signals: list
    account_balance: float
    open_positions: int
    execution_results: Annotated[list, operator.add]


# ─── Node: Market Scanner ─────────────────────────────────────────────────────

def node_scanner(state: TradingState) -> dict:
    print("\n[Supervisor] >>> Running Market Scanner...")
    signals = run_scanner(state["config"])
    # Filter to actionable only
    actionable = [s for s in signals if s["direction"] != "NO_TRADE"]
    print(f"[Supervisor] {len(actionable)}/{len(signals)} pairs have signals")
    return {"raw_signals": signals, "llm_filtered_signals": actionable}


# ─── Node: Ollama LLM Filter ──────────────────────────────────────────────────

def query_ollama(prompt: str, model: str = "llama3", host: str = "http://localhost:11434") -> str:
    """Send prompt to local Ollama instance, return response text."""
    response = requests.post(
        f"{host}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=60,
    )
    return response.json().get("response", "")


def node_llm_filter(state: TradingState) -> dict:
    print("\n[Supervisor] >>> Ollama LLM qualitative filter...")
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
- Last Price: {signal['last_price']}

Rules:
- Only pass UPTREND+LONG or DOWNTREND+SHORT
- RSI must not be overbought/oversold (>75 or <25)
- BOS must match direction
- Reject RANGING markets

Respond ONLY with JSON."""

        try:
            raw = query_ollama(prompt, model=model, host=host)
            # Extract JSON from response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            result = json.loads(raw[start:end])
            if result.get("pass", False):
                passed.append(signal)
                print(f"[LLM] PASS {signal['symbol']}: {result.get('reason')}")
            else:
                print(f"[LLM] REJECT {signal['symbol']}: {result.get('reason')}")
        except Exception as e:
            print(f"[LLM] Error filtering {signal['symbol']}: {e} — passing through")
            passed.append(signal)  # fail-open: don't block on LLM error

    return {"llm_filtered_signals": passed}


# ─── Node: Risk Manager ───────────────────────────────────────────────────────

def node_risk_manager(state: TradingState) -> dict:
    print("\n[Supervisor] >>> Risk Manager validation...")
    validated = []
    for signal in state["llm_filtered_signals"]:
        result = validate_signal(
            signal=signal,
            config=state["config"],
            account_balance=state["account_balance"],
            open_positions=state["open_positions"],
        )
        if result["approved"]:
            print(f"[Risk] APPROVED {signal['symbol']} | Size={result['position_size']} | RR={result['actual_rr']}")
        else:
            print(f"[Risk] REJECTED {signal['symbol']}: {result['reject_reason']}")
        validated.append(result)
    return {"validated_signals": validated}


# ─── Node: Execution ──────────────────────────────────────────────────────────

def node_execution(state: TradingState) -> dict:
    print("\n[Supervisor] >>> Execution Agent...")
    results = []
    for signal in state["validated_signals"]:
        execute_signal(signal, state["config"])
        results.append({
            "symbol": signal["symbol"],
            "approved": signal["approved"],
            "direction": signal.get("direction"),
        })
    return {"execution_results": results}


# ─── Build LangGraph ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(TradingState)
    g.add_node("scanner", node_scanner)
    g.add_node("llm_filter", node_llm_filter)
    g.add_node("risk_manager", node_risk_manager)
    g.add_node("execution", node_execution)

    g.set_entry_point("scanner")
    g.add_edge("scanner", "llm_filter")
    g.add_edge("llm_filter", "risk_manager")
    g.add_edge("risk_manager", "execution")
    g.add_edge("execution", END)

    return g.compile()


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = load_config()
    # Fetch live account balance from Kraken
    import ccxt
    exchange = ccxt.kraken({
        "apiKey": config["kraken"]["api_key"],
        "secret": config["kraken"]["api_secret"],
        "enableRateLimit": True,
    })
    balance = exchange.fetch_balance()
    usd_balance = balance["total"].get("USD", 0.0)
    open_pos = len(exchange.fetch_open_orders())

    graph = build_graph()
    final_state = graph.invoke({
        "config": config,
        "raw_signals": [],
        "llm_filtered_signals": [],
        "validated_signals": [],
        "account_balance": usd_balance,
        "open_positions": open_pos,
        "execution_results": [],
    })

    print("\n[Supervisor] === RUN COMPLETE ===")
    for r in final_state["execution_results"]:
        print(f"  {r['symbol']}: {'✓' if r['approved'] else '✗'} {r.get('direction','')}")
