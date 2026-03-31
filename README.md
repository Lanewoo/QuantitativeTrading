   # QuantitativeTrading

一个可扩展的量化交易框架（Python），主要面向：
- 美股（默认，支持 Alpaca 实盘/模拟盘接口）
- 港股（支持 `sim` 模拟券商，`futu` 可选接入）

当前提供：
- 配置驱动（环境变量）
- 5种可选策略（均线/RSI/布林/突破/MACD）
- 历史数据回测（Yahoo Finance）
- 实盘执行模块骨架（可继续扩展为完整交易系统）

## 1. 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## GUI 界面

启动图形界面（Web GUI）：

```bash
streamlit run app_gui.py
```

GUI 支持：
- 参数配置并一键保存到 `.env`
- 一键执行回测（展示收益/回撤/交易次数与净值曲线）
- 回测结果一键导出 CSV
- 回测买卖点标注图（BUY/SELL）
- 一键执行实盘单次周期（建议先 `DRY_RUN=true`）
- 一键启动/停止定时实盘（live_loop）
- 查看 `logs/live_trades.csv` 最近日志

## 2. 配置

复制配置模板：

```bash
copy .env.example .env
```

关键字段：
- `APP_MODE=backtest` / `live` / `live_loop`
- `MARKET=US` 或 `HK`
- `SYMBOLS=AAPL,MSFT`（港股可写 `0700` / `0700.HK`）
- `DRY_RUN=true` 可开启模拟下单（仅记录计划交易，不真实发单）
- `HK_BROKER=sim` 或 `futu`
- `STRATEGY_NAME=ma_cross`（可选：`ma_cross` / `rsi_reversion` / `bollinger_reversion` / `breakout` / `macd_cross`）

市场-标的校验规则：
- `US` 只允许美股代码（如 `AAPL`），不允许纯数字或 `.HK`
- `HK` 只允许港股数字代码（如 `0700` / `9988` / `0700.HK`）

## 3. 运行回测

```bash
python src/main.py
```

示例输出：
- `[BACKTEST] AAPL return=xx.xx% max_dd=-xx.xx% trades=xx`

## 4. 实盘（可选）

### 美股（Alpaca）
1. 填入 `.env` 的 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`
2. 设置 `APP_MODE=live`
3. 可设置风控参数：
   - `LIVE_QTY_PER_TRADE`：每个标的目标持仓股数
   - `MAX_NOTIONAL_PER_TRADE`：单次调仓最大名义金额
   - `ALLOW_SHORT`：是否允许做空（默认 false）
4. 运行：

```bash
python src/main.py
```

如需先验证行为不下真实单，可设置：

```bash
DRY_RUN=true
```

实盘周期会：
- 拉取近 1 年日线，按双均线生成目标仓位（1=持有，0=空仓）
- 读取当前 Alpaca 持仓并自动补齐仓位差
- 支持持仓级止损/止盈（按持仓均价与最新价计算）
- 超过风控阈值时阻止下单
- 买入前检查账户购买力（Buying Power）
- 支持日内最大亏损熔断（触发后仅允许清仓）
- 写入日志到 `logs/live_trades.csv`
- 默认仅在交易时段运行（美股通过 Alpaca 市场时钟判断，覆盖节假日）
- 失败自动重试，并支持 webhook 告警

可选增强参数：
- `ENABLE_MARKET_HOURS_CHECK=true`：仅在交易时段执行
- `LIVE_MAX_RETRIES=3`：单次执行失败重试次数
- `ALERT_WEBHOOK_URL=`：告警 webhook（如企业微信/飞书/Slack 机器人）
- `MIN_BUYING_POWER_BUFFER=100`：购买力安全缓冲（美元）
- `STOP_LOSS_PCT=0.03`：单标的止损阈值（3%）
- `TAKE_PROFIT_PCT=0.08`：单标的止盈阈值（8%）
- `MAX_DAILY_LOSS_PCT=0.02`：日内亏损熔断阈值（2%）
- `DRY_RUN=false`：是否仅模拟下单（true 时只记录日志，不提交订单）

### 自动定时执行（推荐）

设置：

```bash
APP_MODE=live_loop
LIVE_INTERVAL_MINUTES=15
```

启动后程序会持续每隔指定分钟运行一次实盘周期。

### 港股
- 默认 `HK_BROKER=sim`：可直接运行港股实盘流程（本地模拟券商，便于测试）
- 如需接入富途，设置 `HK_BROKER=futu`，并在 `broker/futu_broker.py` 中接入 futu-api 与 OpenD。

## 5. 下一步建议

- 增加风控（单笔风险、最大回撤熔断、交易时段检查）
- 增加交易成本模型（手续费、滑点）
- 增加多策略与组合管理
- 接入数据库记录订单、成交、净值与日志
- 用任务调度器（Windows 任务计划或 cron）定时执行 live 周期
