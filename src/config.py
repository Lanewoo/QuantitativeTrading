"""
从环境变量（.env / 系统环境）加载运行配置，供 CLI、GUI、实盘调度共用。
对应键名见 .env.example，大写与 AppConfig 字段名一致（下划线转下划线）。
"""

from dataclasses import dataclass
import os
from dotenv import load_dotenv


# 启动时加载项目根目录 .env（若存在）
load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    """解析布尔型环境变量：1/true/yes/y/on 为 True。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    """集中式运行时配置，不可变；由 from_env() 从环境变量构造。"""

    # --- 运行模式与市场 ---
    app_mode: str  # APP_MODE: backtest | live | live_loop
    market: str  # MARKET: US | HK
    symbols: list[str]  # SYMBOLS: 逗号分隔标的

    # --- 策略参数（均线 / RSI / 布林 / 突破 / MACD，按 STRATEGY_NAME 选用）---
    fast_window: int
    slow_window: int
    strategy_name: str  # STRATEGY_NAME: ma_cross | rsi_reversion | ...
    rsi_window: int
    rsi_oversold: float
    rsi_overbought: float
    bb_window: int
    bb_std: float
    breakout_window: int
    macd_fast: int
    macd_slow: int
    macd_signal: int

    # --- 回测 ---
    initial_capital: float
    start_date: str
    end_date: str

    # --- 券商：美股 Alpaca / 港股 Futu 或 sim ---
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool
    futu_host: str
    futu_port: int
    hk_broker: str  # HK_BROKER: sim | futu

    # --- 实盘：仓位、风控、调度 ---
    live_qty_per_trade: int
    max_notional_per_trade: float
    allow_short: bool
    enable_market_hours_check: bool
    live_interval_minutes: int
    live_max_retries: int
    alert_webhook_url: str
    min_buying_power_buffer: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss_pct: float
    dry_run: bool  # True 时不向券商真实下单

    @staticmethod
    def from_env() -> "AppConfig":
        # 默认值集中在此，与 GUI 保存的 .env 保持一致
        return AppConfig(
            app_mode=os.getenv("APP_MODE", "backtest").strip().lower(),
            market=os.getenv("MARKET", "US").strip().upper(),
            symbols=[
                s.strip().upper()
                for s in os.getenv("SYMBOLS", "AAPL").split(",")
                if s.strip()
            ],
            fast_window=int(os.getenv("FAST_WINDOW", "20")),
            slow_window=int(os.getenv("SLOW_WINDOW", "60")),
            strategy_name=os.getenv("STRATEGY_NAME", "ma_cross").strip().lower(),
            rsi_window=int(os.getenv("RSI_WINDOW", "14")),
            rsi_oversold=float(os.getenv("RSI_OVERSOLD", "30")),
            rsi_overbought=float(os.getenv("RSI_OVERBOUGHT", "70")),
            bb_window=int(os.getenv("BB_WINDOW", "20")),
            bb_std=float(os.getenv("BB_STD", "2.0")),
            breakout_window=int(os.getenv("BREAKOUT_WINDOW", "20")),
            macd_fast=int(os.getenv("MACD_FAST", "12")),
            macd_slow=int(os.getenv("MACD_SLOW", "26")),
            macd_signal=int(os.getenv("MACD_SIGNAL", "9")),
            initial_capital=float(os.getenv("INITIAL_CAPITAL", "100000")),
            start_date=os.getenv("START_DATE", "2022-01-01"),
            end_date=os.getenv("END_DATE", "2024-12-31"),
            alpaca_api_key=os.getenv("ALPACA_API_KEY", ""),
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
            alpaca_paper=_env_bool("ALPACA_PAPER", True),
            futu_host=os.getenv("FUTU_HOST", "127.0.0.1"),
            futu_port=int(os.getenv("FUTU_PORT", "11111")),
            hk_broker=os.getenv("HK_BROKER", "sim").strip().lower(),
            live_qty_per_trade=int(os.getenv("LIVE_QTY_PER_TRADE", "1")),
            max_notional_per_trade=float(os.getenv("MAX_NOTIONAL_PER_TRADE", "10000")),
            allow_short=_env_bool("ALLOW_SHORT", False),
            enable_market_hours_check=_env_bool("ENABLE_MARKET_HOURS_CHECK", True),
            live_interval_minutes=int(os.getenv("LIVE_INTERVAL_MINUTES", "15")),
            live_max_retries=int(os.getenv("LIVE_MAX_RETRIES", "3")),
            alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL", ""),
            min_buying_power_buffer=float(os.getenv("MIN_BUYING_POWER_BUFFER", "100")),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.03")),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.08")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02")),
            dry_run=_env_bool("DRY_RUN", False),
        )
