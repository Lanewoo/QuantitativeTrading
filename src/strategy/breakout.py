"""
区间突破：突破昨日滚动窗口最高/最低给出多空 1/0。
"""

from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, window: int) -> pd.Series:
    """prev_high/prev_low 用 shift(1) 避免当根包含在极值内。"""

    prev_high = close.rolling(window=window).max().shift(1)
    prev_low = close.rolling(window=window).min().shift(1)

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[close > prev_high] = 1
    signal[close < prev_low] = 0
    return signal.fillna(0)
