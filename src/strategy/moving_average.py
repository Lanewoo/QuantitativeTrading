"""
双均线策略：快均线 > 慢均线为 1，否则 0。
"""

from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, fast_window: int, slow_window: int) -> pd.Series:
    """SMA 交叉；快线必须小于慢线窗口。"""

    if fast_window >= slow_window:
        raise ValueError("FAST_WINDOW must be smaller than SLOW_WINDOW")
    fast = close.rolling(window=fast_window).mean()
    slow = close.rolling(window=slow_window).mean()
    signal = (fast > slow).astype(int)
    return signal.fillna(0)
