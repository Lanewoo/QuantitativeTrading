from __future__ import annotations


def is_symbol_valid_for_market(symbol: str, market: str) -> bool:
    sym = symbol.strip().upper()
    mkt = market.strip().upper()
    if not sym:
        return False

    if mkt == "US":
        # US symbols should not be HK-coded or pure numeric codes.
        if sym.endswith(".HK"):
            return False
        if sym.isdigit():
            return False
        return True

    if mkt == "HK":
        # HK symbols should be numeric with optional .HK suffix.
        raw = sym.replace(".HK", "")
        return raw.isdigit()

    return False


def invalid_symbols(symbols: list[str], market: str) -> list[str]:
    return [s for s in symbols if not is_symbol_valid_for_market(s, market)]
