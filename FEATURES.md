# Complete Feature List - NSE ↔ BSE Arbitrage Trading Bot

## 🎯 Core Functionality

### 1. **Real-Time Market Data Feed**
- **WebSocket Integration**: Connects to Angel One SmartAPI WebSocket for real-time market data
- **Multi-Exchange Support**: Simultaneously monitors NSE and BSE exchanges
- **Tick Data Processing**: Receives and processes:
  - Last Traded Price (LTP)
  - Best Bid/Ask prices
  - Bid/Ask quantities
  - Market depth (configurable levels, default: 5 levels)
- **Auto-Reconnect**: Automatically reconnects on WebSocket disconnection
- **High-Frequency Updates**: Configurable polling interval (default: 150ms)
- **Backtest Mode**: Replay historical data from CSV files for testing

### 2. **Spread Detection & Analysis**
- **Real-Time Spread Calculation**: Continuously calculates price differences between NSE and BSE
- **Configurable Threshold**: Minimum spread threshold (default: ₹0.35)
- **Spread Percentage**: Calculates both absolute and percentage spreads
- **Direction Detection**: Identifies which exchange is cheaper (BUY side) and which is expensive (SELL side)
- **Liquidity Validation**: Checks market depth to ensure sufficient liquidity before trading

### 3. **Intelligent Trading Decision Engine**
- **Market Hours Enforcement**: Only trades during configured market hours (default: 9:15 AM - 3:30 PM IST)
- **Quote Snapshot Building**: Maintains synchronized NSE and BSE price snapshots
- **Signal Generation**: Creates trading signals when:
  - Spread >= minimum threshold
  - Sufficient liquidity on both exchanges
  - Market is open
- **Telemetry Hooks**: Provides real-time data to dashboards

### 4. **Simultaneous Order Execution**
- **Concurrent Order Placement**: Places BUY and SELL orders simultaneously using asyncio
- **Multi-Threading Support**: Uses ThreadPoolExecutor for parallel order execution
- **Order Types Supported**:
  - MARKET orders
  - LIMIT orders
  - IOC (Immediate or Cancel) orders
  - STOPLOSS orders (with trigger price)
- **Product Types**:
  - INTRADAY (MIS)
  - DELIVERY (CNC)
- **Order Status Tracking**: Monitors order completion with timeout handling

### 5. **Risk Management & Safety Features**

#### Safety Manager (`SafetyManager`)
- **Trade Rate Limiting**: Maximum trades per minute (default: 6)
- **Exposure Limits**: Maximum concurrent open positions (default: 3 symbols)
- **Failed Fill Protection**: Auto-stop after consecutive failures (default: 2)
- **Slippage Control**: Maximum slippage per leg (default: ₹0.25)
- **Position Tracking**: Monitors open and closed positions
- **Trade History**: Records successful and failed trades

#### Risk Controls
- **Pre-Trade Checks**: Validates all risk limits before placing orders
- **Post-Trade Analysis**: Tracks trade outcomes and updates statistics
- **Automatic Blocking**: Prevents trading when risk limits are exceeded

### 6. **Failsafe Mechanisms**
- **One-Leg Failure Handling**: If only one order fills, automatically squares off the other leg
- **Order Status Monitoring**: Continuously polls order status until completion
- **Error Recovery**: Handles API errors, network issues, and order rejections
- **Automatic Square-Off**: Closes open positions when one leg fails

### 7. **Authentication & Session Management**
- **Automatic Authentication**: Handles Angel One SmartAPI authentication on startup
- **TOTP Support**: Time-based One-Time Password (2FA) integration
- **MPIN Authentication**: Supports Angel One's MPIN-based login
- **Token Management**: 
  - Access token storage
  - Refresh token handling
  - Feed token for WebSocket
- **Session Persistence**: Maintains authenticated session throughout bot lifecycle
- **Token Refresh**: Automatic token refresh functionality

### 8. **Comprehensive Logging**
- **Structured Logging**: Organized logging with different log levels
- **File Logging**: Logs saved to `logs/` directory
- **Log Rotation**: Automatic log file rotation
- **Error Tracking**: Detailed exception logging with stack traces
- **Trade Logging**: Records all trades, signals, and order placements
- **Performance Metrics**: Logs timing and execution details

