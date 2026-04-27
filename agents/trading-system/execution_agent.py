"""
Execution Agent
- Receives approved signal from Risk Manager
- Places live order on Kraken via ccxt
- Sets stop-loss and take-profit orders
- Logs all trades to trade_log.jsonl
"""

import ccxt
import yaml
import json
import os
from datetime import datetime, timezone
from typing import Optional


def load_config(path: str = "config/trading_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_exchange(config: dict) -> ccxt.Exchange:
    return ccxt.kraken({
        "apiKey": config["kraken"]["api_key"],
        "secret": config["kraken"]["api_secret"],
        "enableRateLimit": True,
    })


def log_trade(signal: dict, order_result: dict, log_path: str = "logs/trade_log.jsonl") -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "size": signal["position_size"],
        "rr": signal["actual_rr"],
        "order_id": order_result.get("id"),
        "status": order_result.get("status"),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Log] Trade logged: {entry}")


def place_order(exchange: ccxt.Exchange, signal: dict, config: dict) -> Optional[dict]:
    """
    Place market entry + stop-loss limit order on Kraken.
    Returns order dict or None on failure.
    """
    symbol = signal["symbol"]
    side = "buy" if signal["direction"] == "LONG" else "sell"
    size = signal["position_size"]
    sl = signal["stop_loss"]
    tp = signal["take_profit"]

    try:
        # Market entry order
        order = exchange.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=size,
        )
        print(f"[Execution] Market order placed: {symbol} {side} {size} @ market")
        print(f"[Execution] Order ID: {order.get('id')} | Status: {order.get('status')}")

        # Stop-loss order (opposite side)
        sl_side = "sell" if side == "buy" else "buy"
        sl_order = exchange.create_order(
            symbol=symbol,
            type="stop-loss",
            side=sl_side,
            amount=size,
            price=sl,
        )
        print(f"[Execution] SL order placed @ {sl}")

        # Take-profit order
        tp_order = exchange.create_order(
            symbol=symbol,
            type="limit",
            side=sl_side,
            amount=size,
            price=tp,
        )
        print(f"[Execution] TP order placed @ {tp}")

        return order

    except ccxt.InsufficientFunds as e:
        print(f"[Execution] INSUFFICIENT FUNDS: {e}")
        return None
    except ccxt.InvalidOrder as e:
        print(f"[Execution] INVALID ORDER: {e}")
        return None
    except Exception as e:
        print(f"[Execution] ERROR: {e}")
        return None


def execute_signal(signal: dict, config: dict) -> None:
    if not signal.get("approved"):
        print(f"[Execution] SKIP {signal['symbol']}: {signal.get('reject_reason')}")
        return

    exchange = get_exchange(config)
    order = place_order(exchange, signal, config)
    if order:
        log_trade(signal, order)
    else:
        print(f"[Execution] FAILED to execute {signal['symbol']}")


if __name__ == "__main__":
    cfg = load_config()
    test_signal = {
        "symbol": "BTC/USD",
        "direction": "LONG",
        "entry": 65000.0,
        "stop_loss": 63800.0,
        "take_profit": 67400.0,
        "position_size": 0.002,
        "actual_rr": 2.0,
        "approved": True,
        "reject_reason": None,
    }
    execute_signal(test_signal, cfg)
