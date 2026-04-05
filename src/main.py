"""
命令行入口：根据环境变量 APP_MODE 执行回测、单次实盘或定时实盘循环。
运行前请在项目根目录配置 .env，或设置同名环境变量（见 config.py / .env.example）。
"""

from __future__ import annotations

from config import AppConfig
from engine.backtest import run_backtest
from engine.live import run_live_with_retries
from engine.scheduler import run_live_scheduler
from market.data import fetch_ohlcv
from market.validation import invalid_symbols


def main() -> None:
    """加载配置，校验标的与市场匹配，再按 APP_MODE 分发到对应引擎。"""
    cfg = AppConfig.from_env()

    # US 不应填港股代码、HK 不应填美股代码等
    bad = invalid_symbols(cfg.symbols, cfg.market)
    if bad:
        raise ValueError(f"Invalid symbols for market {cfg.market}: {bad}")
    print(f"[INFO] mode={cfg.app_mode} market={cfg.market} symbols={cfg.symbols} dry_run={cfg.dry_run}")

    if cfg.app_mode == "backtest":
        # 按标的拉历史 K 线，逐标的输出回测指标
        for symbol in cfg.symbols:
            df = fetch_ohlcv(symbol, cfg.market, cfg.start_date, cfg.end_date)
            result = run_backtest(
                df=df,
                cfg=cfg,
                initial_capital=cfg.initial_capital,
            )
            print(
                f"[BACKTEST] {symbol} "
                f"return={result['total_return']:.2%} "
                f"max_dd={result['max_drawdown']:.2%} "
                f"trades={result['trades']}"
            )
    elif cfg.app_mode == "live":
        # 执行一轮实盘决策（含重试、可选 webhook）；DRY_RUN 时不下真实单
        run_live_with_retries(cfg)
    elif cfg.app_mode == "live_loop":
        # 按 LIVE_INTERVAL_MINUTES 周期性调用 live，直到进程结束
        run_live_scheduler(cfg)
    else:
        raise ValueError(f"Unsupported APP_MODE: {cfg.app_mode}")


if __name__ == "__main__":
    main()
