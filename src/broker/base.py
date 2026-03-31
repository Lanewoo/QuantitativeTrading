from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBroker(ABC):
    @abstractmethod
    def is_market_open_now(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_position_qty(self, symbol: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_position_avg_entry_price(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_buying_power(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_account_equity(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def submit_market_order(self, symbol: str, qty: int, side: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
