# Instrument Token Setup Guide

## Overview

The arbitrage bot needs instrument tokens to subscribe to market data via WebSocket. Each symbol needs tokens for both NSE and BSE exchanges.

## How to Get Instrument Tokens

### Method 1: Using Angel One Platform

1. Log in to [Angel One](https://www.angelone.in/)
2. Go to Market Watch or Instrument Search
3. Search for your symbol (e.g., "TATAMOTORS")
4. Note the instrument token shown in the URL or instrument details
5. Repeat for both NSE and BSE exchanges

### Method 2: Using Angel One SmartAPI

You can use the SmartAPI to fetch instrument master data:

```python
from SmartApi.smartConnect import SmartConnect
import pyotp

# Authenticate
smart_api = SmartConnect(api_key="your_api_key")
totp = pyotp.TOTP("your_totp_secret").now()
session = smart_api.generateSession("client_id", "mpin", totp)

# Get master data
master_data = smart_api.getMasterData("NSE")  # or "BSE"
# Search for your symbol in master_data
```

### Method 3: Manual Token Mapping

Edit `src/core/data_feed.py` and update the `_manual_token_lookup()` method:

```python
def _manual_token_lookup(self, symbols: List[str]) -> Dict[str, str]:
    manual_map = {
        "TATAMOTORS_NSE": "NSE|884737",
        "TATAMOTORS_BSE": "BSE|500570",
        "ICICIBANK_NSE": "NSE|1270529",
        "ICICIBANK_BSE": "BSE|532174",
        # Add more mappings here
    }
    # ... rest of the code
```

## Token Format

Tokens should be in the format: `"EXCHANGE|TOKEN"`

Examples:
- `"NSE|884737"` - TATAMOTORS on NSE
- `"BSE|500570"` - TATAMOTORS on BSE

## Common Instrument Tokens

Here are some common tokens (verify these are current):

| Symbol | NSE Token | BSE Token |
|--------|-----------|----------|
| TATAMOTORS | 884737 | 500570 |
| ICICIBANK | 1270529 | 532174 |
| HDFCBANK | 133275 | 500180 |
| SBIN | 3045 | 500112 |
| INFY | 408065 | 500209 |
| TCS | 2953217 | 532540 |

**Note**: These tokens may change. Always verify current tokens from Angel One platform.

## Next Steps

1. Get tokens for all symbols in your watchlist
2. Update `_manual_token_lookup()` in `src/core/data_feed.py`
3. Restart the bot
4. Verify WebSocket receives data (check logs)

## Troubleshooting

- **No data received**: Check that tokens are correct and format is "EXCHANGE|TOKEN"
- **WebSocket errors**: Verify feed_token is set correctly after authentication
- **Token not found**: Ensure you're using the correct exchange (NSE vs BSE)






