# Price Watch

自动监控股票和加密货币价格，当 24 小时涨跌幅超过阈值时发送邮件预警。通过 GitHub Actions 每 10 分钟自动执行一次，无需服务器。

## 监控标的

| 市场 | 标的 | Ticker |
|------|------|--------|
| A 股 | 中证 500 指数 | 000905.SS |
| 港股 | 腾讯 | 0700.HK |
| 港股 | 美团 | 3690.HK |
| 港股 | 哔哩哔哩 | 9626.HK |
| 港股 | 恒生科技 ETF | 3032.HK |
| 美股 | 腾讯 ADR | TCEHY |
| 美股 | 特斯拉 | TSLA |
| 美股 | AMD | AMD |
| 美股 | 台积电 | TSM |
| 美股 | 纳斯达克 ETF | QQQ |
| 加密 | 比特币 | BTC-USD |

## 功能特性

- **24 小时涨跌幅监控**：以当前最新价格与 24 小时前价格对比计算涨跌幅
- **邮件预警**：触发阈值时发送 HTML 格式邮件，包含预警摘要和完整行情表格
- **休市检测**：股票数据超过 20 小时未更新时自动识别为休市，不触发误报
- **重复提醒冷却**：同一标的触发预警后，4 小时内不再重复发送
- **GitHub Actions 定时运行**：每 10 分钟自动执行，免服务器

## 文件结构

```
price_watch/
├── price_monitor.py          # 主程序
├── test_monitor.py           # 本地测试脚本
├── requirements.txt          # Python 依赖
└── .github/
    └── workflows/
        └── price_monitor.yml # GitHub Actions 工作流
```

## 快速开始

### 第一步：获取 Gmail 应用专用密码

Gmail 不允许直接使用账户密码发送邮件，需要生成应用专用密码：

1. 前往 [Google 账户安全设置](https://myaccount.google.com/security)
2. 确保已开启**两步验证**
3. 搜索「应用专用密码」并进入
4. 选择应用「邮件」，点击生成
5. 保存生成的 16 位密码（格式：`xxxx xxxx xxxx xxxx`）

### 第二步：配置 GitHub Secrets

在仓库页面进入 **Settings → Secrets and variables → Actions**，添加以下三个 Secret：

| Secret 名称 | 说明 |
|-------------|------|
| `GMAIL_ADDRESS` | 发件人 Gmail 地址，如 `you@gmail.com` |
| `GMAIL_APP_PASSWORD` | 上一步生成的应用专用密码 |
| `RECIPIENT_EMAIL` | 收件人邮箱（可与发件人相同） |

### 第三步：启用 GitHub Actions

将代码推送到 GitHub 后，进入仓库的 **Actions** 页面，确认 `Price Monitor` 工作流已启用。工作流会在每 10 分钟自动触发，也可以点击 **Run workflow** 手动执行。

## 本地测试

在本地运行测试脚本，验证价格获取、预警逻辑和邮件生成是否正常：

```bash
# 安装依赖
pip install yfinance

# 运行基础测试（不发送真实邮件）
python3 test_monitor.py

# 运行完整测试（包含真实邮件发送）
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export RECIPIENT_EMAIL="you@gmail.com"
python3 test_monitor.py --email
```

测试脚本涵盖以下内容：

| 测试项 | 说明 |
|--------|------|
| TEST 1 | 实时价格获取，验证所有标的可正常拉取数据 |
| TEST 2 | 预警阈值逻辑，覆盖边界值 |
| TEST 3 | 冷却期逻辑，验证重复提醒抑制 |
| TEST 4 | HTML 邮件生成，并在浏览器中预览 |
| TEST 5 | SMTP 发送流程（Mock，不真实发送） |

## 配置说明

所有可调参数位于 `price_monitor.py` 顶部：

```python
THRESHOLD_PCT     = 5.0   # 触发预警的涨跌幅阈值（%）
COOLDOWN_HOURS    = 4     # 同一标的重复预警的最小间隔（小时）
MARKET_STALE_HOURS = 20   # 数据超过此时长视为休市，不触发预警（小时）
```

如需添加或删除监控标的，修改 `WATCHLIST` 字典即可，ticker 格式遵循 [Yahoo Finance](https://finance.yahoo.com) 标准：

```python
WATCHLIST = {
    "标的名称": "TICKER",
    ...
}
```

## 依赖

| 包 | 用途 |
|----|------|
| [yfinance](https://github.com/ranaroussi/yfinance) | 免费行情数据（A 股、港股、美股、加密货币） |

标准库（无需额外安装）：`smtplib`、`json`、`os`、`datetime`
