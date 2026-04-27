"""
Telegram Alert Node
- Sends trade signal notifications to a Telegram bot
- Called between Risk Manager and Execution Agent in the LangGraph graph
- Uses Bot API (no extra library needed, just requests)

Setup:
  1. Create bot via @BotFather -> get BOT_TOKEN
  2. Get your CHAT_ID (message the bot, then check:
     https://api.telegram.org/bot<TOKEN>/getUpdates)
  3. Set env vars:
     export TELEGRAM_BOT_TOKEN=your_token
     export TELEGRAM_CHAT_ID=your_chat_id
"""

import os
import requests
from datetime import datetime, timezone


DEFAULT_TIMEOUT = 10


def send_message(text: str, bot_token: str = None, chat_id: str = None) -> bool:
    """Send a plain text message via Telegram Bot API."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cid = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not cid:
        print("[Telegram] WARNING: BOT_TOKEN or CHAT_ID not set. Skipping alert.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            print(f"[Telegram] Alert sent.")
            return True
        else:
            print(f"[Telegram] Failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def format_signal_message(signal: dict) -> str:
    """Format an approved/rejected signal into a readable Telegram message."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    symbol = signal.get("symbol", "?")
    direction = signal.get("direction", "?")
    approved = signal.get("approved", False)
    status = "✅ APPROVED" if approved else "❌ REJECTED"
    reason = signal.get("reject_reason", "")

    if approved:
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        size = signal.get("position_size", 0)
        rr = signal.get("actual_rr", 0)
        msg = (
            f"*🤖 Trading Signal*\n"
            f"`{ts}`\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"*Pair:* `{symbol}`\n"
            f"*Direction:* `{direction}`\n"
            f"*Status:* {status}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"*Entry:* `{entry}`\n"
            f"*Stop Loss:* `{sl}`\n"
            f"*Take Profit:* `{tp}`\n"
            f"*Size:* `{size}`\n"
            f"*RR:* `{rr:.2f}:1`\n"
        )
    else:
        msg = (
            f"*🤖 Trading Signal*\n"
            f"`{ts}`\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"*Pair:* `{symbol}`\n"
            f"*Direction:* `{direction}`\n"
            f"*Status:* {status}\n"
            f"*Reason:* `{reason}`\n"
        )
    return msg


def format_run_summary(execution_results: list) -> str:
    """Send a summary after each supervisor run."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    approved = [r for r in execution_results if r.get("approved")]
    rejected = [r for r in execution_results if not r.get("approved")]
    lines = [
        f"*📊 Run Summary* — `{ts}`",
        f"━━━━━━━━━━━━━━━━",
        f"✅ Executed: {len(approved)}",
        f"❌ Skipped: {len(rejected)}",
    ]
    for r in approved:
        lines.append(f"  • `{r['symbol']}` {r.get('direction','')}")
    return "\n".join(lines)
