from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict


WATCHLIST = {
    "RELIANCE",
    "WIPRO",
    "TATASTEEL",
    "SBIN",
    "TATAMOTORS",
    "ITC",
    "ONGC",
    "JIOFIN",
    "NTPC",
    "ICICIBANK",
    "HDFCBANK",
    "INFY",
    "TCS",
    "POWERGRID",
    "BPCL",
}

DEFAULT_TOKEN_MAP = {
    "RELIANCE_NSE": {"token": "2885", "tradingsymbol": "RELIANCE-EQ"},
    "RELIANCE_BSE": {"token": "500325", "tradingsymbol": "500325"},
    "WIPRO_NSE": {"token": "3787", "tradingsymbol": "WIPRO-EQ"},
    "WIPRO_BSE": {"token": "507685", "tradingsymbol": "507685"},
    "TATASTEEL_NSE": {"token": "3499", "tradingsymbol": "TATASTEEL-EQ"},
    "TATASTEEL_BSE": {"token": "500470", "tradingsymbol": "500470"},
    "HDFCBANK_NSE": {"token": "133275", "tradingsymbol": "HDFCBANK-EQ"},
    "HDFCBANK_BSE": {"token": "500180", "tradingsymbol": "500180"},


    "SBIN_NSE":{"token": "3045",    "tradingsymbol": "SBIN-EQ"},
    "SBIN_BSE":{"token": "500112",  "tradingsymbol": "500112"},

    "TATAMOTORS_NSE": {"token": "3456",    "tradingsymbol": "TATAMOTORS-EQ"},
    "TATAMOTORS_BSE": {"token": "500570",  "tradingsymbol": "500570"},

    "ICICIBANK_NSE":  {"token": "4963",    "tradingsymbol": "ICICIBANK-EQ"},
    "ICICIBANK_BSE":  {"token": "532174",  "tradingsymbol": "532174"},

    
    

    "INFY_NSE":       {"token": "1594",    "tradingsymbol": "INFY-EQ"},
    "INFY_BSE":       {"token": "500209",  "tradingsymbol": "500209"},

    "TCS_NSE":        {"token": "11536",   "tradingsymbol": "TCS-EQ"},
    "TCS_BSE":        {"token": "532540",  "tradingsymbol": "532540"},

    "POWERGRID_NSE": {"token": "18096", "tradingsymbol": "POWERGRID-EQ"},
    "POWERGRID_BSE": {"token": "532898", "tradingsymbol": "532898"},

    "BPCL_NSE":       {"token": "526",     "tradingsymbol": "BPCL-EQ"},
    "BPCL_BSE":       {"token": "500547",  "tradingsymbol": "500547"},
}


TOKEN_MAP: Dict[str, Dict[str, str]] = {}


def _base_symbol(trading_symbol: str) -> str:
    trading_symbol = trading_symbol.upper()
    if "-" in trading_symbol:
        return trading_symbol.split("-", 1)[0]
    return trading_symbol


def _load_from_csv(csv_path: Path) -> None:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            exch = (
                row.get("exch_seg")  # NSE / BSE
                or row.get("exchange")
                or row.get("exch")
                or ""
            ).upper()
            if exch not in {"NSE", "BSE"}:
                continue

            token = row.get("token") or row.get("symboltoken")
            # Use 'symbol' from OpenAPIScripMaster (e.g. SBIN-EQ or SBIN)
            trading_symbol = row.get("symbol") or row.get("trading_symbol") or row.get("tradingsymbol")
            if not token or not trading_symbol:
                continue

            trading_symbol = trading_symbol.upper()
            base = _base_symbol(trading_symbol)  # SBIN-EQ -> SBIN, SBIN -> SBIN
            if base not in WATCHLIST:
                continue

            key = f"{base}_{exch}"
            TOKEN_MAP[key] = {"token": token, "tradingsymbol": trading_symbol}


def load_tokens() -> None:
    csv_path = Path(
        r"C:\Users\prath\.smartapi\OpenAPIScripMaster.csv"
    )

    if not csv_path.exists():
        print(f"Instrument file missing: {csv_path}. Using fallback tokens.")
        TOKEN_MAP.update(DEFAULT_TOKEN_MAP)
        return

    print(f"Loading tokens from: {csv_path}")
    try:
        _load_from_csv(csv_path)
    except KeyError as exc:
        print(f"Instrument file missing expected column {exc}. Using fallback tokens.")
        TOKEN_MAP.clear()
        TOKEN_MAP.update(DEFAULT_TOKEN_MAP)
        return

    # If CSV did not cover all symbols, fill the gaps with defaults
    missing = [sym for sym in WATCHLIST for exch in ("NSE", "BSE") if f"{sym}_{exch}" not in TOKEN_MAP]
    if missing:
        print(f"Instrument file incomplete; adding fallback tokens for: {missing}")
        for key, value in DEFAULT_TOKEN_MAP.items():
            TOKEN_MAP.setdefault(key, value)


load_tokens()
