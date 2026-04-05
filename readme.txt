================================================================================
QuantitativeTrading — 代码运行逻辑说明
================================================================================

一、项目做什么
--------------------------------------------------------------------------------
本仓库是一个可配置的量化交易框架：用历史数据做回测（yfinance），可选接入
Alpaca（美股）或模拟/富途（港股）做实盘或干跑（DRY_RUN）。策略信号统一为
0/1（空仓/持有），再经风控与仓位差决定是否下单。


二、目录与职责（简要）
--------------------------------------------------------------------------------
  app_gui.py              Web 界面（Streamlit）：参数、回测、单次实盘、定时实盘
  requirements.txt        Python 依赖
  .env / .env.example     环境变量配置（密钥勿提交，见 .gitignore）

  src/main.py             命令行入口：按 APP_MODE 分支
  src/config.py           从环境变量加载 AppConfig（冻结 dataclass）
  src/market/data.py      拉取 OHLCV；港股代码规范化（如 09988 -> 9988.HK）
  src/market/validation.py  市场与标的合法性（US 不用港股代码等）

  src/strategy/           各策略 generate_signal；selector 按 STRATEGY_NAME 分发
  src/engine/backtest.py  回测：信号 -> 移位持仓 -> 收益曲线与指标
  src/engine/live.py      实盘单次周期：开市检查、熔断、信号、下单/干跑、日志
  src/engine/scheduler.py live_loop：按间隔重复调用 live（带重试）

  src/broker/             券商抽象：Alpaca / Sim / Futu（占位）
  src/utils/notify.py     Webhook 告警


三、配置如何进入程序
--------------------------------------------------------------------------------
1) 启动时 config.load_dotenv() 读取项目根目录 .env（若存在）。
2) AppConfig.from_env() 把所有环境变量解析成 AppConfig 实例。
3) GUI 可把当前表单写入 .env；命令行直接读同一套变量。

关键变量（不全列举，详见 .env.example）：
  APP_MODE        backtest | live | live_loop
  MARKET          US | HK
  SYMBOLS         逗号分隔
  STRATEGY_NAME   ma_cross | rsi_reversion | bollinger_reversion | breakout | macd_cross
  DRY_RUN         true 时不真实下单（仅记录/模拟路径）


四、两条入口路径
--------------------------------------------------------------------------------
A) 命令行（适合服务器、定时任务）
   工作目录建议在项目根目录，且 PYTHONPATH 包含 src，或从项目根执行：
     python src/main.py
   （若 import 失败，可先：set PYTHONPATH=src  或  cd 到含 src 的路径按你环境调整）

B) 图形界面（本地或服务器 0.0.0.0）
     python -m streamlit run app_gui.py
   GUI 内部会 import src 下模块，逻辑与 CLI 共用 engine、strategy、config。


五、main.py 运行逻辑（核心分支）
--------------------------------------------------------------------------------
1. AppConfig.from_env()
2. invalid_symbols(symbols, market) — 不匹配则抛错退出
3. 按 APP_MODE：
   - backtest：对每个标的 fetch_ohlcv -> run_backtest(df, cfg, capital) -> 打印指标
   - live：run_live_with_retries(cfg) — 内部循环重试 + 可选 webhook
   - live_loop：run_live_scheduler(cfg) — 按 LIVE_INTERVAL_MINUTES 睡眠后重复 live


六、回测引擎（backtest）在算什么
--------------------------------------------------------------------------------
1. 取 close（港股可能需压成一维 Series）。
2. generate_signal_for_config(close, cfg) 得到逐日信号 0/1。
3. position = signal.shift(1) — 用“上一日信号”决定当日持仓，避免前视偏差。
4. 用收盘价涨跌幅与 position 相乘得到策略收益，再累乘成资金曲线。
5. 输出总收益、最大回撤、信号翻转次数（trades）。


七、实盘单次周期（live）在做什么
--------------------------------------------------------------------------------
1. build_broker(cfg)：US 用 Alpaca（干跑且无 key 时可用 Sim）；HK 用 HK_BROKER
   sim 或 futu（futu 需自行接好接口）。
2. 可选：开市检查（US 用 Alpaca clock；HK 用本地时段规则）。
3. 日内亏损熔断：读账户净值，与当日基准比较，触发后只允许平仓。
4. 对每个标的：拉近一年数据 -> 信号 -> 结合止损止盈与熔断得到目标仓位
   -> 与当前持仓算 delta -> 名义金额/购买力等风控 -> DRY_RUN 则只记日志
   否则 submit_market_order。
5. 日志写入 logs/live_trades.csv（路径相对运行当前工作目录）。


八、策略如何切换
--------------------------------------------------------------------------------
strategy/selector.py 中根据 cfg.strategy_name 调用对应模块的 generate_signal。
各策略参数来自 cfg（RSI 窗口、布林参数、MACD 参数等），与 GUI/.env 一致。


九、典型使用顺序（建议）
--------------------------------------------------------------------------------
1. copy .env.example .env，填 MARKET、SYMBOLS、策略与风控；敏感键勿泄露。
2. pip install -r requirements.txt
3. 先 backtest 或 GUI 回测；再 DRY_RUN=true 试 live；最后关闭 DRY_RUN 用模拟盘。
4. 服务器长期跑 live_loop 时，建议用 systemd 托管 python -m streamlit 或
   python src/main.py，并配合 nginx 反代与防火墙。


十、与 README.md 的关系
--------------------------------------------------------------------------------
README.md 侧重安装与功能列表；本 readme.txt 侧重「从配置到引擎」的执行顺序
与模块分工。二者可对照阅读。

================================================================================
（文档随代码迭代可继续补充：如 futu 实盘接入、数据库落库等。）
================================================================================
