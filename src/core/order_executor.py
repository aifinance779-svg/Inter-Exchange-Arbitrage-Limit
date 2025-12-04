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
        try:
            if not self.safety.can_trade(buy_leg.symbol):
                return {"status": "blocked", "reason": "risk"}

            loop = asyncio.get_event_loop()
            self.safety.register_open(buy_leg.symbol)

            async def place(leg: OrderLeg):
                try:
                    return await loop.run_in_executor(
                        self.executor, self._place_order, leg
                    )
                except Exception as exc:
                    logger.exception("Exception in place executor for %s %s: %s", leg.symbol, leg.side, exc)
                    return {"error": str(exc), "status": "error"}

            buy_task = asyncio.create_task(place(buy_leg))
            sell_task = asyncio.create_task(place(sell_leg))

            results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
            summary = {
                "buy": {"result": results[0], "leg": buy_leg},
                "sell": {"result": results[1], "leg": sell_leg},
            }
            await self._post_execute(buy_leg.symbol, summary, spread)
            return summary
        except Exception as exc:
            logger.exception("CRITICAL: Error in execute_pair for %s: %s", buy_leg.symbol, exc)
            # Ensure we close the position even on error
            try:
                self.safety.register_close(buy_leg.symbol)
            except:
                pass
            return {
                "buy": {"result": {"error": str(exc), "status": "error"}, "leg": buy_leg},
                "sell": {"result": {"error": str(exc), "status": "error"}, "leg": sell_leg},
            }

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
            
            # SmartAPI returns order ID as string on success, dict on error
            if isinstance(response, str):
                # Check if it's a numeric string (order ID) or error message
                if response.isdigit() or (response.replace('-', '').isdigit()):
                    # This is an order ID - order was placed successfully!
                    order_id = response
                    logger.info(
                        "Order placed %s %s %s qty=%s id=%s",
                        leg.exchange,
                        leg.side,
                        leg.symbol,
                        leg.quantity,
                        order_id,
                    )
                    # Wait for order completion
                    status = self._wait_for_completion(order_id)
                    
                    # Get execution price from order book
                    execution_price = None
                    try:
                        order_book = self.smart_api.orderBook()
                        if order_book and isinstance(order_book, dict) and order_book.get("status") and order_book.get("data"):
                            for order in order_book["data"]:
                                if str(order.get("orderid")) == str(order_id):
                                    execution_price = order.get("averageprice") or order.get("price")
                                    break
                    except Exception as e:
                        logger.debug("Could not fetch execution price: %s", e)
                    
                    return {"order_id": order_id, "status": status, "price": execution_price}
                else:
                    # Non-numeric string - likely an error message
                    logger.error("Order placement returned error string: %s", response)
                    logger.error("Order params were: %s", order_params)
                    return {"error": response, "status": "error"}
            
            # Handle dict response (some API versions return dict)
            if isinstance(response, dict):
                if response.get("status") and response.get("data"):
                    order_id = response["data"].get("orderid")
                    status = self._wait_for_completion(order_id)
                    
                    # Get execution price
                    execution_price = None
                    try:
                        order_book = self.smart_api.orderBook()
                        if order_book and isinstance(order_book, dict) and order_book.get("status") and order_book.get("data"):
                            for order in order_book["data"]:
                                if str(order.get("orderid")) == str(order_id):
                                    execution_price = order.get("averageprice") or order.get("price")
                                    break
                    except Exception as e:
                        logger.debug("Could not fetch execution price: %s", e)
                    
                    logger.info(
                        "Order placed %s %s %s qty=%s id=%s price=%s",
                        leg.exchange,
                        leg.side,
                        leg.symbol,
                        leg.quantity,
                        order_id,
                        execution_price if execution_price else "N/A",
                    )
                    return {"order_id": order_id, "status": status, "price": execution_price}
                else:
                    error_msg = response.get("message", "Unknown error")
                    logger.error("Order placement failed: %s", error_msg)
                    logger.debug("Full response: %s", response)
                    return {"error": error_msg, "status": "error"}
            
            # Unexpected response type
            logger.error("Order placement returned unexpected type: %s (type: %s)", response, type(response))
            logger.error("Order params were: %s", order_params)
            return {"error": f"Unexpected response type: {type(response)}", "status": "error"}
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
        try:
            def is_success(res):
                # Handle case where result might be an Exception object
                if isinstance(res, Exception):
                    return False
                return isinstance(res, dict) and res.get("status") == "COMPLETE"

            buy_ok = is_success(summary["buy"]["result"])
            sell_ok = is_success(summary["sell"]["result"])

            # Extract execution details safely
            buy_result = summary["buy"]["result"]
            sell_result = summary["sell"]["result"]
            
            # Handle Exception objects from gather()
            if isinstance(buy_result, Exception):
                logger.error("Buy order raised exception: %s", buy_result)
                buy_result = {"error": str(buy_result), "status": "error"}
                summary["buy"]["result"] = buy_result
                
            if isinstance(sell_result, Exception):
                logger.error("Sell order raised exception: %s", sell_result)
                sell_result = {"error": str(sell_result), "status": "error"}
                summary["sell"]["result"] = sell_result
            
            buy_order_id = buy_result.get("order_id", "N/A") if isinstance(buy_result, dict) else "N/A"
            sell_order_id = sell_result.get("order_id", "N/A") if isinstance(sell_result, dict) else "N/A"
            buy_price = buy_result.get("price") if isinstance(buy_result, dict) else None
            sell_price = sell_result.get("price") if isinstance(sell_result, dict) else None
            
            buy_exchange = summary["buy"]["leg"].exchange
            sell_exchange = summary["sell"]["leg"].exchange
            
            if buy_ok and sell_ok:
                # Calculate actual profit
                actual_profit = None
                if buy_price and sell_price:
                    actual_profit = (sell_price - buy_price) * summary["buy"]["leg"].quantity
                
                logger.info(
                    "✅ Trade EXECUTED: %s | Spread=₹%.2f | BUY: %s %s @ ₹%s (id=%s) | SELL: %s %s @ ₹%s (id=%s) | Profit=₹%s",
                    symbol,
                    spread,
                    buy_exchange,
                    summary["buy"]["leg"].side,
                    buy_price if buy_price else "N/A",
                    buy_order_id,
                    sell_exchange,
                    summary["sell"]["leg"].side,
                    sell_price if sell_price else "N/A",
                    sell_order_id,
                    f"{actual_profit:.2f}" if actual_profit else "N/A",
                )
                self.safety.record_trade(symbol, spread, True)
                self.safety.register_close(symbol)
                return
            
            # Log partial or failed trades
            buy_status = buy_result.get("status", "ERROR") if isinstance(buy_result, dict) else "ERROR"
            sell_status = sell_result.get("status", "ERROR") if isinstance(sell_result, dict) else "ERROR"
            logger.warning(
                "⚠️ Trade INCOMPLETE: %s | Spread=₹%.2f | BUY: %s (id=%s, status=%s, price=%s) | SELL: %s (id=%s, status=%s, price=%s)",
                symbol,
                spread,
                buy_exchange,
                buy_order_id,
                buy_status,
                buy_price if buy_price else "N/A",
                sell_exchange,
                sell_order_id,
                sell_status,
                sell_price if sell_price else "N/A",
            )
            await self._failsafe(symbol, summary)
            self.safety.record_trade(symbol, spread, False)
            self.safety.register_close(symbol)
        except Exception as exc:
            logger.exception("CRITICAL: Error in _post_execute for %s: %s", symbol, exc)
            # Still register close to prevent position leak
            try:
                self.safety.register_close(symbol)
            except:
                pass

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

