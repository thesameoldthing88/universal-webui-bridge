#!/usr/bin/env python3
"""
Universal LLM Bridge - GUI Launcher

Easy launcher script for the GUI application.
Usage: python run_gui.py
"""

import subprocess
import sys
import os

def main():
    """Launch the GUI application."""
    gui_path = os.path.join(os.path.dirname(__file__), "gui", "bridge_gui.py")
    
    print("🌉 Universal LLM Bridge - GUI Launcher")
    print("=" * 50)
    print()
    print("Starting GUI...")
    print()
    
    try:
        # Run streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", gui_path,
            "--server.port=8501",
            "--server.address=localhost",
            "--browser.gatherUsageStats=false"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error launching GUI: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)

if __name__ == "__main__":
    main()
