#!/usr/bin/env python3
"""
Investment Price Monitor
Monitors Tencent HK/US stocks and BTC/USD for 24-hour price changes >= 5%.
Designed to run every 10 minutes via GitHub Actions.
"""

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yfinance as yf

# ── Configuration ────────────────────────────────────────────────────────────
WATCHLIST = {
    "腾讯港股 (0700.HK)": "0700.HK",
    "腾讯美股 (TCEHY)":   "TCEHY",
    "比特币 (BTC/USD)":   "BTC-USD",
}

THRESHOLD_PCT  = 5.0  # trigger alert when |24h change| >= this percentage
COOLDOWN_HOURS = 4    # minimum hours between repeat alerts for the same ticker
STATE_FILE     = Path("state.json")
# ─────────────────────────────────────────────────────────────────────────────


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_24h_change(symbol: str) -> tuple:
    """
    Returns (current_price, price_24h_ago, change_pct).
    Returns (None, None, None) on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d", interval="1h")

        if hist.empty or len(hist) < 2:
            return None, None, None

        current_price = float(hist["Close"].iloc[-1])
        now_ts = hist.index[-1]
        target_ts = now_ts - timedelta(hours=24)

        # Find the hourly bar closest to 24 hours ago
        diffs = abs(hist.index - target_ts)
        idx = int(diffs.argmin())
        price_24h_ago = float(hist["Close"].iloc[idx])

        if price_24h_ago == 0:
            return None, None, None

        change_pct = (current_price - price_24h_ago) / price_24h_ago * 100
        return current_price, price_24h_ago, change_pct

    except Exception as exc:
        print(f"  [WARN] Failed to fetch {symbol}: {exc}")
        return None, None, None


def should_alert(symbol: str, state: dict) -> bool:
    """Returns True if enough time has passed since the last alert for this ticker."""
    last_alert_iso = state.get(symbol)
    if not last_alert_iso:
        return True
    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last_alert_iso)
    return elapsed >= timedelta(hours=COOLDOWN_HOURS)


def build_html_email(alerts: list, all_results: list, now_str: str) -> str:
    alert_items = "".join(
        f"<li><b>{a['name']}</b>: {a['change']:+.2f}%"
        f" &nbsp;(当前价 {a['current']:.4f} / 24h前 {a['prev']:.4f})</li>"
        for a in alerts
    )

    table_rows = ""
    for r in all_results:
        if r["change"] is None:
            table_rows += (
                f"<tr><td>{r['name']}</td>"
                f"<td colspan='3' style='color:#9e9e9e;text-align:center'>数据获取失败</td></tr>"
            )
        else:
            color = "#c62828" if r["change"] > 0 else "#2e7d32"
            arrow = "▲" if r["change"] > 0 else "▼"
            table_rows += (
                f"<tr>"
                f"<td>{r['name']}</td>"
                f"<td>{r['current']:.4f}</td>"
                f"<td>{r['prev']:.4f}</td>"
                f"<td style='color:{color};font-weight:bold'>{arrow} {r['change']:+.2f}%</td>"
                f"</tr>"
            )

    return f"""
<html>
<body style="font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:20px">
  <h2 style="color:#b71c1c;border-bottom:2px solid #b71c1c;padding-bottom:8px">
    价格预警通知
  </h2>
  <p>以下标的 <b>24小时涨跌幅超过 {THRESHOLD_PCT}%</b>，触发预警：</p>
  <ul style="line-height:1.8">{alert_items}</ul>
  <hr style="margin:20px 0">
  <h3 style="margin-bottom:10px">完整行情</h3>
  <table border="1" cellpadding="9" cellspacing="0"
         style="border-collapse:collapse;width:100%;font-size:14px">
    <thead>
      <tr style="background:#f5f5f5;text-align:left">
        <th>标的</th><th>当前价格</th><th>24h前价格</th><th>24h涨跌幅</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>
  <p style="color:#9e9e9e;font-size:12px;margin-top:20px">
    监控时间: {now_str} &nbsp;|&nbsp;
    触发阈值: {THRESHOLD_PCT}% &nbsp;|&nbsp;
    重复提醒冷却: {COOLDOWN_HOURS}h
  </p>
</body>
</html>
"""


def send_email(subject: str, html_body: str):
    sender    = os.environ["GMAIL_ADDRESS"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)

    msg = MIMEMultipart("alternative")
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print(f"  邮件已发送至 {recipient}")


def main():
    now     = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n=== 价格监控运行 {now_str} ===")

    state       = load_state()
    all_results = []
    alerts      = []

    for name, symbol in WATCHLIST.items():
        print(f"  检查 {name} ({symbol}) ...", end=" ", flush=True)
        current, prev, change = get_24h_change(symbol)

        result = {
            "name": name, "symbol": symbol,
            "current": current, "prev": prev, "change": change,
        }
        all_results.append(result)

        if change is None:
            print("获取失败")
            continue

        print(f"当前={current:.4f}  24h前={prev:.4f}  变动={change:+.2f}%", end="")

        if abs(change) >= THRESHOLD_PCT:
            if should_alert(symbol, state):
                alerts.append(result)
                state[symbol] = now.isoformat()
                print("  ← 触发预警!")
            else:
                print("  (冷却期内，跳过)")
        else:
            print()

    save_state(state)

    if alerts:
        subject = (
            f"[价格预警] {len(alerts)} 个标的触发 {THRESHOLD_PCT}% 阈值"
            f" — {now_str}"
        )
        html = build_html_email(alerts, all_results, now_str)
        send_email(subject, html)
    else:
        print("  无新预警触发")

    print("=== 运行结束 ===\n")


if __name__ == "__main__":
    main()
