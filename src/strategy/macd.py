"""
MACD：DIF 与信号线比较，DIF > 信号线为 1。
"""

from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, fast: int, slow: int, signal_window: int) -> pd.Series:
    """EMA 快慢线与 MACD 线的 EMA 信号线。"""

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig_line = macd_line.ewm(span=signal_window, adjust=False).mean()
    return (macd_line > sig_line).astype(int).fillna(0)
