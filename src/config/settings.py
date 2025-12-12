"""
Centralized runtime configuration for the NSE ↔ BSE arbitrage bot.

The module exposes a `Settings` dataclass with typed attributes so
other modules can rely on strongly defined values. Environment variables
override defaults and should be stored securely (e.g., via `.env`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
import os

load_dotenv()


def _env(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


@dataclass
class RiskLimits:
    max_trades_per_minute: int = 4
    max_open_exposure: int = 1  # concurrent symbol pairs
    max_failed_fills: int = 2   # consecutive failures before auto-stop
    max_slippage_per_leg: float = 0.25


def _parse_symbols_env() -> List[str]:
    """Parse SYMBOLS environment variable into a list."""
    symbols_str = os.getenv("SYMBOLS", "").strip()
    if not symbols_str:
        return []
    # Support both comma and space separated
    symbols = [s.strip().upper() for s in symbols_str.replace(",", " ").split()]
    return [s for s in symbols if s]  # Remove empty strings

@dataclass
class Settings:
    # Angel One SmartAPI credentials
    api_key: str = field(default_factory=lambda: _env("ANGEL_ONE_API_KEY"))
    client_id: str = field(default_factory=lambda: _env("ANGEL_ONE_CLIENT_ID"))
    mpin: str = field(default_factory=lambda: _env("ANGEL_ONE_MPIN"))  # MPIN instead of password
    totp_secret: str = field(default_factory=lambda: _env("ANGEL_ONE_TOTP_SECRET"))
    # These are set after authentication
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    feed_token: Optional[str] = None

    min_spread: float = float(os.getenv("MIN_SPREAD", 1))
    poll_interval_ms: int = int(os.getenv("POLL_INTERVAL_MS", 40))
    depth_levels: int = int(os.getenv("DEPTH_LEVELS", 5))

    # Limit order buffer settings (Strategy 1)
    limit_order_buy_buffer: float = float(os.getenv("LIMIT_ORDER_BUY_BUFFER", "0.10"))  # ₹0.10 above ask
    limit_order_sell_buffer: float = float(os.getenv("LIMIT_ORDER_SELL_BUFFER", "0.10"))  # ₹0.10 below bid
    use_limit_orders: bool = os.getenv("USE_LIMIT_ORDERS", "1") == "1"  # Enable/disable limit orders

    trading_start: time = time(9, 15)
    trading_end: time = time(15, 30)

    default_quantity: int = int(os.getenv("DEFAULT_QUANTITY", 1))
    per_symbol_qty: Dict[str, int] = field(default_factory=dict)

    log_dir: Path = Path(os.getenv("LOG_DIR", "logs"))
    enable_dashboard: bool = os.getenv("ENABLE_DASHBOARD", "1") == "1"
    backtest_file: Optional[Path] = (
        Path(os.getenv("BACKTEST_FILE")) if os.getenv("BACKTEST_FILE") else None
    )

    risk: RiskLimits = field(default_factory=RiskLimits)
    symbols: List[str] = field(default_factory=_parse_symbols_env)

    def quantity_for(self, symbol: str) -> int:
        return self.per_symbol_qty.get(symbol, self.default_quantity)


settings = Settings()
# `settings` is imported and reused across the codebase so we only
# resolve environment variables once at startup.

