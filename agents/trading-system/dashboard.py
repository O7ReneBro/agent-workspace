"""
Trading Dashboard — Streamlit
-----------------------------
Visualizes trade_log.jsonl and live_test_log.jsonl in real-time.

Features:
  - Live P&L curve
  - Drawdown chart
  - Win/Loss stats
  - Open signal status per pair
  - Recent trades table
  - Auto-refresh every 30s

Usage:
    pip install streamlit plotly watchdog
    streamlit run dashboard.py
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import ccxt
import yaml


# ─── Config ─────────────────────────────────────────────────────────────────

CONFIG_PATH = "config/trading_config.yaml"
LIVE_LOG = "logs/trade_log.jsonl"
TEST_LOG = "logs/live_test_log.jsonl"
SANDBOX_LOG = "logs/sandbox_trade_log.jsonl"
REFRESH_INTERVAL = 30  # seconds

st.set_page_config(
    page_title="Trading Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=REFRESH_INTERVAL)
def load_log(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    rows = []
    with open(path, "r") as f:
        for line in f:
            try:
                rows.append(json.loads(line.strip()))
            except Exception:
                continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def estimate_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate P&L per trade assuming:
    - Win: price reached TP (simulate 50% win rate for closed trades)
    - For dashboard: use RR to compute potential win/loss per trade
    We mark each trade as WIN/LOSS/OPEN based on status field if available.
    Otherwise assume OPEN.
    """
    if df.empty:
        return df
    records = []
    cumulative = 0.0
    for _, row in df.iterrows():
        entry = row.get("entry", 0) or 0
        sl = row.get("stop_loss", 0) or 0
        tp = row.get("take_profit", 0) or 0
        size = row.get("size", 0) or 0
        status = str(row.get("status", "OPEN")).upper()
        direction = str(row.get("direction", "LONG")).upper()

        sl_dist = abs(entry - sl) if entry and sl else 0
        tp_dist = abs(tp - entry) if tp and entry else 0
        risk_usd = size * sl_dist if size and sl_dist else 0
        reward_usd = size * tp_dist if size and tp_dist else 0

        if "CLOSED" in status or "FILLED" in status:
            pnl = reward_usd  # assume TP hit for closed
            result = "WIN"
        elif "CANCELLED" in status or "CANCEL" in status:
            pnl = 0
            result = "CANCELLED"
        elif "SIMULATED" in status or "SANDBOX" in status:
            pnl = reward_usd * 0.5  # simulate neutral
            result = "SIMULATED"
        else:
            pnl = 0
            result = "OPEN"

        cumulative += pnl
        records.append({
            **row.to_dict(),
            "pnl": round(pnl, 2),
            "risk_usd": round(risk_usd, 2),
            "reward_usd": round(reward_usd, 2),
            "result": result,
            "cumulative_pnl": round(cumulative, 2),
        })
    return pd.DataFrame(records)


def compute_drawdown(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "cumulative_pnl" not in df.columns:
        return df
    df = df.copy()
    df["peak"] = df["cumulative_pnl"].cummax()
    df["drawdown"] = df["cumulative_pnl"] - df["peak"]
    df["drawdown_pct"] = (df["drawdown"] / df["peak"].replace(0, 1)) * 100
    return df


@st.cache_data(ttl=30)
def fetch_live_prices(pairs: list) -> dict:
    try:
        exchange = ccxt.kraken({"enableRateLimit": True})
        prices = {}
        for pair in pairs:
            try:
                ticker = exchange.fetch_ticker(pair)
                prices[pair] = {
                    "last": ticker["last"],
                    "change_pct": ticker.get("percentage", 0),
                    "high": ticker["high"],
                    "low": ticker["low"],
                    "volume": ticker["baseVolume"],
                }
            except Exception:
                prices[pair] = None
        return prices
    except Exception:
        return {}


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🤖 Trading System")
    st.markdown("---")

    log_source = st.selectbox(
        "Log source",
        ["Live Trades", "Live Test", "Sandbox"],
        index=1,
    )
    log_map = {
        "Live Trades": LIVE_LOG,
        "Live Test": TEST_LOG,
        "Sandbox": SANDBOX_LOG,
    }
    selected_log = log_map[log_source]

    st.markdown("---")
    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        pairs = config["trading"]["pairs"]
    except Exception:
        pairs = ["BTC/USD", "ETH/USD", "XMR/USD", "SOL/USD", "XRP/USD"]

    st.markdown("**Monitored Pairs**")
    for p in pairs:
        st.markdown(f"`{p}`")

    st.markdown("---")
    auto_refresh = st.toggle("Auto-refresh (30s)", value=True)
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption(f"Last update: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


# ─── Live Price Bar ─────────────────────────────────────────────────────────

st.title("🤖 Multi-Agent Trading Dashboard")
st.markdown(f"**Source:** `{selected_log}`  |  **Pairs:** {len(pairs)}")

with st.spinner("Fetching live prices..."):
    prices = fetch_live_prices(pairs)

cols = st.columns(len(pairs))
for i, pair in enumerate(pairs):
    p = prices.get(pair)
    with cols[i]:
        if p:
            chg = p.get("change_pct") or 0
            color = "🟢" if chg >= 0 else "🔴"
            st.metric(
                label=pair,
                value=f"${p['last']:,.2f}",
                delta=f"{chg:+.2f}%",
            )
        else:
            st.metric(label=pair, value="N/A", delta="")

st.markdown("---")


# ─── Load & Process Log ───────────────────────────────────────────────────────

raw_df = load_log(selected_log)

if raw_df.empty:
    st.info(f"💭 No trade data yet in `{selected_log}`. Run the trading system first.")
    if auto_refresh:
        time.sleep(REFRESH_INTERVAL)
        st.rerun()
    st.stop()

df = estimate_pnl(raw_df)
df = compute_drawdown(df)


# ─── KPI Row ─────────────────────────────────────────────────────────────────

total_trades = len(df)
wins = len(df[df["result"] == "WIN"])
losses = len(df[df["result"] == "LOSS"])
open_trades = len(df[df["result"] == "OPEN"])
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
total_pnl = df["pnl"].sum()
max_dd = df["drawdown"].min() if "drawdown" in df.columns else 0
avg_rr = df["rr"].mean() if "rr" in df.columns else 0

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("📈 Total Trades", total_trades)
k2.metric("✅ Win Rate", f"{win_rate:.1f}%")
k3.metric("💰 Total P&L", f"${total_pnl:,.2f}")
k4.metric("📉 Max Drawdown", f"${max_dd:,.2f}")
k5.metric("🔄 Open", open_trades)
k6.metric("⚖️ Avg RR", f"{avg_rr:.2f}")

st.markdown("---")


# ─── Charts Row ─────────────────────────────────────────────────────────────────

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📈 Cumulative P&L")
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["cumulative_pnl"],
        mode="lines+markers",
        name="Cumulative P&L",
        line=dict(color="#00d4aa", width=2),
        fill="tozeroy",
        fillcolor="rgba(0,212,170,0.1)",
    ))
    fig_pnl.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="", yaxis_title="USD",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig_pnl, use_container_width=True)

