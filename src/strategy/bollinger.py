from __future__ import annotations

import pandas as pd


def generate_signal(close: pd.Series, window: int, std_mult: float) -> pd.Series:
    ma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()
    lower = ma - std_mult * std
    upper = ma + std_mult * std

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[close < lower] = 1
    signal[close > upper] = 0
    return signal.fillna(0)
