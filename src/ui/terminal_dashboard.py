"""
Enhanced terminal dashboard built with Rich.
Features colorful display, spread indicators, and real-time updates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from src.config.settings import settings


console = Console()


@dataclass
class DashboardRow:
    symbol: str
    nse_price: float = 0.0
    bse_price: float = 0.0
    spread: float = 0.0
    spread_pct: float = 0.0
    quantity: int = 0
    signal: str = "-"
    status: str = "-"
    last_update: Optional[datetime] = None
    nse_bid: float = 0.0
    nse_ask: float = 0.0
    bse_bid: float = 0.0
    bse_ask: float = 0.0


class TerminalDashboard:
    def __init__(self):
        self.rows: Dict[str, DashboardRow] = {}
        self.stats = {
            "total_signals": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "start_time": datetime.now(),
        }

    def update(self, symbol: str, **kwargs):
        row = self.rows.get(symbol) or DashboardRow(symbol=symbol)
        for key, value in kwargs.items():
            setattr(row, key, value)
        row.last_update = datetime.now()
        
        # Calculate spread percentage
        if row.nse_price > 0 and row.bse_price > 0:
            avg_price = (row.nse_price + row.bse_price) / 2
            row.spread_pct = (row.spread / avg_price * 100) if avg_price > 0 else 0
        
        self.rows[symbol] = row

    def update_stats(self, **kwargs):
        self.stats.update(kwargs)

    def _get_spread_color(self, spread: float, spread_pct: float) -> str:
        """Get color based on spread value."""
        min_spread = settings.min_spread
        if spread >= min_spread:
            return "[bold green]"  # Profitable spread
        elif spread >= min_spread * 0.7:
            return "[yellow]"  # Approaching threshold
        else:
            return "[white]"  # Below threshold

    def _get_status_color(self, status: str) -> str:
        """Get color based on status."""
        status_colors = {
            "OK": "[bold green]",
            "PENDING": "[yellow]",
            "FAIL": "[bold red]",
            "BLOCKED": "[red]",
            "-": "[dim]",
        }
        return status_colors.get(status, "[white]")

    def render_main_table(self) -> Table:
        """Render the main arbitrage table."""
        table = Table(
            title="[bold cyan]NSE ↔ BSE Arbitrage Monitor[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            expand=True,
        )
        
        table.add_column("Symbol", style="cyan", width=12)
        table.add_column("NSE Price", justify="right", style="green", width=10)
        table.add_column("BSE Price", justify="right", style="blue", width=10)
        table.add_column("Spread", justify="right", width=10)
        table.add_column("Spread %", justify="right", width=10)
        table.add_column("Qty", justify="right", width=6)
        table.add_column("Signal", width=12)
        table.add_column("Status", width=10)

        # Sort by spread (descending) to show best opportunities first
        sorted_rows = sorted(
            self.rows.values(),
            key=lambda x: x.spread,
            reverse=True
        )

        for row in sorted_rows:
            spread_color = self._get_spread_color(row.spread, row.spread_pct)
            status_color = self._get_status_color(row.status)
            
            # Format signal
            signal_text = row.signal if row.signal != "-" else "[dim]-[/dim]"
            
            table.add_row(
                f"[bold]{row.symbol}[/bold]",
                f"₹{row.nse_price:.2f}" if row.nse_price > 0 else "[dim]-[/dim]",
                f"₹{row.bse_price:.2f}" if row.bse_price > 0 else "[dim]-[/dim]",
                f"{spread_color}₹{row.spread:.2f}[/]" if row.spread > 0 else "[dim]-[/dim]",
                f"{spread_color}{row.spread_pct:.2f}%[/]" if row.spread_pct > 0 else "[dim]-[/dim]",
                str(row.quantity) if row.quantity > 0 else "[dim]-[/dim]",
                signal_text,
                f"{status_color}{row.status}[/]",
            )
        
        return table

    def render_stats_panel(self) -> Panel:
        """Render statistics panel."""
        runtime = datetime.now() - self.stats["start_time"]
        runtime_str = str(runtime).split('.')[0]  # Remove microseconds
        
        stats_text = f"""
[bold cyan]Bot Statistics[/bold cyan]

Runtime: {runtime_str}
Total Signals: {self.stats['total_signals']}
Successful Trades: [green]{self.stats['successful_trades']}[/green]
Failed Trades: [red]{self.stats['failed_trades']}[/red]

[bold cyan]Configuration[/bold cyan]

Min Spread: ₹{settings.min_spread:.2f}
Symbols Tracked: {len(self.rows)}
Market Hours: {settings.trading_start.strftime('%H:%M')} - {settings.trading_end.strftime('%H:%M')}
        """
        
        return Panel(stats_text, title="[bold]Stats[/bold]", border_style="blue")

    def render(self) -> Layout:
        """Render the complete dashboard layout."""
        layout = Layout()
        
        # Split into main table and stats
        layout.split_column(
            Layout(name="main", size=20),
            Layout(name="stats", size=8),
        )
        
        layout["main"].update(self.render_main_table())
        layout["stats"].update(self.render_stats_panel())
        
        return layout

    def live_loop(self):
        """Run the live dashboard loop."""
        try:
            with Live(
                self.render(),
                refresh_per_second=4,
                console=console,
                screen=True,
            ) as live:
                while True:
                    live.update(self.render())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped.[/yellow]")

