from __future__ import annotations

from config import AppConfig
from engine.backtest import run_backtest
from engine.live import run_live_with_retries
from engine.scheduler import run_live_scheduler
from market.data import fetch_ohlcv
from market.validation import invalid_symbols


def main() -> None:
    cfg = AppConfig.from_env()
    bad = invalid_symbols(cfg.symbols, cfg.market)
    if bad:
        raise ValueError(f"Invalid symbols for market {cfg.market}: {bad}")
    print(f"[INFO] mode={cfg.app_mode} market={cfg.market} symbols={cfg.symbols} dry_run={cfg.dry_run}")

    if cfg.app_mode == "backtest":
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
        run_live_with_retries(cfg)
    elif cfg.app_mode == "live_loop":
        run_live_scheduler(cfg)
    else:
        raise ValueError(f"Unsupported APP_MODE: {cfg.app_mode}")


if __name__ == "__main__":
    main()
