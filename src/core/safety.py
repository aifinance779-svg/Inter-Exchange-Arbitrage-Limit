"""
Risk checks and fail-safes.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict

from src.config.settings import settings
from src.core.logger import get_logger


logger = get_logger("safety")


@dataclass
class TradeRecord:
    timestamp: float
    symbol: str
    spread: float
    success: bool


class SafetyManager:
    def __init__(self):
        self.trade_history: Deque[TradeRecord] = deque(maxlen=1000)
        self.open_symbols: Dict[str, int] = {}
        self.failed_fills = 0

    def can_trade(self, symbol: str) -> bool:
        now = time.time()
        recent = [t for t in self.trade_history if now - t.timestamp <= 60]
        trades_per_minute = len(recent)
        if trades_per_minute >= settings.risk.max_trades_per_minute:
            logger.warning("Trade rate limit hit: %s/min", trades_per_minute)
            return False

        # Block concurrent trade on the same symbol
        if self.open_symbols.get(symbol, 0) > 0:
            logger.warning("Symbol %s already has an open trade; blocking new trade", symbol)
            return False

        if len(self.open_symbols) >= settings.risk.max_open_exposure:
            logger.warning("Open exposure limit reached")
            return False

        if self.failed_fills >= settings.risk.max_failed_fills:
            logger.error("Too many failed fills; blocking new trades")
            return False

        return True

    def register_open(self, symbol: str):
        self.open_symbols[symbol] = self.open_symbols.get(symbol, 0) + 1

    def register_close(self, symbol: str):
        if symbol in self.open_symbols:
            self.open_symbols[symbol] -= 1
            if self.open_symbols[symbol] <= 0:
                del self.open_symbols[symbol]

    def record_trade(self, symbol: str, spread: float, success: bool):
        self.trade_history.append(
            TradeRecord(timestamp=time.time(), symbol=symbol, spread=spread, success=success)
        )
        if success:
            self.failed_fills = 0
        else:
            self.failed_fills += 1






