"""
Entry point for the NSE ↔ BSE arbitrage bot.
"""

from __future__ import annotations

import argparse
import asyncio
import threading

from src.config import symbols as symbols_config
from src.config.settings import settings
from src.core.auth import authenticate
from src.core.data_feed import AngelOneDataFeed
from src.core.decision_engine import DecisionEngine
from src.core.logger import get_logger
from src.core.order_executor import OrderExecutor, OrderLeg
from src.core.safety import SafetyManager
from src.ui.terminal_dashboard import TerminalDashboard


logger = get_logger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="NSE-BSE Arbitrage Bot")
    parser.add_argument(
        "--backtest",
        help="Path to CSV file for offline backtest",
    )
    return parser.parse_args()


async def run_bot(args):
    if args.backtest:
        from pathlib import Path

        settings.backtest_file = Path(args.backtest)
    else:
        # Authenticate with Angel One before starting
        logger.info("Authenticating with Angel One SmartAPI...")
        if not authenticate():
            logger.error("Authentication failed. Cannot proceed.")
            return
        logger.info("Authentication successful. Starting bot...")

    watchlist = settings.symbols or symbols_config.DEFAULT_SYMBOLS
    if symbols_config.SYMBOL_META:
        settings.per_symbol_qty.update(
            {sym: meta.quantity for sym, meta in symbols_config.SYMBOL_META.items()}
        )

    loop = asyncio.get_running_loop()
    feed = AngelOneDataFeed(watchlist, loop)
    safety = SafetyManager()
    executor = OrderExecutor(safety)
    engine = DecisionEngine(watchlist)
    dashboard = TerminalDashboard() if settings.enable_dashboard else None

    if dashboard:
        threading.Thread(target=dashboard.live_loop, daemon=True).start()

    def telemetry(snapshot):
        if not dashboard:
            return
        dashboard.update(
            snapshot.symbol,
            nse_price=snapshot.nse_ltp,
            bse_price=snapshot.bse_ltp,
            spread=abs(snapshot.nse_ltp - snapshot.bse_ltp),
            quantity=settings.quantity_for(snapshot.symbol),
        )

    async def on_signal(signal, snapshot):
        try:
            logger.info(
                "Signal %s spread=%.2f buy=%s@₹%.2f sell=%s@₹%.2f qty=%s",
                signal.symbol,
                signal.spread,
                signal.buy_exchange,
                snapshot.nse_ltp if signal.buy_exchange == "NSE" else snapshot.bse_ltp,
                signal.sell_exchange,
                snapshot.nse_ltp if signal.sell_exchange == "NSE" else snapshot.bse_ltp,
                signal.quantity,
            )
            if dashboard:
                dashboard.update_stats(total_signals=dashboard.stats.get("total_signals", 0) + 1)
                dashboard.update(
                    signal.symbol,
                    signal=f"{signal.buy_exchange}->{signal.sell_exchange}",
                    status="PENDING",
                )
            buy_leg = OrderLeg(
                exchange=signal.buy_exchange,
                symbol=signal.symbol,
                side="BUY",
                quantity=signal.quantity,
            )
            sell_leg = OrderLeg(
                exchange=signal.sell_exchange,
                symbol=signal.symbol,
                side="SELL",
                quantity=signal.quantity,
            )
            result = await executor.execute_pair(buy_leg, sell_leg, signal.spread)
            if dashboard:
                status = "OK"
                if result.get("status") == "blocked":
                    status = "BLOCKED"
                elif any(isinstance(leg.get("result"), dict) and leg["result"].get("status") == "error"
                         for leg in (result.get("buy", {}), result.get("sell", {}))):
                    status = "FAIL"
                    dashboard.update_stats(failed_trades=dashboard.stats.get("failed_trades", 0) + 1)
                else:
                    dashboard.update_stats(successful_trades=dashboard.stats.get("successful_trades", 0) + 1)
                dashboard.update(signal.symbol, status=status)
        except Exception as exc:
            logger.exception("CRITICAL: Error processing signal for %s: %s", signal.symbol, exc)
            # Don't re-raise - let bot continue running
            if dashboard:
                dashboard.update(signal.symbol, status="ERROR")

    feed.start()
    try:
        await engine.run(feed, on_signal, telemetry_hook=telemetry)
    finally:
        feed.stop()


def main():
    args = parse_args()
    asyncio.run(run_bot(args))


if __name__ == "__main__":
    main()

