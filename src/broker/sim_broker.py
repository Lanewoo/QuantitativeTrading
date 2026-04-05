"""
本地模拟券商：持久化 JSON，用于 DRY_RUN、无密钥或港股默认路径。
不连接真实交易所，仅粗略更新持仓与购买力字段。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from pathlib import Path
import json

from .base import BaseBroker


@dataclass
class _Position:
    qty: int = 0
    avg_entry_price: float = 0.0


class SimBroker(BaseBroker):
    """
    Lightweight simulated broker for dry-run/HK workflows.
    State is persisted locally so repeated runs keep positions/equity.
    """

    def __init__(self, state_file: str = "logs/sim_account.json", initial_equity: float = 100000.0) -> None:
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load(initial_equity)

    def _load(self, initial_equity: float) -> dict:
        if not self._path.exists():
            state = {"equity": initial_equity, "buying_power": initial_equity, "positions": {}}
            self._save(state)
            return state
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            state = {"equity": initial_equity, "buying_power": initial_equity, "positions": {}}
            self._save(state)
            return state

    def _save(self, state: dict) -> None:
        self._path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")

    def is_market_open_now(self) -> bool:
        return True

    def get_position_qty(self, symbol: str) -> int:
        pos = self._state["positions"].get(symbol, asdict(_Position()))
        return int(pos.get("qty", 0))

    def get_position_avg_entry_price(self, symbol: str) -> float:
        pos = self._state["positions"].get(symbol, asdict(_Position()))
        return float(pos.get("avg_entry_price", 0.0))

    def get_buying_power(self) -> float:
        return float(self._state.get("buying_power", 0.0))

    def get_account_equity(self) -> float:
        return float(self._state.get("equity", 0.0))

    def submit_market_order(self, symbol: str, qty: int, side: str) -> None:
        # No live venue fill simulation here; we only maintain rough cash/position state.
        pos = self._state["positions"].get(symbol, asdict(_Position()))
        current_qty = int(pos.get("qty", 0))
        avg_entry = float(pos.get("avg_entry_price", 0.0))
        fill_price = avg_entry if avg_entry > 0 else 1.0
        notional = float(qty) * fill_price

        if side.lower() == "buy":
            new_qty = current_qty + qty
            self._state["positions"][symbol] = {"qty": new_qty, "avg_entry_price": fill_price}
            self._state["buying_power"] = float(self._state["buying_power"]) - notional
        else:
            new_qty = max(0, current_qty - qty)
            if new_qty == 0:
                self._state["positions"].pop(symbol, None)
            else:
                self._state["positions"][symbol] = {"qty": new_qty, "avg_entry_price": avg_entry}
            self._state["buying_power"] = float(self._state["buying_power"]) + notional

        self._save(self._state)

    def close(self) -> None:
        self._save(self._state)
