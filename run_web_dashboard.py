"""
Quick launcher for the web dashboard.

Run this script to start the Streamlit web dashboard.
Make sure the bot is running in another terminal for live data.
"""

import subprocess
import sys

if __name__ == "__main__":
    print("Starting Web Dashboard...")
    print("Open your browser to the URL shown below")
    print("=" * 50)
    
    # Run streamlit
    subprocess.run([
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/ui/web_dashboard.py",
        "--server.port=8501",
        "--server.headless=false",
    ])






