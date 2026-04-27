# Multi-Agent Trading System

## Overview

A LangGraph-orchestrated multi-agent system for live trading on Kraken across multiple crypto pairs.
Local Ollama LLM provides a qualitative filter layer between rule-based signal generation and execution.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   SUPERVISOR                        │
│              (LangGraph StateGraph)                 │
└──────────┬──────────┬──────────┬────────────────────┘
           │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼──────────┐
    │ Market  │ │  Ollama  │ │    Risk     │
    │ Scanner │→│ LLM Filter│→│  Manager   │
    └─────────┘ └──────────┘ └──────┬──────┘
                                    │
                             ┌──────▼──────┐
                             │  Execution  │
                             │   Agent     │
                             └─────────────┘
```

## Agents

### 1. Market Scanner
- **File**: `agents/trading-system/market_scanner.py`
- **Fetches**: OHLCV data via ccxt (Kraken) for all configured pairs
- **Analyzes**: 4H structure (HH/HL), 1H BOS, RSI, ATR
- **Outputs**: Signal dict with direction (LONG/SHORT/NO_TRADE)

### 2. Ollama LLM Filter
- **Model**: Local Ollama (llama3 / mistral / qwen2.5 — configurable)
- **Role**: Qualitative second-opinion on each signal
- **Prompt**: Structured JSON response — pass/reject with reason
- **Fail-safe**: On LLM error, signal passes through (fail-open)

### 3. Risk Manager
- **File**: `agents/trading-system/risk_manager.py`
- **Validates**: RR ≥ 2:1, max open positions, minimum order size
- **Computes**: ATR-based SL/TP, fixed-fractional position size (1% risk)
- **Outputs**: Enriched signal with entry, SL, TP, size, approved flag

### 4. Execution Agent
- **File**: `agents/trading-system/execution_agent.py`
- **Places**: Market entry + stop-loss + take-profit orders on Kraken
- **Logs**: All trades to `logs/trade_log.jsonl`
- **Handles**: InsufficientFunds, InvalidOrder, network errors gracefully

## Setup

### 1. Install dependencies
```bash
cd agents/trading-system
pip install -r requirements.txt
```

### 2. Configure
```bash
# Edit config/trading_config.yaml
# Fill in Kraken API key/secret
# Set pairs, risk parameters, Ollama model
```

⚠️ **Never commit real API keys.** Use environment variables:
```bash
export KRAKEN_API_KEY=your_key
export KRAKEN_API_SECRET=your_secret
```
Then update `trading_config.yaml` to read from env:
```python
import os
api_key = os.environ["KRAKEN_API_KEY"]
```

### 3. Start Ollama
```bash
ollama pull llama3
ollama serve
```

### 4. Run
```bash
cd agents/trading-system
python supervisor.py
```

## Running on a Schedule (cron)
```bash
# Every 15 minutes
*/15 * * * * cd /path/to/agent-workspace/agents/trading-system && python supervisor.py >> /var/log/trading.log 2>&1
```

## Risk Parameters (defaults)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade` | 1% | Account % risked per trade |
| `min_rr` | 2.0 | Minimum reward:risk ratio |
| `max_open_positions` | 3 | Max simultaneous open trades |
| `atr_sl_multiplier` | 1.5 | SL distance = ATR × 1.5 |
| `max_daily_drawdown` | 5% | Manual DD limit (log-based) |

## Trade Log

All executed trades are appended to `logs/trade_log.jsonl`.
Each entry contains: timestamp, symbol, direction, entry, SL, TP, size, RR, order ID, status.

## Extending

- **Add pairs**: Edit `trading.pairs` in `trading_config.yaml`
- **Change model**: Set `ollama.model` (e.g. `mistral`, `qwen2.5:14b`)
- **Add indicators**: Extend `market_scanner.py` (volume, VWAP, funding rate)
- **Telegram alerts**: Add a notification node between Risk Manager and Execution
- **Backtesting**: Run `market_scanner.py` in isolation with historical data
