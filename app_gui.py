from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import os
import subprocess
import sys
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import AppConfig  # noqa: E402
from engine.backtest import run_backtest  # noqa: E402
from engine.live import run_live_with_retries  # noqa: E402
from market.data import fetch_ohlcv  # noqa: E402
from market.validation import invalid_symbols  # noqa: E402
from strategy.selector import generate_signal_for_config  # noqa: E402


LOOP_PID_FILE = ROOT / "logs" / "live_loop.pid"


def _to_1d_series(values: pd.Series | pd.DataFrame) -> pd.Series:
    """Normalize possibly 2D yfinance columns to a 1D series."""
    if isinstance(values, pd.DataFrame):
        return values.iloc[:, 0]
    return values


def _parse_date_safe(value: str, fallback: str) -> date:
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return pd.to_datetime(fallback).date()


def _save_env(cfg: AppConfig) -> None:
    """Persist current GUI form values into .env for CLI/next launch reuse."""
    pairs = asdict(cfg)
    lines: list[str] = []
    for key, value in pairs.items():
        env_key = key.upper()
        if isinstance(value, bool):
            env_value = "true" if value else "false"
        elif isinstance(value, list):
            env_value = ",".join(str(v) for v in value)
        else:
            env_value = str(value)
        lines.append(f"{env_key}={env_value}")
    (ROOT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_alpaca_credentials(api_key: str, secret_key: str) -> None:
    """Save only Alpaca credentials into .env while keeping other keys."""
    env_path = ROOT / ".env"
    existing = dotenv_values(env_path)
    existing["ALPACA_API_KEY"] = api_key
    existing["ALPACA_SECRET_KEY"] = secret_key
    lines: list[str] = []
    for key, value in existing.items():
        if key is None:
            continue
        lines.append(f"{key}={'' if value is None else value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_cfg() -> AppConfig:
    """Build AppConfig from sidebar widgets, using env values as defaults."""
    base = AppConfig.from_env()
    env_file = dotenv_values(ROOT / ".env")
    st.sidebar.header("参数配置")

    app_mode = st.sidebar.selectbox("运行模式", ["backtest", "live"], index=0)
    market = st.sidebar.selectbox("市场", ["US", "HK"], index=0 if base.market == "US" else 1)

    # Keep separate symbol lists for US/HK and switch automatically by market.
    us_default = str(env_file.get("SYMBOLS_US") or ("AAPL,MSFT" if base.market != "US" else ",".join(base.symbols)))
    hk_default = str(env_file.get("SYMBOLS_HK") or ("0700,9988" if base.market != "HK" else ",".join(base.symbols)))
    if "symbols_us_raw" not in st.session_state:
        st.session_state["symbols_us_raw"] = us_default
    if "symbols_hk_raw" not in st.session_state:
        st.session_state["symbols_hk_raw"] = hk_default

    if "symbols_market_prev" not in st.session_state:
        st.session_state["symbols_market_prev"] = market
    if "symbols_raw" not in st.session_state:
        st.session_state["symbols_raw"] = (
            st.session_state["symbols_us_raw"] if market == "US" else st.session_state["symbols_hk_raw"]
        )

    if market != st.session_state["symbols_market_prev"]:
        st.session_state["symbols_raw"] = (
            st.session_state["symbols_us_raw"] if market == "US" else st.session_state["symbols_hk_raw"]
        )
        st.session_state["symbols_market_prev"] = market

    symbols_raw = st.sidebar.text_input("交易标的(逗号分隔)", key="symbols_raw")
    if market == "US":
        st.session_state["symbols_us_raw"] = symbols_raw
    else:
        st.session_state["symbols_hk_raw"] = symbols_raw

    last_saved_symbols = st.session_state.get("_last_saved_symbols", "")
    if symbols_raw != last_saved_symbols:
        env_path = ROOT / ".env"
        existing = dotenv_values(env_path)
        existing["SYMBOLS"] = symbols_raw
        existing["SYMBOLS_US"] = st.session_state["symbols_us_raw"]
        existing["SYMBOLS_HK"] = st.session_state["symbols_hk_raw"]
        lines: list[str] = []
        for key, value in existing.items():
            if key is None:
                continue
            lines.append(f"{key}={'' if value is None else value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        st.session_state["_last_saved_symbols"] = symbols_raw
        st.sidebar.caption("交易标的已按市场自动保存到 .env")
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

    fast_window = st.sidebar.number_input("快线窗口", min_value=2, value=base.fast_window)
    slow_window = st.sidebar.number_input("慢线窗口", min_value=3, value=base.slow_window)
    strategy_name = st.sidebar.selectbox(
        "策略",
        ["ma_cross", "rsi_reversion", "bollinger_reversion", "breakout", "macd_cross"],
        index=["ma_cross", "rsi_reversion", "bollinger_reversion", "breakout", "macd_cross"].index(base.strategy_name)
        if base.strategy_name in {"ma_cross", "rsi_reversion", "bollinger_reversion", "breakout", "macd_cross"}
        else 0,
    )
    rsi_window = st.sidebar.number_input("RSI窗口", min_value=2, value=base.rsi_window)
    rsi_oversold = st.sidebar.number_input("RSI超卖", min_value=1.0, max_value=99.0, value=float(base.rsi_oversold))
    rsi_overbought = st.sidebar.number_input("RSI超买", min_value=1.0, max_value=99.0, value=float(base.rsi_overbought))
    bb_window = st.sidebar.number_input("布林窗口", min_value=2, value=base.bb_window)
    bb_std = st.sidebar.number_input("布林标准差倍数", min_value=0.1, value=float(base.bb_std))
    breakout_window = st.sidebar.number_input("突破窗口", min_value=2, value=base.breakout_window)
    macd_fast = st.sidebar.number_input("MACD快线", min_value=2, value=base.macd_fast)
    macd_slow = st.sidebar.number_input("MACD慢线", min_value=3, value=base.macd_slow)
    macd_signal = st.sidebar.number_input("MACD信号线", min_value=2, value=base.macd_signal)
    initial_capital = st.sidebar.number_input("初始资金", min_value=1000.0, value=float(base.initial_capital))
    start_date_obj = st.sidebar.date_input("回测开始日期", value=_parse_date_safe(base.start_date, "2022-01-01"))
    end_date_obj = st.sidebar.date_input("回测结束日期", value=_parse_date_safe(base.end_date, "2024-12-31"))
    start_date = start_date_obj.strftime("%Y-%m-%d")
    end_date = end_date_obj.strftime("%Y-%m-%d")

    # Read saved credentials from .env first, then fallback to process env values.
    saved_api = str(env_file.get("ALPACA_API_KEY") or base.alpaca_api_key)
    saved_secret = str(env_file.get("ALPACA_SECRET_KEY") or base.alpaca_secret_key)

    # Keep credentials in session state so Streamlit reruns do not clear them.
    if "alpaca_api_key" not in st.session_state:
        st.session_state["alpaca_api_key"] = saved_api
    if "alpaca_secret_key" not in st.session_state:
        st.session_state["alpaca_secret_key"] = saved_secret

    alpaca_api_key = st.sidebar.text_input("Alpaca API Key", key="alpaca_api_key")
    alpaca_secret_key = st.sidebar.text_input("Alpaca Secret", key="alpaca_secret_key", type="password")
    # Auto-save credentials on change so users don't lose keys by forgetting buttons.
    last_saved_api = st.session_state.get("_last_saved_api", "")
    last_saved_secret = st.session_state.get("_last_saved_secret", "")
    if alpaca_api_key != last_saved_api or alpaca_secret_key != last_saved_secret:
        _save_alpaca_credentials(alpaca_api_key, alpaca_secret_key)
        st.session_state["_last_saved_api"] = alpaca_api_key
        st.session_state["_last_saved_secret"] = alpaca_secret_key
        st.sidebar.caption("Alpaca API Key/Secret 已自动保存到 .env")
    alpaca_paper = st.sidebar.checkbox("Alpaca 模拟盘", value=base.alpaca_paper)
    hk_broker = st.sidebar.selectbox("港股券商", ["sim", "futu"], index=0 if base.hk_broker == "sim" else 1)

    live_qty_per_trade = st.sidebar.number_input("单标的目标持仓股数", min_value=1, value=base.live_qty_per_trade)
    max_notional_per_trade = st.sidebar.number_input(
        "单次最大名义金额", min_value=100.0, value=float(base.max_notional_per_trade)
    )
    allow_short = st.sidebar.checkbox("允许做空", value=base.allow_short)
    enable_market_hours_check = st.sidebar.checkbox("检查交易时段", value=base.enable_market_hours_check)
    live_max_retries = st.sidebar.number_input("实盘重试次数", min_value=1, value=base.live_max_retries)
    min_buying_power_buffer = st.sidebar.number_input(
        "购买力缓冲", min_value=0.0, value=float(base.min_buying_power_buffer)
    )
    stop_loss_pct = st.sidebar.number_input("止损比例", min_value=0.0, max_value=1.0, value=float(base.stop_loss_pct))
    take_profit_pct = st.sidebar.number_input(
        "止盈比例", min_value=0.0, max_value=2.0, value=float(base.take_profit_pct)
    )
    max_daily_loss_pct = st.sidebar.number_input(
        "日内最大亏损比例", min_value=0.0, max_value=1.0, value=float(base.max_daily_loss_pct)
    )
    dry_run = st.sidebar.checkbox("DRY_RUN (不真实下单)", value=True)

    cfg = AppConfig(
        app_mode=app_mode,
        market=market,
        symbols=symbols,
        fast_window=int(fast_window),
        slow_window=int(slow_window),
        strategy_name=strategy_name,
        rsi_window=int(rsi_window),
        rsi_oversold=float(rsi_oversold),
        rsi_overbought=float(rsi_overbought),
        bb_window=int(bb_window),
        bb_std=float(bb_std),
        breakout_window=int(breakout_window),
        macd_fast=int(macd_fast),
        macd_slow=int(macd_slow),
        macd_signal=int(macd_signal),
        initial_capital=float(initial_capital),
        start_date=start_date,
        end_date=end_date,
        alpaca_api_key=alpaca_api_key,
        alpaca_secret_key=alpaca_secret_key,
        alpaca_paper=alpaca_paper,
        futu_host=base.futu_host,
        futu_port=base.futu_port,
        hk_broker=hk_broker,
        live_qty_per_trade=int(live_qty_per_trade),
        max_notional_per_trade=float(max_notional_per_trade),
        allow_short=allow_short,
        enable_market_hours_check=enable_market_hours_check,
        live_interval_minutes=base.live_interval_minutes,
        live_max_retries=int(live_max_retries),
        alert_webhook_url=base.alert_webhook_url,
        min_buying_power_buffer=float(min_buying_power_buffer),
        stop_loss_pct=float(stop_loss_pct),
        take_profit_pct=float(take_profit_pct),
        max_daily_loss_pct=float(max_daily_loss_pct),
        dry_run=dry_run,
    )
    return cfg


def _is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_live_loop_pid() -> int:
    """Return running live-loop PID, or 0 when not running."""
    if not LOOP_PID_FILE.exists():
        return 0
    try:
        pid = int(LOOP_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 0
    return pid if _is_pid_running(pid) else 0


def _start_live_loop(cfg: AppConfig) -> int:
    """Start detached live_loop process and store PID."""
    LOOP_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "APP_MODE": "live_loop",
            "MARKET": cfg.market,
            "SYMBOLS": ",".join(cfg.symbols),
            "FAST_WINDOW": str(cfg.fast_window),
            "SLOW_WINDOW": str(cfg.slow_window),
            "STRATEGY_NAME": cfg.strategy_name,
            "RSI_WINDOW": str(cfg.rsi_window),
            "RSI_OVERSOLD": str(cfg.rsi_oversold),
            "RSI_OVERBOUGHT": str(cfg.rsi_overbought),
            "BB_WINDOW": str(cfg.bb_window),
            "BB_STD": str(cfg.bb_std),
            "BREAKOUT_WINDOW": str(cfg.breakout_window),
            "MACD_FAST": str(cfg.macd_fast),
            "MACD_SLOW": str(cfg.macd_slow),
            "MACD_SIGNAL": str(cfg.macd_signal),
            "INITIAL_CAPITAL": str(cfg.initial_capital),
            "START_DATE": cfg.start_date,
            "END_DATE": cfg.end_date,
            "ALPACA_API_KEY": cfg.alpaca_api_key,
            "ALPACA_SECRET_KEY": cfg.alpaca_secret_key,
            "ALPACA_PAPER": "true" if cfg.alpaca_paper else "false",
            "HK_BROKER": cfg.hk_broker,
            "LIVE_QTY_PER_TRADE": str(cfg.live_qty_per_trade),
            "MAX_NOTIONAL_PER_TRADE": str(cfg.max_notional_per_trade),
            "ALLOW_SHORT": "true" if cfg.allow_short else "false",
            "ENABLE_MARKET_HOURS_CHECK": "true" if cfg.enable_market_hours_check else "false",
            "LIVE_INTERVAL_MINUTES": str(cfg.live_interval_minutes),
            "LIVE_MAX_RETRIES": str(cfg.live_max_retries),
            "ALERT_WEBHOOK_URL": cfg.alert_webhook_url,
            "MIN_BUYING_POWER_BUFFER": str(cfg.min_buying_power_buffer),
            "STOP_LOSS_PCT": str(cfg.stop_loss_pct),
            "TAKE_PROFIT_PCT": str(cfg.take_profit_pct),
            "MAX_DAILY_LOSS_PCT": str(cfg.max_daily_loss_pct),
            "DRY_RUN": "true" if cfg.dry_run else "false",
        }
    )
    kwargs = {
        "cwd": str(ROOT),
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        proc = subprocess.Popen([sys.executable, "src/main.py"], creationflags=creationflags, **kwargs)
    else:
        proc = subprocess.Popen([sys.executable, "src/main.py"], start_new_session=True, **kwargs)
    LOOP_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def _stop_live_loop(pid: int) -> None:
    """Stop detached live_loop process by PID and cleanup marker file."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        os.kill(pid, 15)
    if LOOP_PID_FILE.exists():
        LOOP_PID_FILE.unlink()


def _render_backtest(cfg: AppConfig) -> dict[str, pd.DataFrame]:
    """Render backtest metrics/charts and return exportable per-symbol data."""
    st.subheader("回测结果")
    exports: dict[str, pd.DataFrame] = {}
    for symbol in cfg.symbols:
        df = fetch_ohlcv(symbol, cfg.market, cfg.start_date, cfg.end_date)
        close = _to_1d_series(df["close"])
        signal = generate_signal_for_config(close, cfg)
        # Use shifted signal to avoid look-ahead bias in equity simulation.
        position = signal.shift(1).fillna(0)
        ret = close.pct_change().fillna(0)
        equity = (1 + position * ret).cumprod() * cfg.initial_capital
        result = run_backtest(
            df=df,
            cfg=cfg,
            initial_capital=cfg.initial_capital,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{symbol} 总收益", f"{result['total_return']:.2%}")
        c2.metric(f"{symbol} 最大回撤", f"{result['max_drawdown']:.2%}")
        c3.metric(f"{symbol} 交易次数", str(result["trades"]))
        curve = pd.DataFrame({"date": equity.index, "equity": equity.values})
        curve["date_label"] = pd.to_datetime(curve["date"]).dt.strftime("%Y-%m-%d")
        line = alt.Chart(curve).mark_line().encode(
            x=alt.X("date:T", title="日期"),
            y=alt.Y("equity:Q", title="资金"),
            tooltip=["date_label:N", "equity:Q"],
        )
        st.altair_chart(line, use_container_width=True)

        buy_points = df[(signal.diff() == 1)].copy()
        sell_points = df[(signal.diff() == -1)].copy()
        marker_df = pd.concat(
            [
                pd.DataFrame({"date": buy_points.index, "price": _to_1d_series(buy_points["close"]).values, "type": "BUY"}),
                pd.DataFrame({"date": sell_points.index, "price": _to_1d_series(sell_points["close"]).values, "type": "SELL"}),
            ],
            ignore_index=True,
        )
        if not marker_df.empty:
            marker_df["date_label"] = pd.to_datetime(marker_df["date"]).dt.strftime("%Y-%m-%d")
        if not marker_df.empty:
            marker = (
                alt.Chart(marker_df)
                .mark_circle(size=60)
                .encode(
                    x="date:T",
                    y=alt.Y("price:Q", title="价格"),
                    color=alt.Color("type:N", scale=alt.Scale(domain=["BUY", "SELL"], range=["green", "red"])),
                    tooltip=["date_label:N", "price:Q", "type:N"],
                )
            )
            st.caption(f"{symbol} 买卖点（收盘价）")
            st.altair_chart(marker, use_container_width=True)

        exports[symbol] = pd.DataFrame(
            {
                "date": pd.to_datetime(df.index).strftime("%Y-%m-%d"),
                "close": close.values,
                "signal": signal.values,
                "position": position.values,
                "equity": equity.values,
            }
        )
    return exports


def _render_logs() -> None:
    """Show recent trade log records for quick operational checks."""
    st.subheader("交易日志")
    log_path = ROOT / "logs" / "live_trades.csv"
    if not log_path.exists():
        st.info("暂无日志。")
        return
    df = pd.read_csv(log_path)
    st.dataframe(df.tail(200), use_container_width=True)


def _render_current_strategy(cfg: AppConfig) -> None:
    """Show current strategy snapshot for each symbol."""
    st.subheader("当前策略")
    strategy_desc = {
        "ma_cross": f"双均线趋势 | FAST={cfg.fast_window}, SLOW={cfg.slow_window}",
        "rsi_reversion": f"RSI均值回归 | WINDOW={cfg.rsi_window}, OS={cfg.rsi_oversold}, OB={cfg.rsi_overbought}",
        "bollinger_reversion": f"布林带均值回归 | WINDOW={cfg.bb_window}, STD={cfg.bb_std}",
        "breakout": f"区间突破 | WINDOW={cfg.breakout_window}",
        "macd_cross": f"MACD金叉死叉 | FAST={cfg.macd_fast}, SLOW={cfg.macd_slow}, SIGNAL={cfg.macd_signal}",
    }.get(cfg.strategy_name, cfg.strategy_name)
    st.markdown(f"**策略名称**: `{cfg.strategy_name}`  \n**当前参数**: {strategy_desc}")
    with st.expander("查看策略详细说明", expanded=True):
        st.markdown(
            """
- **核心思想**: 用快线均线与慢线均线的相对位置判断趋势方向。  
- **可选策略**: `ma_cross` / `rsi_reversion` / `bollinger_reversion` / `breakout` / `macd_cross`  
- **信号规则**: 所有策略输出统一的 0/1 信号（1=BUY 持有，0=SELL 空仓）。  
- **计算方式**: 根据信号由 `generate_signal_for_config()` 自动切换对应策略。  
- **执行方式**: 实盘会根据目标仓位与当前仓位差值下单；回测用 `signal.shift(1)` 避免前视偏差。  
- **风控联动**: 下单前会经过名义金额限制、购买力检查、止损止盈、日亏损熔断等规则。  
- **结果解读**:  
  - `BUY` 表示当前策略倾向持有该标的；  
  - `SELL` 表示当前策略倾向空仓观望。  
"""
        )
    rows: list[dict] = []
    for symbol in cfg.symbols:
        try:
            df = fetch_ohlcv(symbol, cfg.market, cfg.start_date, cfg.end_date)
            close = _to_1d_series(df["close"])
            signal = generate_signal_for_config(close, cfg)
            if signal.empty:
                rows.append(
                    {
                        "symbol": symbol,
                        "signal": "N/A",
                        "latest_price": None,
                        "signal_time": None,
                        "note": "no signal",
                    }
                )
                continue
            latest_signal = int(signal.iloc[-1])
            rows.append(
                {
                    "symbol": symbol,
                    "signal": "BUY" if latest_signal == 1 else "SELL",
                    "latest_price": float(close.iloc[-1]),
                    "signal_time": pd.to_datetime(signal.index[-1]).strftime("%Y-%m-%d"),
                    "note": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "signal": "ERROR",
                    "latest_price": None,
                    "signal_time": None,
                    "note": str(exc),
                }
            )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def main() -> None:
    """Streamlit entrypoint: configuration, execution controls, and result views."""
    st.set_page_config(page_title="QuantitativeTrading GUI", layout="wide")
    st.title("QuantitativeTrading 操作界面")
    st.caption("默认建议先用 DRY_RUN=true 验证策略行为。")

    cfg = _build_cfg()
    bad_symbols = invalid_symbols(cfg.symbols, cfg.market)
    if bad_symbols:
        st.error(
            f"市场与交易标的不匹配: market={cfg.market}, invalid={bad_symbols}. "
            "US 需美股代码（如 AAPL）；HK 需数字代码（如 0700/9988 或 .HK）。"
        )
    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 2])
    with col1:
        if st.button("保存配置到 .env", use_container_width=True):
            _save_env(cfg)
            st.success("已保存 .env（包含 API Key / Secret）")
    with col2:
        if st.button("仅保存API密钥", use_container_width=True):
            _save_alpaca_credentials(cfg.alpaca_api_key, cfg.alpaca_secret_key)
            st.success("已保存 Alpaca API Key / Secret 到 .env")
    with col3:
        run_text = "执行回测" if cfg.app_mode == "backtest" else "执行实盘一次"
        run_now = st.button(run_text, type="primary", use_container_width=True)
    with col4:
        loop_pid = _get_live_loop_pid()
        if loop_pid:
            if st.button("停止定时实盘", use_container_width=True):
                _stop_live_loop(loop_pid)
                st.success("已停止定时实盘。")
        else:
            if st.button("启动定时实盘", use_container_width=True):
                pid = _start_live_loop(cfg)
                st.success(f"定时实盘已启动，PID={pid}")
    with col5:
        status = "运行中" if _get_live_loop_pid() else "未运行"
        st.write(f"当前模式: `{cfg.app_mode}` | 市场: `{cfg.market}` | DRY_RUN: `{cfg.dry_run}` | 定时实盘: `{status}`")

    if run_now and not bad_symbols:
        try:
            if cfg.app_mode == "backtest":
                exports = _render_backtest(cfg)
                for symbol, df in exports.items():
                    st.download_button(
                        label=f"下载 {symbol} 回测CSV",
                        data=df.to_csv(index=False).encode("utf-8"),
                        file_name=f"backtest_{symbol}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
            else:
                run_live_with_retries(cfg)
                st.success("实盘周期执行完成。")
        except Exception as exc:
            st.error(f"执行失败: {exc}")

    st.divider()
    _render_current_strategy(cfg)
    st.divider()
    _render_logs()


if __name__ == "__main__":
    main()