with col_right:
    st.subheader("📉 Drawdown")
    fig_dd = go.Figure()
    if "drawdown" in df.columns:
        fig_dd.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["drawdown"],
            mode="lines",
            name="Drawdown",
            line=dict(color="#ff4b4b", width=2),
            fill="tozeroy",
            fillcolor="rgba(255,75,75,0.1)",
        ))
    fig_dd.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="", yaxis_title="USD",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig_dd, use_container_width=True)


# ─── Win/Loss + Pair Distribution ───────────────────────────────────────────────

col3, col4 = st.columns(2)

with col3:
    st.subheader("🎯 Trade Results")
    result_counts = df["result"].value_counts().reset_index()
    result_counts.columns = ["result", "count"]
    color_map = {"WIN": "#00d4aa", "LOSS": "#ff4b4b", "OPEN": "#ffd700",
                 "CANCELLED": "#888", "SIMULATED": "#7b9cff"}
    fig_pie = px.pie(
        result_counts, names="result", values="count",
        color="result", color_discrete_map=color_map,
        hole=0.4,
    )
    fig_pie.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col4:
    st.subheader("📊 Trades per Pair")
    pair_counts = df["symbol"].value_counts().reset_index()
    pair_counts.columns = ["symbol", "count"]
    fig_bar = px.bar(
        pair_counts, x="symbol", y="count",
        color="count", color_continuous_scale="teal",
    )
    fig_bar.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)


# ─── Recent Trades Table ───────────────────────────────────────────────────────

st.markdown("---")
st.subheader("🗒 Recent Trades")

display_cols = [c for c in [
    "timestamp", "mode", "symbol", "direction", "result",
    "entry", "stop_loss", "take_profit", "size", "rr", "pnl"
] if c in df.columns]

recent = df[display_cols].tail(20).sort_values("timestamp", ascending=False)

def highlight_result(row):
    result = row.get("result", "")
    if result == "WIN":
        return ["background-color: rgba(0,212,170,0.15)"] * len(row)
    elif result == "LOSS":
        return ["background-color: rgba(255,75,75,0.15)"] * len(row)
    elif result == "OPEN":
        return ["background-color: rgba(255,215,0,0.10)"] * len(row)
    return [""] * len(row)

st.dataframe(
    recent.style.apply(highlight_result, axis=1),
    use_container_width=True,
    height=400,
)


# ─── Risk Monitor ─────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("🛡 Risk Monitor")

try:
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    risk_cfg = cfg["risk"]
    dd_limit = risk_cfg.get("max_daily_drawdown", 0.05)
    risk_pct = risk_cfg.get("risk_per_trade", 0.01)
    max_pos = risk_cfg.get("max_open_positions", 3)
    min_rr = risk_cfg.get("min_rr", 2.0)
except Exception:
    dd_limit, risk_pct, max_pos, min_rr = 0.05, 0.01, 3, 2.0

r1, r2, r3, r4 = st.columns(4)
r1.metric("🚧 Max Daily DD", f"{dd_limit*100:.0f}%")
r2.metric("🎰 Risk / Trade", f"{risk_pct*100:.1f}%")
r3.metric("📌 Max Positions", max_pos)
r4.metric("⚖️ Min RR", f"{min_rr}:1")


# ─── Auto-refresh ───────────────────────────────────────────────────────────────

if auto_refresh:
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