### 9. **Dual Dashboard System**

#### Terminal Dashboard (Rich)
- **Real-Time Display**: Updates 4 times per second
- **Color-Coded Spreads**: 
  - Green: Profitable spreads (>= threshold)
  - Yellow: Approaching threshold (>= 70% of threshold)
  - White: Below threshold
- **Statistics Panel**: Shows:
  - Runtime
  - Total signals generated
  - Successful trades
  - Failed trades
  - Configuration settings
- **Sorted Display**: Best opportunities shown first
- **Spread Metrics**: Shows both absolute (₹) and percentage spreads
- **Status Indicators**: Visual status for each symbol (OK, PENDING, FAIL, BLOCKED)

#### Web Dashboard (Streamlit)
- **Interactive Charts**: 
  - Bar charts for spreads by symbol
  - Spread percentage visualization
- **Real-Time Metrics**: Statistics cards at the top
- **Data Table**: Sortable table with all symbols and prices
- **Configuration Panel**: View and understand bot settings
- **Auto-Refresh**: Updates every second
- **Browser-Based**: Accessible from any device on your network

### 10. **Configuration Management**

#### Environment Variables
- `ANGEL_ONE_API_KEY`: API key for Angel One
- `ANGEL_ONE_CLIENT_ID`: Client ID
- `ANGEL_ONE_MPIN`: Mobile PIN for authentication
- `ANGEL_ONE_TOTP_SECRET`: TOTP secret for 2FA
- `MIN_SPREAD`: Minimum spread threshold (default: 0.35)
- `POLL_INTERVAL_MS`: Data polling interval (default: 150)
- `DEPTH_LEVELS`: Market depth levels (default: 5)
- `DEFAULT_QUANTITY`: Default trading quantity (default: 50)
- `LOG_DIR`: Log directory (default: logs)
- `ENABLE_DASHBOARD`: Enable/disable dashboard (default: 1)
- `BACKTEST_FILE`: Path to backtest CSV file (optional)

#### Runtime Configuration
- **Symbol Watchlist**: Configurable list of symbols to monitor
- **Per-Symbol Quantities**: Different quantities for different symbols
- **Trading Hours**: Customizable market hours
- **Risk Limits**: Adjustable risk parameters

### 11. **Symbol Management**
- **Default Watchlist**: Pre-configured with popular stocks:
  - TATAMOTORS
  - ICICIBANK
  - HDFCBANK
  - SBIN
  - POWERGRID
  - INFY
  - TCS
  - BPCL
- **Custom Symbols**: Easy to add/remove symbols
- **Symbol Metadata**: Per-symbol configuration (quantity, comments)

### 12. **Helper Tools & Utilities**

#### Token Fetcher Script (`scripts/get_tokens.py`)
- **Automatic Token Resolution**: Fetches instrument tokens from Angel One API
- **Master Data Integration**: Uses Angel One instrument master data
- **Code Generation**: Generates Python code for token mappings
- **Multi-Exchange Support**: Fetches tokens for both NSE and BSE

#### Web Dashboard Launcher (`run_web_dashboard.py`)
- **Easy Launch**: Simple script to start web dashboard
- **Port Configuration**: Configurable port (default: 8501)

### 13. **Backtest Capabilities**
- **CSV Replay**: Replay historical market data from CSV files
- **Offline Testing**: Test strategies without live market connection
- **Historical Analysis**: Analyze past spreads and opportunities
- **Data Format Support**: Flexible CSV format for historical data

### 14. **Error Handling & Resilience**
- **Exception Handling**: Comprehensive try-catch blocks throughout
- **Network Resilience**: Handles network errors and timeouts
- **API Error Recovery**: Graceful handling of API errors
- **WebSocket Reconnection**: Automatic reconnection on connection loss
- **Order Retry Logic**: Handles transient order failures

### 15. **Performance Features**
- **Asynchronous Architecture**: Built on asyncio for high performance
- **Non-Blocking Operations**: All I/O operations are non-blocking
- **Efficient Data Structures**: Optimized for low latency
- **Memory Efficient**: Minimal memory footprint

