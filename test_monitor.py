#!/usr/bin/env python3
"""
本地测试脚本 — 验证 price_monitor.py 各项功能是否正常

运行方式：
    pip install yfinance          # 如尚未安装
    python test_monitor.py        # 基础测试（不发邮件）
    python test_monitor.py --email  # 追加发送真实测试邮件（需设置环境变量）

环境变量（--email 模式需要）：
    export GMAIL_ADDRESS="you@gmail.com"
    export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
    export RECIPIENT_EMAIL="you@gmail.com"   # 可选，默认与发件人相同
"""

import os
import sys
import webbrowser
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# ── 从主脚本导入被测函数 ─────────────────────────────────────────────────────
from price_monitor import (
    get_24h_change,
    should_alert,
    build_html_email,
    send_email,
    WATCHLIST,
    THRESHOLD_PCT,
    COOLDOWN_HOURS,
)

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    status = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"{status}  {label}{suffix}")
    if condition:
        passed += 1
    else:
        failed += 1


# ════════════════════════════════════════════════════════════════════════════
# TEST 1 — 价格数据获取（真实网络请求）
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("TEST 1  实时价格获取（yfinance）")
print("─" * 60)

live_results = []   # shared with TEST 4 for the email preview

for name, symbol in WATCHLIST.items():
    print(f"  正在请求 {name} ({symbol}) ...", end=" ", flush=True)
    current, prev, change, stale = get_24h_change(symbol)
    ok = current is not None and change is not None and current > 0
    if ok and stale:
        detail = f"当前={current:.4f}  休市（数据过旧，不触发预警）"
    elif ok:
        detail = f"当前={current:.4f}  24h前={prev:.4f}  变动={change:+.2f}%"
    else:
        detail = "返回 None，可能网络问题"
    check(name, ok, detail)
    live_results.append({
        "name": name, "symbol": symbol,
        "current": current, "prev": prev, "change": change, "stale": stale,
    })


# ════════════════════════════════════════════════════════════════════════════
# TEST 2 — 预警阈值逻辑（使用模拟数据，不依赖网络）
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("TEST 2  预警阈值逻辑")
print("─" * 60)

threshold_cases = [
    ("涨幅 3%  → 不触发", 3.0,  False),
    ("涨幅 5%  → 触发",   5.0,  True),
    ("涨幅 7%  → 触发",   7.0,  True),
    ("跌幅 3%  → 不触发", -3.0, False),
    ("跌幅 6%  → 触发",  -6.0,  True),
]

for label, change, expect_alert in threshold_cases:
    triggered = abs(change) >= THRESHOLD_PCT
    check(label, triggered == expect_alert,
          f"|{change}%| {'≥' if triggered else '<'} 阈值 {THRESHOLD_PCT}%")


# ════════════════════════════════════════════════════════════════════════════
# TEST 3 — 冷却期逻辑
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("TEST 3  重复预警冷却期逻辑")
print("─" * 60)

now = datetime.now(timezone.utc)

# 从未预警过
state_never = {}
check("首次预警（无历史）→ 应触发",
      should_alert("BTC-USD", state_never) is True)

# 1 小时前刚预警过（在 4h 冷却期内）
state_recent = {"BTC-USD": (now - timedelta(hours=1)).isoformat()}
check("距上次预警 1h（冷却期内）→ 不触发",
      should_alert("BTC-USD", state_recent) is False)

# 正好在冷却期边界
state_boundary = {"BTC-USD": (now - timedelta(hours=COOLDOWN_HOURS)).isoformat()}
check(f"距上次预警恰好 {COOLDOWN_HOURS}h（边界）→ 应触发",
      should_alert("BTC-USD", state_boundary) is True)

# 5 小时前（超出冷却期）
state_old = {"BTC-USD": (now - timedelta(hours=5)).isoformat()}
check("距上次预警 5h（超出冷却期）→ 应触发",
      should_alert("BTC-USD", state_old) is True)

