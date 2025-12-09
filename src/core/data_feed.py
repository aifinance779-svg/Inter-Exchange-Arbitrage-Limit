"""
Real-time data feed via Angel One SmartAPI WebSocket with automatic reconnects.

The feed publishes ticks through an asyncio queue for downstream consumers.
In backtest mode the feed replays historical data from CSV (timestamp, symbol,
exchange, ltp, bid, ask, depth json).
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from src.config.settings import settings
from src.core.logger import get_logger


logger = get_logger("data_feed")


@dataclass
class Tick:
    symbol: str
    exchange: str
    ltp: float
    best_bid: float
    best_ask: float
    bid_qty: int
    ask_qty: int
    depth: Dict[str, List[Dict[str, Any]]]


class AngelOneDataFeed:
    def __init__(self, symbols: List[str], loop: asyncio.AbstractEventLoop):
        self.symbols = symbols
        self.loop = loop
        self.queue: asyncio.Queue[Tick] = asyncio.Queue()
        self._ws: Optional[SmartWebSocketV2] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._instrument_tokens: Dict[str, str] = {}  # symbol -> token (Angel One uses string tokens)

    def start(self) -> None:
        if settings.backtest_file:
            self._start_backtest()
            return
        self._start_realtime()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception as exc:
                logger.debug("Error closing WebSocket: %s", exc)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    async def next_tick(self) -> Tick:
        return await self.queue.get()

    # --- Real-time handling -------------------------------------------------
    def _start_realtime(self) -> None:
        logger.info("Starting Angel One WebSocket feed for %s", self.symbols)
        self._instrument_tokens = self._resolve_tokens(self.symbols)
        
        if not settings.feed_token:
            logger.error("Feed token not available. Please authenticate first.")
            return

        # Angel One WebSocket configuration
        auth_token = settings.access_token
        api_key = settings.api_key
        feed_token = settings.feed_token
        
        # Prepare correlation ID
        correlation_id = "arbitrage_bot_001"
        
        # Build subscription list for SmartWebSocketV2: [{exchangeType: int, tokens: [str]}]
        mode = 3  # SNAP_QUOTE mode provides depth + quote data
        exchange_type_map = {
            "NSE": SmartWebSocketV2.NSE_CM,
            "BSE": SmartWebSocketV2.BSE_CM,
            "NFO": SmartWebSocketV2.NSE_FO,
            "BFO": SmartWebSocketV2.BSE_FO,
        }
        token_groups: Dict[int, List[str]] = {}
        for key, token_string in self._instrument_tokens.items():
            if "|" in token_string:
                exchange_code, token_value = token_string.split("|", 1)
            else:
                exchange_code = "NSE" if "_NSE" in key else "BSE" if "_BSE" in key else "NSE"
                token_value = token_string
            exchange_code = exchange_code.upper()
            exchange_type = exchange_type_map.get(exchange_code)
            if not exchange_type:
                logger.warning("Unsupported exchange %s for token %s", exchange_code, token_string)
                continue
            token_groups.setdefault(exchange_type, []).append(str(token_value))
        
        token_list = [
            {"exchangeType": exchange_type, "tokens": tokens}
            for exchange_type, tokens in token_groups.items()
            if tokens
        ]
        
        if not token_list:
            logger.error("No tokens to subscribe to. WebSocket will not receive data.")
            return
        
        def on_message(ws, message):
            logger.debug("WebSocket message: %s", message)

        def on_data(ws, data):
            try:
                self._process_tick(data)
            except Exception as exc:
                logger.exception("Failed to process WebSocket payload: %s", exc)
        
        def on_error(ws, error):
            logger.error("WebSocket error: %s", error)
        
        def on_close(ws):
            logger.warning("WebSocket closed")
            if not self._stop_event.is_set():
                # Auto-reconnect
                threading.Timer(2.0, self._start_realtime).start()
        
        def on_open(ws):
            total_tokens = sum(len(item["tokens"]) for item in token_list)
            logger.info("WebSocket connected. Subscribing to %d instruments", total_tokens)
            try:
                self._ws.subscribe(correlation_id, mode, token_list)
            except Exception as exc:
                logger.error("Failed to subscribe: %s", exc)
        
        def run():
            while not self._stop_event.is_set():
                try:
                    self._ws = SmartWebSocketV2(
                        auth_token=auth_token,
                        api_key=api_key,
                        client_code=settings.client_id,
                        feed_token=feed_token,
                    )

                    self._ws.on_open = on_open
                    self._ws.on_message = on_message
                    self._ws.on_data = on_data
                    self._ws.on_error = on_error
                    self._ws.on_close = on_close
                    self._ws.connect()
                except Exception as exc:
                    logger.error("WebSocket error: %s. Reconnecting...", exc)
                    if self._stop_event.wait(timeout=2):
                        break

        self._thread = threading.Thread(target=run, name="angelone-ws", daemon=True)
        self._thread.start()

    @staticmethod
    def _normalize_price(value: Optional[float]) -> float:
        if value is None:
            return 0.0
        try:
            price = float(value)
        except (TypeError, ValueError):
            return 0.0
        # SmartAPI returns prices scaled by 100 for equities
        if price > 2000:
            return price / 100.0
        return price

    def _process_tick(self, tick_data: Dict):
        """Process Angel One tick data format."""
        try:
            token = tick_data.get("token") or tick_data.get("tk")
            if not token:
                return

            symbol, exchange = self._symbol_from_token(token)
            if not symbol:
                return

            ltp = self._normalize_price(
                tick_data.get("last_traded_price", tick_data.get("ltp"))
            )

            buy_levels = (
                tick_data.get("best_5_buy_data")
                or tick_data.get("depth_20_buy_data")
                or tick_data.get("buyDepth")
            )
            sell_levels = (
                tick_data.get("best_5_sell_data")
                or tick_data.get("depth_20_sell_data")
                or tick_data.get("sellDepth")
            )

            def _depth(levels):
                depth = []
                if not levels:
                    return depth
                for level in levels[: settings.depth_levels]:
                    price = self._normalize_price(level.get("price"))
                    quantity = int(level.get("quantity", 0))
                    depth.append({"price": price, "quantity": quantity})
                return depth

            buy_depth = _depth(buy_levels)
            sell_depth = _depth(sell_levels)

            if not buy_depth:
                best_bid = self._normalize_price(tick_data.get("bp1", ltp))
                bid_qty = int(tick_data.get("bq1", 0))
            else:
                best_bid = buy_depth[0]["price"]
                bid_qty = buy_depth[0]["quantity"]

            if not sell_depth:
                best_ask = self._normalize_price(tick_data.get("sp1", ltp))
                ask_qty = int(tick_data.get("sq1", 0))
            else:
                best_ask = sell_depth[0]["price"]
                ask_qty = sell_depth[0]["quantity"]
            
            payload = Tick(
                symbol=symbol,
                exchange=exchange,
                ltp=ltp,
                best_bid=best_bid,
                best_ask=best_ask,
                bid_qty=bid_qty,
                ask_qty=ask_qty,
                depth={
                    "buy": buy_depth,
                    "sell": sell_depth,
                },
            )
            logger.debug("Tick %s/%s LTP=%.2f bid=%.2f ask=%.2f", symbol, exchange, ltp, best_bid, best_ask)
            
            # Check if event loop is still open before putting in queue
            if self.loop.is_closed():
                return  # Silently ignore if loop is closed
            
            self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                # Silently ignore - bot is shutting down
                return
            raise  # Re-raise other RuntimeErrors
        except Exception as exc:
            logger.exception("Failed to process tick: %s", exc)

    # --- Token lookup -------------------------------------------------------
    def _resolve_tokens(self, symbols: List[str]) -> Dict[str, str]:
        """
        Resolve instrument tokens from Angel One instrument master.
        Returns mapping: symbol -> "NSE|token" or "BSE|token"
        """
        if not symbols:
            return {}
        
        from src.core.auth import get_authenticated_api
        
        authenticated_api = get_authenticated_api()
        if not authenticated_api:
            logger.error("No authenticated API instance available for token resolution")
            return {}
        
        token_map = {}
        
        try:
            # Get instrument master data
            # Angel One provides instrument master via getMasterData or similar
            # We'll fetch it and search for our symbols
            logger.info("Fetching instrument master data for %d symbols...", len(symbols))
            
            # Try to get master data - this might be cached or fetched from API
            # Check if there's a method to get instrument master
            if hasattr(authenticated_api, 'getMasterData'):
                master_data = authenticated_api.getMasterData("NSE")
                # Process master data to find tokens
                # Master data format varies, but typically contains symbol, token, exchange info
                for symbol in symbols:
                    nse_token = self._find_token_in_master(master_data, symbol, "NSE")
                    bse_token = self._find_token_in_master(master_data, symbol, "BSE") if "BSE" in str(master_data) else None
                    
                    # Store both NSE and BSE tokens if available
                    # We'll need to handle both exchanges separately
                    if nse_token:
                        token_map[f"{symbol}_NSE"] = f"NSE|{nse_token}"
                    if bse_token:
                        token_map[f"{symbol}_BSE"] = f"BSE|{bse_token}"
            
            # Alternative: Use searchScrip or similar method if available
            # For now, let's create a helper that uses the instrument master file
            # Angel One typically provides instrument master as CSV or JSON
            
            # If master data fetch fails, try manual lookup
            if not token_map:
                logger.warning("Could not fetch from master data. Using manual token lookup.")
                token_map = self._manual_token_lookup(symbols)
            
            if token_map:
                logger.info("Resolved %d instrument tokens", len(token_map))
            else:
                logger.warning("No tokens resolved. WebSocket will not receive data.")
                logger.warning("Please implement token resolution or provide manual mapping.")
            
        except Exception as exc:
            logger.exception("Error resolving tokens: %s", exc)
            logger.warning("Falling back to manual token lookup")
            token_map = self._manual_token_lookup(symbols)
        
        return token_map
    
    def _find_token_in_master(self, master_data, symbol: str, exchange: str) -> Optional[str]:
        """Find token for symbol in master data."""
        # This is a placeholder - implement based on actual master data structure
        # Master data might be a list of dicts with keys like 'symbol', 'token', 'exchange'
        if isinstance(master_data, list):
            for item in master_data:
                if isinstance(item, dict):
                    if (item.get('symbol', '').upper() == symbol.upper() and 
                        item.get('exchange', '').upper() == exchange.upper()):
                        return str(item.get('token', ''))
        return None
    
    def _manual_token_lookup(self, symbols: List[str]) -> Dict[str, str]:
        """
        Manual token lookup - you need to provide token mappings here.
        Format: {symbol_exchange: "EXCHANGE|token"}
        
        You can get tokens from:
        1. Angel One website (instrument search)
        2. Angel One API documentation
        3. Instrument master CSV file
        4. Run scripts/get_tokens.py to fetch tokens automatically
        """
        # Token mappings for default symbols
        # Format: "SYMBOL_EXCHANGE": "EXCHANGE|TOKEN"
        # These tokens are from TOKEN_SETUP.md - verify they are current
        manual_map = {
            "RELIANCE_NSE": "NSE|2885",
            "RELIANCE_BSE": "BSE|500325",
            "WIPRO_NSE": "NSE|3787",
            "WIPRO_BSE": "BSE|507685",
            "TATASTEEL_NSE": "NSE|3499",
            "TATASTEEL_BSE": "BSE|500470",
            "HDFCBANK_NSE": "NSE|133275",
            "HDFCBANK_BSE": "BSE|500180",
            "TATAMOTORS_NSE": "NSE|884737",
            "TATAMOTORS_BSE": "BSE|500570",
            "ICICIBANK_NSE": "NSE|1270529",
            "ICICIBANK_BSE": "BSE|532174",
            
            "SBIN_NSE": "NSE|3045",
            "SBIN_BSE": "BSE|500112",
            "POWERGRID_NSE": "NSE|383385",
            "POWERGRID_BSE": "BSE|532498",
            "INFY_NSE": "NSE|408065",
            "INFY_BSE": "BSE|500209",
            "TCS_NSE": "NSE|2953217",
            "TCS_BSE": "BSE|532540",
            "BPCL_NSE": "NSE|134809",
            "BPCL_BSE": "BSE|500547",
        }
        
        # Build token map from manual mappings
        token_map = {}
        for symbol in symbols:
            nse_key = f"{symbol}_NSE"
            bse_key = f"{symbol}_BSE"
            if nse_key in manual_map:
                token_map[nse_key] = manual_map[nse_key]
            if bse_key in manual_map:
                token_map[bse_key] = manual_map[bse_key]
        
        if not token_map:
            logger.error("No manual token mappings found. Please add tokens to _manual_token_lookup()")
            logger.error("You can find tokens from Angel One instrument search or API")
        
        return token_map

    def _symbol_from_token(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Map token back to symbol.
        Returns (base_symbol, exchange)
        """
        for key, tok_string in self._instrument_tokens.items():
            if "|" in tok_string:
                exchange_code, tok_part = tok_string.split("|", 1)
            else:
                exchange_code, tok_part = ("", tok_string)

            if tok_part == token:
                base_symbol = key.replace("_NSE", "").replace("_BSE", "")
                if key.endswith("_NSE"):
                    return base_symbol, "NSE"
                if key.endswith("_BSE"):
                    return base_symbol, "BSE"
                exchange = exchange_code or "NSE"
                return base_symbol, exchange

        return None, None

    # --- Backtest replay ----------------------------------------------------
    def _start_backtest(self) -> None:
        logger.info("Starting backtest replay from %s", settings.backtest_file)

        async def replay():
            import csv

            with settings.backtest_file.open() as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    tick = Tick(
                        symbol=row["symbol"],
                        exchange=row["exchange"],
                        ltp=float(row["ltp"]),
                        best_bid=float(row["best_bid"]),
                        best_ask=float(row["best_ask"]),
                        bid_qty=int(row["bid_qty"]),
                        ask_qty=int(row["ask_qty"]),
                        depth=json.loads(row["depth_json"]),
                    )
                    await self.queue.put(tick)
                    await asyncio.sleep(settings.poll_interval_ms / 1000)

        asyncio.run_coroutine_threadsafe(replay(), self.loop)

