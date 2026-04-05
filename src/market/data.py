"""
行情数据：yfinance 拉取 OHLCV；港股代码规范为 Yahoo 格式（如 9988.HK）。
"""

from __future__ import annotations

import pandas as pd

import yfinance as yf


def normalize_symbol(symbol: str, market: str) -> str:
    """按市场把用户输入转成 yfinance 可识别的 ticker。"""

    market = market.upper().strip()
    symbol = symbol.strip()
    if market == "US":
        return symbol.upper()
    if market == "HK":
        sym = symbol.upper().replace(".HK", "").strip()
        # Keep digits only to handle inputs like "09988.HK ", " 9988 ", etc.
        digits = "".join(ch for ch in sym if ch.isdigit())
        if digits:
            # Accept inputs like 700 / 0700 / 09988 and normalize to Yahoo HK format.
            norm = str(int(digits))  # strip leading zeros safely
            return f"{norm:0>4}.HK"
        return symbol.upper()
    return symbol.upper()


def fetch_ohlcv(symbol: str, market: str, start_date: str, end_date: str) -> pd.DataFrame:
    """下载并返回小写列名的 OHLCV；无数据则抛错。"""

    yf_symbol = normalize_symbol(symbol, market)
    df = yf.download(yf_symbol, start=start_date, end=end_date, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {symbol} ({market})")
    df = df.rename(columns=str.lower)
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].dropna()