# 不同标的之间互不影响
state_other = {"0700.HK": now.isoformat()}
check("冷却期仅对应各自标的，不影响其他标的",
      should_alert("BTC-USD", state_other) is True)


# ════════════════════════════════════════════════════════════════════════════
# TEST 4 — 邮件 HTML 内容生成 + 浏览器预览
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("TEST 4  邮件 HTML 生成与预览")
print("─" * 60)

# Use live data from TEST 1; treat anything >= threshold (and not stale) as an alert
live_alerts = [
    r for r in live_results
    if r["change"] is not None and not r["stale"] and abs(r["change"]) >= THRESHOLD_PCT
]

now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
html = build_html_email(live_alerts, live_results, now_str)

has_any_name  = any(r["name"] in html for r in live_results if r["current"] is not None)
has_table     = "<table" in html
has_threshold = str(THRESHOLD_PCT) in html

check("HTML 包含标的名称",  has_any_name)
check("HTML 包含价格表格",  has_table)
check("HTML 包含阈值配置",  has_threshold)

# 写入临时文件并在浏览器中打开
tmp = tempfile.NamedTemporaryFile(
    suffix=".html", delete=False, mode="w", encoding="utf-8"
)
tmp.write(html)
tmp.close()
print(f"{INFO}  邮件预览已保存至 {tmp.name}")
try:
    webbrowser.open(f"file://{tmp.name}")
    print(f"{INFO}  已在浏览器中打开预览")
except Exception:
    print(f"{INFO}  请手动打开: file://{tmp.name}")


# ════════════════════════════════════════════════════════════════════════════
# TEST 5 — SMTP 连接（Mock，不真正发送）
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 60)
print("TEST 5  SMTP 发送逻辑（Mock）")
print("─" * 60)

os.environ.setdefault("GMAIL_ADDRESS",      "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "mock-password")
os.environ.setdefault("RECIPIENT_EMAIL",    "test@gmail.com")

calls = {"smtp": False, "login": False, "send": False}

class MockSMTP:
    def __init__(self, *_): calls["smtp"] = True
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def login(self, *_):    calls["login"] = True
    def sendmail(self, *_): calls["send"] = True

with patch("price_monitor.smtplib.SMTP_SSL", MockSMTP):
    try:
        send_email("[测试] Price Monitor", html)
    except Exception as exc:
        print(f"  错误: {exc}")

check("SMTP_SSL 连接被调用",   calls["smtp"])
check("login() 被调用",        calls["login"])
check("sendmail() 被调用",     calls["send"])


# ════════════════════════════════════════════════════════════════════════════
# TEST 6 — 真实邮件发送（仅 --email 模式）
# ════════════════════════════════════════════════════════════════════════════
if "--email" in sys.argv:
    print("\n" + "─" * 60)
    print("TEST 6  真实邮件发送")
    print("─" * 60)

    required = ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"]
    missing  = [k for k in required if not os.environ.get(k) or "mock" in os.environ[k]]

    if missing:
        print(f"  跳过：请先设置环境变量: {', '.join(missing)}")
    else:
        sender = os.environ["GMAIL_ADDRESS"]
        print(f"  发件人: {sender}")
        try:
            send_email(
                subject="[Price Monitor] 本地测试邮件",
                html_body=build_html_email(live_alerts, live_results, now_str),
            )
            check("真实邮件发送成功", True, f"已发至 {os.environ.get('RECIPIENT_EMAIL', sender)}")
        except Exception as exc:
            check("真实邮件发送", False, str(exc))


# ════════════════════════════════════════════════════════════════════════════
# 测试汇总
# ════════════════════════════════════════════════════════════════════════════
total = passed + failed
print("\n" + "═" * 60)
print(f"  测试结果：{passed}/{total} 通过", end="")
if failed:
    print(f"  (\033[91m{failed} 失败\033[0m)")
else:
    print("  \033[92m全部通过\033[0m")
print("═" * 60 + "\n")

sys.exit(0 if failed == 0 else 1)
