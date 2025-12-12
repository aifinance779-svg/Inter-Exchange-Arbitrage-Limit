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
        

    def _validate_limit_price(self, price: float, market_price: float, side: str) -> bool:
        """
        Validate that limit price is reasonable.
        For BUY: limit should be >= market ask (we're willing to pay more)
        For SELL: limit should be <= market bid (we're willing to accept less)
        """
        if side == "BUY":
            if price < market_price:
                logger.warning("BUY limit price ₹%.2f is below market ask ₹%.2f", price, market_price)
                return False
        else:  # SELL
            if price > market_price:
                logger.warning("SELL limit price ₹%.2f is above market bid ₹%.2f", price, market_price)
                return False
        return True

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
            if leg.order_type == "LIMIT":
                if leg.price <= 0:
                    logger.error("LIMIT order requires valid price > 0, got: %s", leg.price)
                    return {"error": "Invalid limit price", "status": "error"}
                order_params["price"] = str(round(leg.price, 2))  # Round to 2 decimal places
                logger.debug("Placing LIMIT order: %s %s %s @ ₹%.2f", 
                            leg.exchange, leg.side, leg.symbol, leg.price)
            
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
                        "Order placed %s %s %s qty=%s %s id=%s",
                        leg.exchange,
                        leg.side,
                        leg.symbol,
                        leg.quantity,
                        f"@ ₹{leg.price:.2f}" if leg.order_type == "LIMIT" else "(MARKET)",
                        order_id,
                    )
                    # Wait for order completion (pass IOC flag)
                    is_ioc = leg.validity == "IOC"
                    status = self._wait_for_completion(order_id, timeout=3.0, is_ioc=is_ioc)
                    
                    # Get detailed order information including filled quantity
                    order_details = self._get_order_details(order_id)
                    execution_price = order_details.get("price")
                    filled_qty = order_details.get("filled_qty", 0)
                    requested_qty = order_details.get("requested_qty", leg.quantity)
                    
                    # Check for partial fill
                    if status == "COMPLETE" and filled_qty > 0 and filled_qty != requested_qty:
                        logger.warning(
                            "⚠️ PARTIAL FILL DETECTED: %s %s %s - Requested: %s, Filled: %s",
                            leg.exchange, leg.side, leg.symbol, requested_qty, filled_qty
                        )
                        return {
                            "order_id": order_id,
                            "status": "PARTIAL",
                            "price": execution_price,
                            "filled_qty": filled_qty,
                            "requested_qty": requested_qty,
                        }
                    
                    # Verify full fill if status is COMPLETE
                    if status == "COMPLETE" and filled_qty > 0:
                        if filled_qty != leg.quantity:
                            logger.warning(
                                "Order %s marked COMPLETE but filled_qty (%s) != requested_qty (%s)",
                                order_id, filled_qty, leg.quantity
                            )
                    
                    return {
                        "order_id": order_id,
                        "status": status,
                        "price": execution_price,
                        "filled_qty": filled_qty if filled_qty > 0 else leg.quantity,  # Default to requested if not available
                        "requested_qty": leg.quantity,
                    }
                else:
                    # Non-numeric string - likely an error message
                    logger.error("Order placement returned error string: %s", response)
                    logger.error("Order params were: %s", order_params)
                    return {"error": response, "status": "error"}
            
            # Handle dict response (some API versions return dict)
            if isinstance(response, dict):
                if response.get("status") and response.get("data"):
                    order_id = response["data"].get("orderid")
                    # Wait for order completion (pass IOC flag)
                    is_ioc = leg.validity == "IOC"
                    status = self._wait_for_completion(order_id, timeout=3.0, is_ioc=is_ioc)
                    
                    # Get detailed order information including filled quantity
                    order_details = self._get_order_details(order_id)
                    execution_price = order_details.get("price")
                    filled_qty = order_details.get("filled_qty", 0)
                    requested_qty = order_details.get("requested_qty", leg.quantity)
                    
                    # Check for partial fill
                    if status == "COMPLETE" and filled_qty > 0 and filled_qty != requested_qty:
                        logger.warning(
                            "⚠️ PARTIAL FILL DETECTED: %s %s %s - Requested: %s, Filled: %s",
                            leg.exchange, leg.side, leg.symbol, requested_qty, filled_qty
                        )
                        return {
                            "order_id": order_id,
                            "status": "PARTIAL",
                            "price": execution_price,
                            "filled_qty": filled_qty,
                            "requested_qty": requested_qty,
                        }
                    
                    # Verify full fill if status is COMPLETE
                    if status == "COMPLETE" and filled_qty > 0:
                        if filled_qty != leg.quantity:
                            logger.warning(
                                "Order %s marked COMPLETE but filled_qty (%s) != requested_qty (%s)",
                                order_id, filled_qty, leg.quantity
                            )
                    
                    logger.info(
                        "Order placed %s %s %s qty=%s %s id=%s price=%s",
                        leg.exchange,
                        leg.side,
                        leg.symbol,
                        leg.quantity,
                        f"@ ₹{leg.price:.2f}" if leg.order_type == "LIMIT" else "(MARKET)",
                        order_id,
                        execution_price if execution_price else "N/A",
                    )
                    return {
                        "order_id": order_id,
                        "status": status,
                        "price": execution_price,
                        "filled_qty": filled_qty if filled_qty > 0 else leg.quantity,  # Default to requested if not available
                        "requested_qty": leg.quantity,
                    }
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

    def _get_order_details(self, order_id: str) -> Dict:
        """
        Get detailed order information including filled quantity and status.
        Returns dict with: status, filled_qty, requested_qty, price
        """
        try:
            order_book = self.smart_api.orderBook()
            if order_book and isinstance(order_book, dict) and order_book.get("status") and order_book.get("data"):
                for order in order_book["data"]:
                    if str(order.get("orderid")) == str(order_id):
                        # Try multiple field names for filled quantity (API variations)
                        filled_qty = (
                            order.get("filledshares") or
                            order.get("tradedqty") or
                            order.get("filledquantity") or
                            order.get("filledqty") or
                            0
                        )
                        # Convert to int if it's a string
                        if isinstance(filled_qty, str):
                            try:
                                filled_qty = int(float(filled_qty))
                            except (ValueError, TypeError):
                                filled_qty = 0
                        
                        requested_qty = order.get("quantity") or order.get("orderquantity") or 0
                        if isinstance(requested_qty, str):
                            try:
                                requested_qty = int(float(requested_qty))
                            except (ValueError, TypeError):
                                requested_qty = 0
                        
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
                        
                        return {
                            "status": mapped_status,
                            "filled_qty": filled_qty,
                            "requested_qty": requested_qty,
                            "price": order.get("averageprice") or order.get("price"),
                            "variety": order.get("variety", "NORMAL"),
                        }
        except Exception as e:
            logger.debug("Could not fetch order details for %s: %s", order_id, e)
        return {"status": "UNKNOWN", "filled_qty": 0, "requested_qty": 0, "price": None, "variety": "NORMAL"}

    def _cancel_order(self, order_id: str, variety: str = "NORMAL") -> bool:
        """
        Cancel an unfilled order.
        Returns True if cancellation was successful, False otherwise.
        """
        try:
            self._ensure_authenticated()
            # Angel One cancelOrder API
            response = self.smart_api.cancelOrder(
                orderid=order_id,
                variety=variety
            )
            
            if isinstance(response, dict):
                if response.get("status") and response.get("data"):
                    logger.info("Order %s cancelled successfully", order_id)
                    return True
                else:
                    error_msg = response.get("message", "Unknown error")
                    logger.warning("Failed to cancel order %s: %s", order_id, error_msg)
                    return False
            elif isinstance(response, str):
                # Some API versions return string
                if "success" in response.lower() or "cancelled" in response.lower():
                    logger.info("Order %s cancelled successfully", order_id)
                    return True
                else:
                    logger.warning("Failed to cancel order %s: %s", order_id, response)
                    return False
            else:
                logger.warning("Unexpected response type when cancelling order %s: %s", order_id, type(response))
                return False
        except Exception as exc:
            logger.exception("Error cancelling order %s: %s", order_id, exc)
            return False

    def _wait_for_completion(self, order_id: str, timeout: float = 3.0, is_ioc: bool = True) -> str:
        """
        Wait for order completion with enhanced IOC handling.
        For IOC orders, verifies cancellation if still pending after timeout.
        """
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
        
        # Timeout reached - check final status
        final_details = self._get_order_details(order_id)
        final_status = final_details.get("status", "PENDING")
        
        # For IOC orders, verify cancellation
        if is_ioc and final_status in {"PENDING", "OPEN"}:
            logger.warning(
                "IOC order %s still %s after %.1fs timeout - exchange should auto-cancel, verifying...",
                order_id, final_status, timeout
            )
            # Wait a bit more for exchange to process cancellation
            time.sleep(0.5)
            final_details = self._get_order_details(order_id)
            final_status = final_details.get("status", "PENDING")
            
            # If still pending/open, explicitly cancel
            if final_status in {"PENDING", "OPEN"}:
                variety = final_details.get("variety", "NORMAL")
                logger.warning("IOC order %s still %s - attempting explicit cancellation", order_id, final_status)
                cancelled = self._cancel_order(order_id, variety)
                if cancelled:
                    return "CANCELLED"
                else:
                    logger.error("Failed to cancel IOC order %s - may remain pending", order_id)
                    return "PENDING"
        
        return final_status

    async def _post_execute(self, symbol: str, summary: Dict, spread: float):
        try:
            def is_success(res):
                # Handle case where result might be an Exception object
                if isinstance(res, Exception):
                    return False
                if not isinstance(res, dict):
                    return False
                status = res.get("status")
                # COMPLETE is success, PARTIAL needs special handling
                return status == "COMPLETE"
            
            def is_partial(res):
                """Check if order had partial fill."""
                if not isinstance(res, dict):
                    return False
                return res.get("status") == "PARTIAL"

            buy_ok = is_success(summary["buy"]["result"])
            sell_ok = is_success(summary["sell"]["result"])
            buy_partial = is_partial(summary["buy"]["result"])
            sell_partial = is_partial(summary["sell"]["result"])

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
            buy_filled_qty = buy_result.get("filled_qty", summary["buy"]["leg"].quantity) if isinstance(buy_result, dict) else 0
            sell_filled_qty = sell_result.get("filled_qty", summary["sell"]["leg"].quantity) if isinstance(sell_result, dict) else 0
            buy_requested_qty = buy_result.get("requested_qty", summary["buy"]["leg"].quantity) if isinstance(buy_result, dict) else summary["buy"]["leg"].quantity
            sell_requested_qty = sell_result.get("requested_qty", summary["sell"]["leg"].quantity) if isinstance(sell_result, dict) else summary["sell"]["leg"].quantity
            
            buy_exchange = summary["buy"]["leg"].exchange
            sell_exchange = summary["sell"]["leg"].exchange

            # --- Slippage check -------------------------------------------------
            def _slip(actual: float | None, expected: float | None) -> float:
                if actual is None or expected is None:
                    return 0.0
                try:
                    return abs(float(actual) - float(expected))
                except Exception:
                    return 0.0

            buy_expected = summary["buy"]["leg"].price if summary["buy"]["leg"].order_type == "LIMIT" else buy_price
            sell_expected = summary["sell"]["leg"].price if summary["sell"]["leg"].order_type == "LIMIT" else sell_price
            buy_slip = _slip(buy_price, buy_expected)
            sell_slip = _slip(sell_price, sell_expected)
            max_slip = settings.risk.max_slippage_per_leg

            slippage_breach = (buy_slip > max_slip) or (sell_slip > max_slip)
            if slippage_breach:
                logger.error(
                    "🚨 Slippage breach: %s | BUY slip=₹%.2f (expected=₹%s, got=₹%s) | SELL slip=₹%.2f (expected=₹%s, got=₹%s) | limit=₹%.2f",
                    symbol,
                    buy_slip,
                    f"{buy_expected:.2f}" if buy_expected else "N/A",
                    f"{buy_price:.2f}" if buy_price else "N/A",
                    sell_slip,
                    f"{sell_expected:.2f}" if sell_expected else "N/A",
                    f"{sell_price:.2f}" if sell_price else "N/A",
                    max_slip,
                )
                # Treat as failure path to allow failsafe/metrics handling
                buy_ok = False
                sell_ok = False
            
            # Check for partial fills
            has_partial_fill = buy_partial or sell_partial
            
            if buy_ok and sell_ok and not has_partial_fill:
                # Both orders fully filled - success
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
            
            # Handle partial fills or failures
            buy_status = buy_result.get("status", "ERROR") if isinstance(buy_result, dict) else "ERROR"
            sell_status = sell_result.get("status", "ERROR") if isinstance(sell_result, dict) else "ERROR"
            
            if has_partial_fill:
                logger.error(
                    "🚨 PARTIAL FILL DETECTED: %s | Spread=₹%.2f | BUY: %s (id=%s, status=%s, filled=%s/%s, price=%s) | SELL: %s (id=%s, status=%s, filled=%s/%s, price=%s)",
                    symbol,
                    spread,
                    buy_exchange,
                    buy_order_id,
                    buy_status,
                    buy_filled_qty,
                    buy_requested_qty,
                    buy_price if buy_price else "N/A",
                    sell_exchange,
                    sell_order_id,
                    sell_status,
                    sell_filled_qty,
                    sell_requested_qty,
                    sell_price if sell_price else "N/A",
                )
            else:
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
        logger.error("Failsafe triggered for %s", symbol)
        legs_to_close = []
        buy_res = summary["buy"]["result"]
        sell_res = summary["sell"]["result"]
        
        # Handle buy leg - square off if filled (fully or partially)
        if isinstance(buy_res, dict):
            buy_status = buy_res.get("status")
            # Square off if COMPLETE or PARTIAL
            if buy_status in {"COMPLETE", "PARTIAL"}:
                # Use filled quantity if available, otherwise requested quantity
                filled_qty = buy_res.get("filled_qty", 0)
                requested_qty = buy_res.get("requested_qty", summary["buy"]["leg"].quantity)
                # Use filled quantity for square-off, fallback to requested if not available
                qty_to_close = filled_qty if filled_qty > 0 else requested_qty
                
                if qty_to_close > 0:
                    logger.info(
                        "Failsafe: Squaring off BUY leg - %s %s qty=%s (filled=%s, requested=%s)",
                        summary["buy"]["leg"].exchange, symbol, qty_to_close, filled_qty, requested_qty
                    )
                    legs_to_close.append(
                        OrderLeg(
                            exchange=summary["buy"]["leg"].exchange,
                            symbol=symbol,
                            side="SELL" if summary["buy"]["leg"].side == "BUY" else "BUY",
                            quantity=qty_to_close,
                            order_type="MARKET",  # Use MARKET for quick square-off
                            validity="IOC",
                        )
                    )
        
        # Handle sell leg - square off if filled (fully or partially)
        if isinstance(sell_res, dict):
            sell_status = sell_res.get("status")
            # Square off if COMPLETE or PARTIAL
            if sell_status in {"COMPLETE", "PARTIAL"}:
                # Use filled quantity if available, otherwise requested quantity
                filled_qty = sell_res.get("filled_qty", 0)
                requested_qty = sell_res.get("requested_qty", summary["sell"]["leg"].quantity)
                # Use filled quantity for square-off, fallback to requested if not available
                qty_to_close = filled_qty if filled_qty > 0 else requested_qty
                
                if qty_to_close > 0:
                    logger.info(
                        "Failsafe: Squaring off SELL leg - %s %s qty=%s (filled=%s, requested=%s)",
                        summary["sell"]["leg"].exchange, symbol, qty_to_close, filled_qty, requested_qty
                    )
                    legs_to_close.append(
                        OrderLeg(
                            exchange=summary["sell"]["leg"].exchange,
                            symbol=symbol,
                            side="BUY" if summary["sell"]["leg"].side == "SELL" else "SELL",
                            quantity=qty_to_close,
                            order_type="MARKET",  # Use MARKET for quick square-off
                            validity="IOC",
                        )
                    )

        if legs_to_close:
            logger.info("Failsafe: Placing %d square-off order(s) for %s", len(legs_to_close), symbol)
            loop = asyncio.get_event_loop()
            results = await asyncio.gather(
                *[
                    loop.run_in_executor(self.executor, self._place_order, leg)
                    for leg in legs_to_close
                ],
                return_exceptions=True
            )
            
            # Log failsafe results
            for i, result in enumerate(results):
                leg = legs_to_close[i]
                if isinstance(result, Exception):
                    logger.error("Failsafe order failed for %s %s %s: %s", leg.exchange, leg.side, leg.symbol, result)
                elif isinstance(result, dict):
                    status = result.get("status", "UNKNOWN")
                    if status == "COMPLETE":
                        logger.info("Failsafe order executed: %s %s %s qty=%s", leg.exchange, leg.side, leg.symbol, leg.quantity)
                    else:
                        logger.warning("Failsafe order incomplete: %s %s %s status=%s", leg.exchange, leg.side, leg.symbol, status)
        else:
            logger.warning("Failsafe: No filled legs to square off for %s", symbol)

