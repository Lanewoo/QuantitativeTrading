"""
RSI 均值回归：超卖区置 1，超买区置 0；中间保持前序状态由逐行覆盖实现。
"""

from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, window: int, oversold: float, overbought: float) -> pd.Series:
    """简化版 RSI 信号（非完整状态机）。"""

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[rsi < oversold] = 1
    signal[rsi > overbought] = 0
    return signal.fillna(0)
