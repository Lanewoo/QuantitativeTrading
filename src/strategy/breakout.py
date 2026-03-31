from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, window: int) -> pd.Series:
    prev_high = close.rolling(window=window).max().shift(1)
    prev_low = close.rolling(window=window).min().shift(1)

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[close > prev_high] = 1
    signal[close < prev_low] = 0
    return signal.fillna(0)
