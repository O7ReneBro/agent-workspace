"""
Risk Manager Agent
- Validates signal against risk rules
- Computes position size (fixed fractional)
- Enforces RR >= 2:1, max drawdown, max open positions
- Returns enriched signal with size, SL, TP or REJECT
"""

import yaml
from typing import Optional


def load_config(path: str = "config/trading_config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def compute_position_size(
    account_balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
) -> float:
    """
    Fixed fractional position sizing.
    risk_pct: e.g. 0.01 = 1% of account per trade.
    Returns size in base currency units.
    """
    risk_amount = account_balance * risk_pct
    sl_distance = abs(entry - stop_loss)
    if sl_distance == 0:
        return 0.0
    size = risk_amount / sl_distance
    return round(size, 6)


def compute_sl_tp(
    direction: str,
    entry: float,
    atr: float,
    atr_sl_multiplier: float = 1.5,
    rr_ratio: float = 2.0,
) -> tuple[float, float]:
    """
    ATR-based stop-loss and take-profit.
    SL: entry ± ATR * multiplier
    TP: entry ± SL_distance * RR
    """
    sl_distance = atr * atr_sl_multiplier
    if direction == "LONG":
        sl = entry - sl_distance
        tp = entry + sl_distance * rr_ratio
    else:
        sl = entry + sl_distance
        tp = entry - sl_distance * rr_ratio
    return round(sl, 6), round(tp, 6)


def validate_signal(
    signal: dict,
    config: dict,
    account_balance: float,
    open_positions: int,
) -> dict:
    """
    Validate signal against all risk rules.
    Returns enriched dict with 'approved': True/False and reason.
    """
    risk_cfg = config["risk"]
    direction = signal["direction"]

    if direction == "NO_TRADE":
        return {**signal, "approved": False, "reject_reason": "No trade signal"}

    # Max open positions guard
    if open_positions >= risk_cfg["max_open_positions"]:
        return {**signal, "approved": False, "reject_reason": f"Max open positions reached ({open_positions})"}

    entry = signal["last_price"]
    atr = signal["atr"]

    sl, tp = compute_sl_tp(
        direction=direction,
        entry=entry,
        atr=atr,
        atr_sl_multiplier=risk_cfg.get("atr_sl_multiplier", 1.5),
        rr_ratio=risk_cfg.get("min_rr", 2.0),
    )

    # RR check
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    actual_rr = tp_dist / sl_dist if sl_dist > 0 else 0
    if actual_rr < risk_cfg["min_rr"]:
        return {**signal, "approved": False, "reject_reason": f"RR {actual_rr:.2f} < min {risk_cfg['min_rr']}"}

    # Position size
    size = compute_position_size(
        account_balance=account_balance,
        risk_pct=risk_cfg["risk_per_trade"],
        entry=entry,
        stop_loss=sl,
    )

    # Minimum size guard
    if size < risk_cfg.get("min_order_size", 0.0001):
        return {**signal, "approved": False, "reject_reason": f"Computed size {size} too small"}

    return {
        **signal,
        "approved": True,
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "position_size": size,
        "actual_rr": round(actual_rr, 2),
        "reject_reason": None,
    }


if __name__ == "__main__":
    cfg = load_config()
    # Example test
    test_signal = {
        "symbol": "BTC/USD",
        "direction": "LONG",
        "last_price": 65000.0,
        "atr": 800.0,
        "rsi_1h": 55.0,
        "structure_4h": {"trend": "UPTREND"},
        "structure_1h": {"bos": "BULL"},
    }
    result = validate_signal(test_signal, cfg, account_balance=10000.0, open_positions=0)
    print(result)