## 📊 Data & Analytics

### Market Data Captured
- Last Traded Price (LTP) for NSE and BSE
- Best Bid Price and Quantity
- Best Ask Price and Quantity
- Market Depth (5 levels by default)
- Timestamp for each tick

### Statistics Tracked
- Total signals generated
- Successful trades count
- Failed trades count
- Runtime duration
- Spread analysis per symbol
- Order execution times

## 🔧 Technical Features

### Architecture
- **Modular Design**: Clean separation of concerns
- **Extensible**: Easy to add new features
- **Type Hints**: Full type annotations for better code quality
- **Documentation**: Comprehensive docstrings

### Code Quality
- **Error Handling**: Robust error handling throughout
- **Logging**: Detailed logging at all levels
- **Configuration**: Centralized configuration management
- **Testing Ready**: Structure supports unit testing

## 🚀 Usage Modes

### 1. Live Trading Mode
- Real-time market data
- Automatic order execution
- Full risk management
- Live dashboards

### 2. Backtest Mode
- Historical data replay
- Strategy testing
- Performance analysis
- No real orders placed

### 3. Monitor Mode
- Data collection only
- No order execution
- Analysis and observation
- Dashboard visualization

## 📈 Trading Workflow

1. **Data Collection**: WebSocket receives real-time ticks from NSE and BSE
2. **Spread Calculation**: Calculates price difference for each symbol
3. **Liquidity Check**: Validates sufficient market depth
4. **Risk Validation**: Checks all risk limits
5. **Signal Generation**: Creates trading signal if conditions met
6. **Order Execution**: Places simultaneous BUY and SELL orders
7. **Status Monitoring**: Tracks order completion
8. **Failsafe Handling**: Squares off if one leg fails
9. **Logging & Reporting**: Records all activities
10. **Dashboard Update**: Updates both terminal and web dashboards

## 🛡️ Safety Features Summary

- ✅ Maximum trades per minute limit
- ✅ Maximum concurrent exposure limit
- ✅ Failed fill protection
- ✅ Slippage limits
- ✅ Market hours enforcement
- ✅ Liquidity validation
- ✅ Automatic square-off on failure
- ✅ Order status monitoring
- ✅ Comprehensive error handling
- ✅ Risk-based trade blocking

## 📝 Configuration Files

- `src/config/settings.py`: Main configuration
- `src/config/symbols.py`: Symbol watchlist
- `.env`: Environment variables (credentials, thresholds)
- `requirements.txt`: Python dependencies

## 🎨 User Interface

### Terminal Dashboard Features
- Color-coded spread indicators
- Real-time price updates
- Statistics panel
- Sorted opportunity display
- Status indicators

### Web Dashboard Features
- Interactive charts
- Real-time metrics
- Sortable data tables
- Configuration viewer
- Auto-refresh

## 🔄 Integration Points

- **Angel One SmartAPI**: Full integration for market data and orders
- **WebSocket**: Real-time data streaming
- **REST API**: Order placement and status checks
- **TOTP**: Two-factor authentication
- **Logging System**: File and console logging

## 📚 Documentation

- `README.md`: Main documentation
- `FEATURES.md`: This file - complete feature list
- `DASHBOARD_GUIDE.md`: Dashboard usage guide
- `TOKEN_SETUP.md`: Instrument token setup guide
- Inline code documentation: Comprehensive docstrings

## 🎯 Key Capabilities Summary

✅ **Real-time market monitoring** across NSE and BSE  
✅ **Automatic spread detection** with configurable thresholds  
✅ **Simultaneous order execution** on both exchanges  
✅ **Comprehensive risk management** with multiple safety layers  
✅ **Failsafe mechanisms** for order failures  
✅ **Dual dashboard system** (terminal + web)  
✅ **Automatic authentication** and session management  
✅ **Backtest mode** for strategy testing  
✅ **Extensive logging** for audit and analysis  
✅ **Configurable parameters** for all aspects  
✅ **Helper tools** for token management  
✅ **Error resilience** and auto-recovery  

---

**Note**: This bot is designed for personal use and educational purposes. Always test thoroughly and trade responsibly.






