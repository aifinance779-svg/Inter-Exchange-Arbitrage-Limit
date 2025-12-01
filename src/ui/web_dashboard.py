"""
Streamlit web dashboard for NSE ↔ BSE Arbitrage Bot.

Run with: streamlit run src/ui/web_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import threading
from typing import Dict, Optional

from src.config.settings import settings
from src.core.logger import get_logger

logger = get_logger("web_dashboard")

# Try to import shared dashboard state (if running alongside bot)
try:
    # This will work if web dashboard is running in same process as bot
    from src.ui.terminal_dashboard import TerminalDashboard
    # Access terminal dashboard data if available
    _shared_dashboard = None
except ImportError:
    _shared_dashboard = None

# Global state for dashboard data
if 'dashboard_data' not in st.session_state:
    st.session_state.dashboard_data = {}
if 'stats' not in st.session_state:
    st.session_state.stats = {
        "total_signals": 0,
        "successful_trades": 0,
        "failed_trades": 0,
        "start_time": datetime.now(),
    }


class WebDashboard:
    """Web dashboard using Streamlit."""
    
    def __init__(self):
        self.data = st.session_state.dashboard_data
        self.stats = st.session_state.stats
    
    def update(self, symbol: str, **kwargs):
        """Update data for a symbol."""
        if symbol not in self.data:
            self.data[symbol] = {
                "symbol": symbol,
                "nse_price": 0.0,
                "bse_price": 0.0,
                "spread": 0.0,
                "spread_pct": 0.0,
                "quantity": 0,
                "signal": "-",
                "status": "-",
                "last_update": None,
            }
        
        self.data[symbol].update(kwargs)
        self.data[symbol]["last_update"] = datetime.now()
        
        # Calculate spread percentage
        nse = self.data[symbol].get("nse_price", 0)
        bse = self.data[symbol].get("bse_price", 0)
        if nse > 0 and bse > 0:
            avg = (nse + bse) / 2
            spread = abs(nse - bse)
            self.data[symbol]["spread"] = spread
            self.data[symbol]["spread_pct"] = (spread / avg * 100) if avg > 0 else 0
    
    def update_stats(self, **kwargs):
        """Update statistics."""
        self.stats.update(kwargs)


def render_dashboard():
    """Render the Streamlit dashboard."""
    st.set_page_config(
        page_title="NSE ↔ BSE Arbitrage Bot",
        page_icon="📈",
        layout="wide",
    )
    
    dashboard = WebDashboard()
    
    # Header
    st.title("📈 NSE ↔ BSE Arbitrage Trading Bot")
    st.markdown("---")
    
    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Signals", dashboard.stats.get("total_signals", 0))
    
    with col2:
        st.metric(
            "Successful Trades",
            dashboard.stats.get("successful_trades", 0),
            delta=None,
        )
    
    with col3:
        st.metric(
            "Failed Trades",
            dashboard.stats.get("failed_trades", 0),
            delta=None,
        )
    
    with col4:
        runtime = datetime.now() - dashboard.stats.get("start_time", datetime.now())
        st.metric("Runtime", str(runtime).split('.')[0])
    
    st.markdown("---")
    
    # Main data table
    if dashboard.data:
        # Convert to DataFrame
        df_data = []
        for symbol, data in dashboard.data.items():
            df_data.append({
                "Symbol": symbol,
                "NSE Price": f"₹{data.get('nse_price', 0):.2f}" if data.get('nse_price', 0) > 0 else "-",
                "BSE Price": f"₹{data.get('bse_price', 0):.2f}" if data.get('bse_price', 0) > 0 else "-",
                "Spread": f"₹{data.get('spread', 0):.2f}" if data.get('spread', 0) > 0 else "-",
                "Spread %": f"{data.get('spread_pct', 0):.2f}%" if data.get('spread_pct', 0) > 0 else "-",
                "Quantity": data.get('quantity', 0),
                "Signal": data.get('signal', '-'),
                "Status": data.get('status', '-'),
            })
        
        df = pd.DataFrame(df_data)
        
        # Sort by spread
        if 'Spread' in df.columns:
            df = df.sort_values('Spread', ascending=False, na_position='last')
        
        # Display table
        st.subheader("📊 Live Market Data")
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )
        
        # Spread visualization
        st.subheader("📈 Spread Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Bar chart of spreads
            symbols = [d["Symbol"] for d in df_data]
            spreads = [float(d["Spread"].replace("₹", "").replace("-", "0")) for d in df_data]
            
            fig_bar = go.Figure(data=[
                go.Bar(
                    x=symbols,
                    y=spreads,
                    marker_color=['green' if s >= settings.min_spread else 'orange' if s >= settings.min_spread * 0.7 else 'gray' for s in spreads],
                )
            ])
            fig_bar.update_layout(
                title="Current Spreads by Symbol",
                xaxis_title="Symbol",
                yaxis_title="Spread (₹)",
                height=400,
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        
        with col2:
            # Spread percentage chart
            spread_pcts = [float(d["Spread %"].replace("%", "").replace("-", "0")) for d in df_data]
            
            fig_pct = go.Figure(data=[
                go.Bar(
                    x=symbols,
                    y=spread_pcts,
                    marker_color=['green' if s >= (settings.min_spread / 100) else 'orange' for s in spread_pcts],
                )
            ])
            fig_pct.update_layout(
                title="Spread Percentage by Symbol",
                xaxis_title="Symbol",
                yaxis_title="Spread (%)",
                height=400,
            )
            st.plotly_chart(fig_pct, use_container_width=True)
    
    else:
        st.info("⏳ Waiting for market data... Make sure the bot is running and tokens are configured.")
    
    # Configuration panel
    with st.expander("⚙️ Configuration", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Min Spread:** ₹{settings.min_spread:.2f}")
            st.write(f"**Trading Hours:** {settings.trading_start.strftime('%H:%M')} - {settings.trading_end.strftime('%H:%M')}")
            st.write(f"**Symbols Tracked:** {len(dashboard.data)}")
        
        with col2:
            st.write(f"**Default Quantity:** {settings.default_quantity}")
            st.write(f"**Poll Interval:** {settings.poll_interval_ms}ms")
            st.write(f"**Depth Levels:** {settings.depth_levels}")
    
    # Auto-refresh
    time.sleep(1)
    st.rerun()


if __name__ == "__main__":
    render_dashboard()

