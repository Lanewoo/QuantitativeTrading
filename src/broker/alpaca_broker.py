from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from .base import BaseBroker


class AlpacaBroker(BaseBroker):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True) -> None:
        if not api_key or not secret_key:
            raise ValueError("Alpaca credentials are required for live mode.")
        self._client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)

    def get_position_qty(self, symbol: str) -> int:
        try:
            pos = self._client.get_open_position(symbol_or_asset_id=symbol)
            return int(float(pos.qty))
        except Exception:
            return 0

    def get_position_avg_entry_price(self, symbol: str) -> float:
        try:
            pos = self._client.get_open_position(symbol_or_asset_id=symbol)
            return float(pos.avg_entry_price)
        except Exception:
            return 0.0

    def is_market_open_now(self) -> bool:
        clock = self._client.get_clock()
        return bool(clock.is_open)

    def get_buying_power(self) -> float:
        account = self._client.get_account()
        return float(account.buying_power)

    def get_account_equity(self) -> float:
        account = self._client.get_account()
        return float(account.equity)

    def submit_market_order(self, symbol: str, qty: int, side: str) -> None:
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        self._client.submit_order(order_data=order)

    def close(self) -> None:
        return
