# Trading System Agent

## Role
Multi-agent trading system orchestrated by a LangGraph Supervisor. Coordinates three specialized sub-agents to execute live trades on Kraken across multiple pairs using local Ollama LLM for decision support.

## Sub-Agents
- **market-scanner** — OHLCV data ingestion, BOS/HH/HL structure analysis, signal generation
- **risk-manager** — Position sizing, RR filter, drawdown guard, checklist validation
- **execution** — Kraken API order placement, trade logging, error handling

## Entry Rules (Rule-Based Core)
1. HTF (4H) must show clear HH/HL or LH/LL structure
2. BOS confirmed on 1H
3. Pullback entry on 15M after BOS retest
4. RR ≥ 2:1 mandatory
5. Stop-loss: 5–10 USD beyond prior wick
6. No trade during extreme funding rates (>±400 Hyblock)

## Skills Used
- `market-analysis`
- `risk-calculation`
- `kraken-execution`

## LLM Role
Ollama (local) acts as Supervisor reasoning layer — it receives structured market context from Scanner, validates against rules, and instructs Execution Agent. Model: `llama3` or `mistral` (configurable).

## Config
See `config/trading_config.yaml`
