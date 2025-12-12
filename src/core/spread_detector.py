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
        """
        Evaluate arbitrage opportunity using actual executable prices (bid/ask).
        
        Spread is calculated as the actual profit per share:
        - Buy on NSE, Sell on BSE: spread = BSE_bid - NSE_ask
        - Buy on BSE, Sell on NSE: spread = NSE_bid - BSE_ask
        
        This ensures the spread reflects the actual profit that can be realized.
        """
        qty = settings.quantity_for(snapshot.symbol)
        min_spread_threshold = max(self.min_spread, settings.min_spread)
        
        # Calculate spread for both directions using executable prices
        # Direction 1: Buy NSE, Sell BSE
        # Profit = BSE_bid (what you get) - NSE_ask (what you pay)
        spread_nse_buy = snapshot.bse_bid - snapshot.nse_ask
        
        # Direction 2: Buy BSE, Sell NSE
        # Profit = NSE_bid (what you get) - BSE_ask (what you pay)
        spread_bse_buy = snapshot.nse_bid - snapshot.bse_ask
        
        # Choose the direction with better spread
        if spread_nse_buy >= spread_bse_buy and spread_nse_buy >= min_spread_threshold:
            # Buy on NSE, Sell on BSE
            if not self._has_liquidity(snapshot.nse_ask_qty, snapshot.bse_bid_qty, qty):
                return None
            return SpreadSignal(
                symbol=snapshot.symbol,
                spread=spread_nse_buy,
                buy_exchange="NSE",
                sell_exchange="BSE",
                quantity=qty,
            )
        
        if spread_bse_buy >= min_spread_threshold:
            # Buy on BSE, Sell on NSE
            if not self._has_liquidity(snapshot.bse_ask_qty, snapshot.nse_bid_qty, qty):
                return None
            return SpreadSignal(
                symbol=snapshot.symbol,
                spread=spread_bse_buy,
                buy_exchange="BSE",
                sell_exchange="NSE",
                quantity=qty,
            )
        
        # No profitable opportunity
        return None

    @staticmethod
    def _has_liquidity(buy_side_qty: int, sell_side_qty: int, required: int) -> bool:
        return buy_side_qty >= required and sell_side_qty >= required






