from __future__ import annotations

from .base import BaseBroker


class FutuBroker(BaseBroker):
    """
    Optional HK live broker placeholder.
    To enable real trading, install OpenD + official futu-api package and replace this implementation.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def is_market_open_now(self) -> bool:
        raise NotImplementedError("Futu market clock query is not implemented yet.")

    def get_position_qty(self, symbol: str) -> int:
        raise NotImplementedError("Futu position query is not implemented yet.")

    def get_position_avg_entry_price(self, symbol: str) -> float:
        raise NotImplementedError("Futu avg entry price query is not implemented yet.")

    def get_buying_power(self) -> float:
        raise NotImplementedError("Futu buying power query is not implemented yet.")

    def get_account_equity(self) -> float:
        raise NotImplementedError("Futu account equity query is not implemented yet.")

    def submit_market_order(self, symbol: str, qty: int, side: str) -> None:
        raise NotImplementedError(
            "Futu live trading is optional and currently a placeholder. "
            "Integrate futu-api here if you need HK live trading."
        )

    def close(self) -> None:
        return
