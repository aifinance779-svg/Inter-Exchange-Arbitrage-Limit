"""
Central coordinator that ingests ticks, maintains snapshot state,
and produces spread signals for execution.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, time
from typing import Dict, Optional

from src.config.settings import settings
from src.core.logger import get_logger
from src.core.spread_detector import QuoteSnapshot, SpreadDetector, SpreadSignal


logger = get_logger("decision_engine")
heartbeat_logger = get_logger("live")


class DecisionEngine:
    def __init__(self, symbols):
        self.symbols = symbols
        self.detector = SpreadDetector(settings.min_spread)
        self.nse_ticks: Dict[str, dict] = defaultdict(dict)
        self.bse_ticks: Dict[str, dict] = defaultdict(dict)
        self._heartbeat_interval = 5.0  # Log heartbeat every 5 seconds

    def _market_open(self) -> bool:
        now = datetime.now().time()
        return settings.trading_start <= now <= settings.trading_end

    async def run(self, feed, callback, telemetry_hook=None):
        # Start heartbeat task that runs independently
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        try:
            while True:
                tick = await feed.next_tick()
                bucket = self.nse_ticks if tick.exchange == "NSE" else self.bse_ticks
                bucket[tick.symbol] = tick

                if not self._market_open():
                    continue

                snapshot = self._build_snapshot(tick.symbol)
                if not snapshot:
                    continue

                if telemetry_hook:
                    try:
                        telemetry_hook(snapshot)
                    except Exception as exc:
                        logger.exception("Telemetry hook error: %s", exc)

                signal = self.detector.evaluate(snapshot)
                if signal:
                    await callback(signal, snapshot)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self):
        """Background task that logs heartbeat every few seconds."""
        # Log immediately on start
        self._log_heartbeat()
        # Then log every interval
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            self._log_heartbeat()
    
    def _log_heartbeat(self):
        """Log heartbeat with current monitoring status."""
        # Find the best spread opportunity across all symbols
        best_spread = 0.0
        best_symbol = None
        best_nse_price = 0.0
        best_bse_price = 0.0
        
        for symbol in self.symbols:
            snapshot = self._build_snapshot(symbol)
            if snapshot:
                spread = abs(snapshot.nse_ltp - snapshot.bse_ltp)
                if spread > best_spread:
                    best_spread = spread
                    best_symbol = symbol
                    best_nse_price = snapshot.nse_ltp
                    best_bse_price = snapshot.bse_ltp
        
        if best_symbol:
            heartbeat_logger.info(
                "Monitoring... NSE=₹%.2f BSE=₹%.2f Spread=₹%.2f",
                best_nse_price,
                best_bse_price,
                best_spread
            )
        else:
            heartbeat_logger.info("Monitoring... (waiting for data)")

    def _build_snapshot(self, symbol: str) -> Optional[QuoteSnapshot]:
        nse = self.nse_ticks.get(symbol)
        bse = self.bse_ticks.get(symbol)
        if not nse or not bse:
            return None
        return QuoteSnapshot(
            symbol=symbol,
            nse_ltp=nse.ltp,
            bse_ltp=bse.ltp,
            nse_bid=nse.best_bid,
            nse_ask=nse.best_ask,
            bse_bid=bse.best_bid,
            bse_ask=bse.best_ask,
            nse_bid_qty=nse.bid_qty,
            nse_ask_qty=nse.ask_qty,
            bse_bid_qty=bse.bid_qty,
            bse_ask_qty=bse.ask_qty,
            nse_depth=nse.depth,
            bse_depth=bse.depth,
        )

