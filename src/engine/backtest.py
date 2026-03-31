from __future__ import annotations

import pandas as pd

from config import AppConfig
from strategy.selector import generate_signal_for_config


def _to_1d_close(close: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(close, pd.DataFrame):
        return close.iloc[:, 0]
    return close


def run_backtest(
    df: pd.DataFrame,
    cfg: AppConfig,
    initial_capital: float,
) -> dict:
    close = _to_1d_close(df["close"])
    signal = generate_signal_for_config(close, cfg)
    position = signal.shift(1).fillna(0)
    ret = close.pct_change().fillna(0)
    strategy_ret = position * ret
    equity_curve = (1 + strategy_ret).cumprod() * initial_capital

    total_return = float((equity_curve.iloc[-1] / initial_capital) - 1)
    max_drawdown = float((equity_curve / equity_curve.cummax() - 1).min())
    trade_changes = (signal.diff().abs() == 1).sum()
    trades = int(trade_changes.item() if hasattr(trade_changes, "item") else trade_changes)

    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "equity_curve": equity_curve,
    }
