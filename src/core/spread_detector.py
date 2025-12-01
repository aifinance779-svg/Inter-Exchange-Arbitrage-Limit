"""
Spread calculation and liquidity validation primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config.settings import settings


@dataclass
class QuoteSnapshot:
    symbol: str
    nse_ltp: float
    bse_ltp: float
    nse_bid: float
    nse_ask: float
    bse_bid: float
    bse_ask: float
    nse_bid_qty: int
    nse_ask_qty: int
    bse_bid_qty: int
    bse_ask_qty: int
    nse_depth: dict
    bse_depth: dict


@dataclass
class SpreadSignal:
    symbol: str
    spread: float
    buy_exchange: str
    sell_exchange: str
    quantity: int


class SpreadDetector:
    def __init__(self, min_spread: float):
        self.min_spread = min_spread

    def evaluate(self, snapshot: QuoteSnapshot) -> Optional[SpreadSignal]:
        spread = abs(snapshot.nse_ltp - snapshot.bse_ltp)
        qty = settings.quantity_for(snapshot.symbol)
        if spread < max(self.min_spread, settings.min_spread):
            return None

        if snapshot.nse_ltp < snapshot.bse_ltp:
            if not self._has_liquidity(snapshot.nse_ask_qty, snapshot.bse_bid_qty, qty):
                return None
            return SpreadSignal(
                symbol=snapshot.symbol,
                spread=spread,
                buy_exchange="NSE",
                sell_exchange="BSE",
                quantity=qty,
            )

        if not self._has_liquidity(snapshot.bse_ask_qty, snapshot.nse_bid_qty, qty):
            return None
        return SpreadSignal(
            symbol=snapshot.symbol,
            spread=spread,
            buy_exchange="BSE",
            sell_exchange="NSE",
            quantity=qty,
        )

    @staticmethod
    def _has_liquidity(buy_side_qty: int, sell_side_qty: int, required: int) -> bool:
        return buy_side_qty >= required and sell_side_qty >= required






