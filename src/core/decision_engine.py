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
        
        logger.info("Decision engine started. Waiting for market data...")
        logger.info("Market hours: %s to %s", settings.trading_start, settings.trading_end)
        logger.info("Monitoring symbols: %s", self.symbols)
        logger.info("Minimum spread threshold: ₹%.2f", settings.min_spread)
        
        tick_count = 0
        try:
            while True:
                try:
                    logger.debug("Waiting for next tick from feed...")
                    tick = await feed.next_tick()
                    tick_count += 1
                    logger.debug("Received tick #%d: %s %s LTP=₹%.2f bid=₹%.2f ask=₹%.2f", 
                                tick_count, tick.symbol, tick.exchange, tick.ltp, tick.best_bid, tick.best_ask)
                    
                    bucket = self.nse_ticks if tick.exchange == "NSE" else self.bse_ticks
                    bucket[tick.symbol] = tick

                    now = datetime.now().time()
                    if not self._market_open():
                        logger.debug("Market closed. Current time: %s, Market hours: %s-%s. Skipping tick.", 
                                   now, settings.trading_start, settings.trading_end)
                        continue

                    snapshot = self._build_snapshot(tick.symbol)
                    if not snapshot:
                        nse_has = tick.symbol in self.nse_ticks
                        bse_has = tick.symbol in self.bse_ticks
                        logger.debug("Cannot build snapshot for %s: NSE=%s BSE=%s (need both)", 
                                    tick.symbol, nse_has, bse_has)
                        continue

                    logger.debug("Snapshot built for %s: NSE=₹%.2f BSE=₹%.2f spread=₹%.2f", 
                               snapshot.symbol, snapshot.nse_ltp, snapshot.bse_ltp, 
                               abs(snapshot.nse_ltp - snapshot.bse_ltp))

                    if telemetry_hook:
                        try:
                            telemetry_hook(snapshot)
                        except Exception as exc:
                            logger.exception("Telemetry hook error: %s", exc)

                    signal = self.detector.evaluate(snapshot)
                    if signal:
                        logger.info("Spread signal detected: %s spread=₹%.2f", signal.symbol, signal.spread)
                        await callback(signal, snapshot)
                    else:
                        logger.debug("No signal for %s (spread=₹%.2f < threshold=₹%.2f)", 
                                   snapshot.symbol, abs(snapshot.nse_ltp - snapshot.bse_ltp), settings.min_spread)
                except asyncio.CancelledError:
                    logger.info("Decision engine cancelled")
                    raise
                except Exception as exc:
                    logger.exception("Error processing tick: %s", exc)
                    # Wait a bit before retrying to avoid tight error loop
                    await asyncio.sleep(1)
        finally:
            logger.info("Decision engine shutting down. Processed %d ticks.", tick_count)
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self):
        """Background task that logs heartbeat every few seconds."""
        logger.info("Heartbeat loop started")
        # Log immediately on start
        self._log_heartbeat()
        # Then log every interval
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                self._log_heartbeat()
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
            raise
    
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

