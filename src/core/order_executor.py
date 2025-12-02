"""
Order execution engine leveraging Angel One SmartAPI.

Orders are fired concurrently using `asyncio` and `ThreadPoolExecutor`
to satisfy the "simultaneous" requirement while keeping the main loop async.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from typing import Dict


from SmartApi.smartConnect import SmartConnect

from src.config.settings import settings
from src.core.logger import get_logger
from src.core.safety import SafetyManager
from src.core.tokens import TOKEN_MAP


logger = get_logger("order_executor")


@dataclass
class OrderLeg:
    exchange: str
    symbol: str
    side: str  # BUY / SELL
    quantity: int
    order_type: str = "MARKET"  # MARKET, LIMIT, STOPLOSS_LIMIT, etc.
    product: str = "INTRADAY"  # INTRADAY, DELIVERY, MARGIN, etc.
    validity: str = "IOC"  # IOC, DAY, TTL
    price: float = 0.0  # For LIMIT orders
    trigger_price: float = 0.0  # For STOPLOSS orders


class OrderExecutor:
    def __init__(self, safety: SafetyManager):
        self.safety = safety
        # Use the authenticated SmartConnect instance from auth module
        from src.core.auth import get_authenticated_api
        authenticated_api = get_authenticated_api()
        if authenticated_api:
            self.smart_api = authenticated_api
        else:
            # Fallback: create new instance (should not happen if auth was successful)
            self.smart_api = SmartConnect(api_key=settings.api_key)
            logger.warning("Using unauthenticated SmartConnect instance")
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    def _ensure_authenticated(self):
        """Ensure we have a valid session token."""
        if not settings.access_token:
            from src.core.auth import authenticate
            if not authenticate():
                raise RuntimeError("Authentication required but failed")

    async def execute_pair(self, buy_leg: OrderLeg, sell_leg: OrderLeg, spread: float) -> Dict:
        if not self.safety.can_trade(buy_leg.symbol):
            return {"status": "blocked", "reason": "risk"}

        loop = asyncio.get_event_loop()
        self.safety.register_open(buy_leg.symbol)

        async def place(leg: OrderLeg):
            return await loop.run_in_executor(
                self.executor, self._place_order, leg
            )

        buy_task = asyncio.create_task(place(buy_leg))
        sell_task = asyncio.create_task(place(sell_leg))

        results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
        summary = {
            "buy": {"result": results[0], "leg": buy_leg},
            "sell": {"result": results[1], "leg": sell_leg},
        }
        await self._post_execute(buy_leg.symbol, summary, spread)
        return summary

    def _place_order(self, leg: OrderLeg):
        self._ensure_authenticated()
        try:
            # Reinitialize SmartConnect with current token if needed
            # SmartConnect should maintain session, but we ensure token is available
            if not hasattr(self.smart_api, '_session_token') or not self.smart_api._session_token:
                # Token might be stored differently - try to set it
                # This is a fallback; normally token is set during generateSession
                pass
            # Map order type to Angel One format
            order_type_map = {
                "MARKET": "MARKET",
                "LIMIT": "LIMIT",
                "IOC": "MARKET",  # IOC is handled via validity
            }
            
            # Map product type
            product_map = {
                "MIS": "INTRADAY",
                "INTRADAY": "INTRADAY",
                "CNC": "DELIVERY",
                "DELIVERY": "DELIVERY",
            }
            
            # Build order params for Angel One
            instrument = self._get_instrument(leg.symbol, leg.exchange)
            if not instrument:
                return {"error": "missing token", "status": "error"}

            order_params = {
                "variety": "NORMAL",  # NORMAL, STOPLOSS, AMO, etc.
                "tradingsymbol": instrument["tradingsymbol"],
                "symboltoken": instrument["token"],
                "transactiontype": leg.side,  # BUY or SELL
                "exchange": leg.exchange,
                "ordertype": order_type_map.get(leg.order_type, "MARKET"),
                "producttype": product_map.get(leg.product, "INTRADAY"),
                "duration": leg.validity,  # IOC, DAY, TTL
                "quantity": str(leg.quantity),
            }
            
            # Add price for LIMIT orders
            if leg.order_type == "LIMIT" and leg.price > 0:
                order_params["price"] = str(leg.price)
            
            # Add trigger price for STOPLOSS orders
            if leg.trigger_price > 0:
                order_params["triggerprice"] = str(leg.trigger_price)
            
            response = self.smart_api.placeOrder(order_params)
            
            if response and response.get("status") and response.get("data"):
                order_id = response["data"].get("orderid")
                status = self._wait_for_completion(order_id)
                logger.info(
                    "Order placed %s %s %s qty=%s id=%s",
                    leg.exchange,
                    leg.side,
                    leg.symbol,
                    leg.quantity,
                    order_id,
                )
                return {"order_id": order_id, "status": status}
            else:
                error_msg = response.get("message", "Unknown error") if response else "No response"
                logger.error("Order placement failed: %s", error_msg)
                return {"error": error_msg, "status": "error"}
        except Exception as exc:
            logger.exception("Order failed for %s %s: %s", leg.symbol, leg.side, exc)
            return {"error": str(exc), "status": "error"}
    
    def _get_instrument(self, symbol: str, exchange: str) -> Dict[str, str] | None:
        key = f"{symbol.upper()}_{exchange.upper()}"
        instrument = TOKEN_MAP.get(key)

        if not instrument:
            logger.error("Token NOT FOUND for %s (%s)", symbol, exchange)
            return None

        return instrument

    def _wait_for_completion(self, order_id: str, timeout: float = 3.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # Angel One order status check
                response = self.smart_api.orderBook()
                if response and response.get("status") and response.get("data"):
                    orders = response["data"]
                    for order in orders:
                        if str(order.get("orderid")) == str(order_id):
                            status = order.get("status", "PENDING")
                            # Map Angel One status to standard status
                            status_map = {
                                "complete": "COMPLETE",
                                "rejected": "REJECTED",
                                "cancelled": "CANCELLED",
                                "pending": "PENDING",
                                "open": "OPEN",
                            }
                            mapped_status = status_map.get(status.lower(), status.upper())
                            if mapped_status in {"COMPLETE", "REJECTED", "CANCELLED"}:
                                return mapped_status
            except Exception as exc:
                logger.debug("Order status fetch failed for %s: %s", order_id, exc)
            time.sleep(0.2)
        return "PENDING"

    async def _post_execute(self, symbol: str, summary: Dict, spread: float):
        def is_success(res):
            return isinstance(res, dict) and res.get("status") == "COMPLETE"

        buy_ok = is_success(summary["buy"]["result"])
        sell_ok = is_success(summary["sell"]["result"])

        if buy_ok and sell_ok:
            self.safety.record_trade(symbol, spread, True)
            self.safety.register_close(symbol)
            return

        await self._failsafe(symbol, summary)
        self.safety.record_trade(symbol, spread, False)
        self.safety.register_close(symbol)

    async def _failsafe(self, symbol: str, summary: Dict):
        logger.error("Failsafe triggered for %s: %s", symbol, summary)
        legs_to_close = []
        buy_res = summary["buy"]["result"]
        sell_res = summary["sell"]["result"]
        if isinstance(buy_res, dict) and buy_res.get("status") == "COMPLETE":
            legs_to_close.append(
                OrderLeg(
                    exchange=summary["buy"]["leg"].exchange,
                    symbol=symbol,
                    side="SELL" if summary["buy"]["leg"].side == "BUY" else "BUY",
                    quantity=summary["buy"]["leg"].quantity,
                )
            )
        if isinstance(sell_res, dict) and sell_res.get("status") == "COMPLETE":
            legs_to_close.append(
                OrderLeg(
                    exchange=summary["sell"]["leg"].exchange,
                    symbol=symbol,
                    side="BUY" if summary["sell"]["leg"].side == "SELL" else "SELL",
                    quantity=summary["sell"]["leg"].quantity,
                )
            )

        if legs_to_close:
            loop = asyncio.get_event_loop()
            await asyncio.gather(
                *[
                    loop.run_in_executor(self.executor, self._place_order, leg)
                    for leg in legs_to_close
                ]
            )

