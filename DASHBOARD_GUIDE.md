# Dashboard Guide

The arbitrage bot comes with two dashboard options:

## 1. Terminal Dashboard (Default)

The enhanced terminal dashboard runs automatically when you start the bot. It features:

- **Color-coded spreads**: Green for profitable, yellow for approaching threshold
- **Real-time updates**: Refreshes 4 times per second
- **Statistics panel**: Shows runtime, signals, and trade statistics
- **Sorted by opportunity**: Best spreads shown first

### Usage

Just run the bot normally:
```bash
python -m src.main
```

The dashboard will appear in your terminal automatically.

## 2. Web Dashboard (Streamlit)

A beautiful web-based dashboard with charts and visualizations.

### Setup

1. Install Streamlit (if not already installed):
```bash
pip install streamlit plotly pandas
```

2. Run the web dashboard:
```bash
streamlit run src/ui/web_dashboard.py
```

3. Open your browser to the URL shown (usually `http://localhost:8501`)

### Features

- **Real-time data table**: All symbols with prices and spreads
- **Interactive charts**: Bar charts for spreads and percentages
- **Statistics metrics**: Total signals, trades, runtime
- **Configuration panel**: View current bot settings
- **Auto-refresh**: Updates every second

### Running Both

You can run both dashboards simultaneously:

1. Terminal: Run `python -m src.main` (terminal dashboard auto-starts)
2. Web: In another terminal, run `streamlit run src/ui/web_dashboard.py`

The web dashboard reads from the same data source as the terminal dashboard.

## Dashboard Data

Both dashboards show:
- **Symbol**: Stock symbol
- **NSE Price**: Last traded price on NSE
- **BSE Price**: Last traded price on BSE
- **Spread**: Absolute price difference
- **Spread %**: Percentage difference
- **Quantity**: Trading quantity configured
- **Signal**: Trading signal (e.g., "NSE->BSE")
- **Status**: Order status (OK, PENDING, FAIL, BLOCKED)

## Troubleshooting

### Terminal Dashboard Not Showing

- Check that `ENABLE_DASHBOARD=1` in your `.env` file
- Make sure your terminal supports Rich library (most modern terminals do)

### Web Dashboard Not Updating

- Ensure the bot is running (`python -m src.main`)
- Check that tokens are configured correctly
- Verify market data is being received (check logs)

### No Data Showing

- Verify instrument tokens are configured (see `TOKEN_SETUP.md`)
- Check that market is open (9:15 AM - 3:30 PM IST)
- Review logs for WebSocket connection errors

## Customization

### Terminal Dashboard Colors

Edit `src/ui/terminal_dashboard.py` to customize colors in the `_get_spread_color()` method.

### Web Dashboard Layout

Edit `src/ui/web_dashboard.py` to customize the Streamlit layout, add more charts, or modify the display.






