from __future__ import annotations

import pandas as pd

from config import AppConfig
from strategy import moving_average, rsi, bollinger, breakout, macd


def _to_1d_close(close: pd.Series | pd.DataFrame) -> pd.Series:
    # yfinance HK may return a single-column DataFrame; normalize to Series.
    if isinstance(close, pd.DataFrame):
        return close.iloc[:, 0]
    return close


def generate_signal_for_config(close: pd.Series, cfg: AppConfig) -> pd.Series:
    close = _to_1d_close(close)
    name = cfg.strategy_name
    if name == "ma_cross":
        return moving_average.generate_signal(close, cfg.fast_window, cfg.slow_window)
    if name == "rsi_reversion":
        return rsi.generate_signal(close, cfg.rsi_window, cfg.rsi_oversold, cfg.rsi_overbought)
    if name == "bollinger_reversion":
        return bollinger.generate_signal(close, cfg.bb_window, cfg.bb_std)
    if name == "breakout":
        return breakout.generate_signal(close, cfg.breakout_window)
    if name == "macd_cross":
        return macd.generate_signal(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    raise ValueError(f"Unsupported strategy: {name}")
