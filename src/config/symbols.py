"""
Default watchlist for the arbitrage bot.

Edit `DEFAULT_SYMBOLS` or supply your own via configuration. The map
`SYMBOL_META` can hold per-symbol overrides (e.g., quantity, thresholds).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


DEFAULT_SYMBOLS: List[str] = [
    "TATAMOTORS",
    "ICICIBANK",
    "HDFCBANK",
    "SBIN",
    "POWERGRID",
    "INFY",
    "TCS",
    "BPCL",
]


@dataclass(frozen=True)
class SymbolMeta:
    quantity: int
    min_spread: float
    comment: str = ""


SYMBOL_META: Dict[str, SymbolMeta] = {
    # Example:
    # "INFY": SymbolMeta(quantity=100, min_spread=0.4, comment="High liquidity"),
}






