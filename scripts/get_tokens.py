"""
Helper script to fetch and display instrument tokens from Angel One.

This script helps you get the correct tokens for your symbols on both NSE and BSE.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import pyotp
from SmartApi.smartConnect import SmartConnect

load_dotenv()


def get_tokens(symbols):
    """Fetch instrument tokens for given symbols."""
    api_key = os.getenv("ANGEL_ONE_API_KEY")
    client_id = os.getenv("ANGEL_ONE_CLIENT_ID")
    mpin = os.getenv("ANGEL_ONE_MPIN")
    totp_secret = os.getenv("ANGEL_ONE_TOTP_SECRET")
    
    if not all([api_key, client_id, mpin, totp_secret]):
        print("Error: Missing environment variables. Check your .env file.")
        return
    
    # Authenticate
    smart_api = SmartConnect(api_key=api_key)
    totp = pyotp.TOTP(totp_secret).now()
    
    try:
        session = smart_api.generateSession(client_id, mpin, totp)
        if not session or not session.get("status"):
            print(f"Authentication failed: {session.get('message', 'Unknown error') if session else 'No response'}")
            return
        
        print("Authentication successful!\n")
        print("Fetching instrument master data...\n")
        
        # Get master data for NSE
        try:
            nse_master = smart_api.getMasterData("NSE")
            print("✓ NSE master data fetched")
        except Exception as e:
            print(f"✗ Failed to fetch NSE master data: {e}")
            nse_master = None
        
        # Get master data for BSE
        try:
            bse_master = smart_api.getMasterData("BSE")
            print("✓ BSE master data fetched")
        except Exception as e:
            print(f"✗ Failed to fetch BSE master data: {e}")
            bse_master = None
        
        print("\n" + "="*60)
        print("INSTRUMENT TOKENS")
        print("="*60)
        print(f"{'Symbol':<20} {'NSE Token':<15} {'BSE Token':<15}")
        print("-"*60)
        
        token_map = {}
        
        for symbol in symbols:
            nse_token = None
            bse_token = None
            
            # Search in NSE master
            if nse_master:
                nse_token = search_in_master(nse_master, symbol, "NSE")
            
            # Search in BSE master
            if bse_master:
                bse_token = search_in_master(bse_master, symbol, "BSE")
            
            print(f"{symbol:<20} {str(nse_token) if nse_token else 'NOT FOUND':<15} {str(bse_token) if bse_token else 'NOT FOUND':<15}")
            
            if nse_token:
                token_map[f"{symbol}_NSE"] = f"NSE|{nse_token}"
            if bse_token:
                token_map[f"{symbol}_BSE"] = f"BSE|{bse_token}"
        
        print("\n" + "="*60)
        print("PYTHON CODE TO ADD TO _manual_token_lookup():")
        print("="*60)
        print("manual_map = {")
        for key, value in token_map.items():
            print(f'    "{key}": "{value}",')
        print("}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def search_in_master(master_data, symbol, exchange):
    """Search for symbol in master data."""
    if not master_data:
        return None
    
    # Master data structure varies - try different formats
    symbol_upper = symbol.upper()
    
    if isinstance(master_data, list):
        for item in master_data:
            if isinstance(item, dict):
                # Try different key combinations
                item_symbol = item.get('symbol', item.get('tradingsymbol', item.get('name', ''))).upper()
                item_exchange = item.get('exchange', item.get('exch', '')).upper()
                
                if symbol_upper in item_symbol and exchange.upper() in item_exchange:
                    token = item.get('token', item.get('instrumenttoken', item.get('tokenid')))
                    if token:
                        return str(token)
    
    return None


if __name__ == "__main__":
    # Default symbols from the bot
    default_symbols = [
        "TATAMOTORS", "ICICIBANK", "HDFCBANK", "SBIN", 
        "POWERGRID", "INFY","RELIANCE", "TCS", "BPCL", "TATASTEEL"
    ]
    
    # You can also pass symbols as command line arguments
    if len(sys.argv) > 1:
        symbols = sys.argv[1:]
    else:
        symbols = default_symbols
    
    print("Angel One Instrument Token Fetcher")
    print("="*60)
    print(f"Fetching tokens for: {', '.join(symbols)}\n")
    
    get_tokens(symbols)






