# NSE ↔ BSE Arbitrage Trading Bot

High-frequency personal trading bot that scans NSE and BSE quotes for configured symbols, detects actionable spreads, validates liquidity, and executes simultaneous hedge orders through the Angel One SmartAPI.

> ⚠️ **Disclaimer**: This project is for educational purposes only. Exchanges, brokers, and regulators may impose additional compliance requirements. Trade responsibly and at your own risk.

## Features

- Angel One SmartAPI WebSocket market data (LTP, best bid/ask, depth snapshots).
- Async monitoring loop (100‑300 ms cadence) with auto-reconnect.
- Spread detector + liquidity gate + risk guardrails.
- Concurrent dual-leg order execution (IOC/MARKET) with fail-safe square-offs.
- Order state tracker with retry + slippage logging.
- Terminal dashboard (Rich) plus hooks for Streamlit or custom UI extensions.
- Configuration-driven symbol universe, thresholds, and risk limits.
- Optional backtest mode to replay historical ticks/spreads.

## Project Layout

```
src/
  config/
    settings.py      # thresholds, risk, env loader
    symbols.py       # default watchlist
  core/
    auth.py          # Angel One authentication
    data_feed.py     # WebSocket manager + tick fan-out
    spread_detector.py
    decision_engine.py
    order_executor.py
    safety.py
    logger.py
  ui/
    terminal_dashboard.py
  main.py
```

## Getting Started

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   or use `poetry`/`pipenv` per preference. Required packages include:
   `smartapi-python`, `pyotp`, `logzero`, `websocket-client`, `rich`, `python-dotenv`.

2. **Environment variables**

   Create a `.env` file (or set system env vars):
   ```
   ANGEL_ONE_API_KEY=your_api_key
   ANGEL_ONE_CLIENT_ID=your_client_id
   ANGEL_ONE_MPIN=your_mpin
   ANGEL_ONE_TOTP_SECRET=your_totp_secret
   ```
   
   **Note**: 
   - The bot will automatically authenticate using TOTP (Time-based One-Time Password) on startup.
   - Angel One now requires MPIN (Mobile PIN) instead of password for authentication.
   - Make sure your TOTP secret and MPIN are configured correctly.

3. **Configure settings**

   Adjust `src/config/settings.py` for thresholds, risk, and UI cadence. Update `src/config/symbols.py` to change the default watchlist or per-symbol quantities.

4. **Run the bot**
   ```bash
   python -m src.main
   ```

   Use `--backtest path/to/data.csv` to enter offline test mode if you implement a backtest dataset.

5. **Optional: Web Dashboard**

   For a visual web-based dashboard with charts:
   ```bash
   # Install web dashboard dependencies
   pip install streamlit plotly pandas
   
   # Run web dashboard (in a separate terminal)
   streamlit run src/ui/web_dashboard.py
   # Or use the launcher:
   python run_web_dashboard.py
   ```
   
   Then open your browser to `http://localhost:8501`

## Notes

- The Angel One SmartAPI requires proper authentication using API key, client ID, password, and TOTP secret. The bot handles authentication automatically on startup.
- Session tokens may need to be refreshed periodically; the bot includes token refresh functionality.
- The provided code focuses on structure and safety scaffolding. You must:
  - Implement proper instrument token resolution (currently placeholder)
  - Configure correct exchange codes and symbol formats for NSE/BSE
  - Verify order types, product codes, and validity options match your Angel One account
  - Test with paper trading or minimal size before scaling
- Always test thoroughly in a safe environment before live trading.

