#!/usr/bin/env python3
"""
One-Click Installer for Universal WebUI Bridge v2.0

Usage: python install.py

This script:
1. Checks Python version
2. Installs dependencies
3. Installs Playwright browsers
4. Creates desktop shortcuts
5. Verifies installation
"""

import subprocess
import sys
import os
import platform
from pathlib import Path


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def check_python():
    """Check Python version."""
    print_header("Checking Python Version")
    
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print("❌ ERROR: Python 3.10+ required")
        print("Please install from: https://python.org")
        sys.exit(1)
    
    print("✅ Python version OK")
    return True


def install_package():
    """Install the package with dependencies."""
    print_header("Installing Package")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-e", "."
        ])
        print("✅ Package installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install package")
        return False


def install_playwright():
    """Install Playwright browsers."""
    print_header("Installing Browser Automation")
    
    try:
        print("Downloading Chromium browser (this may take a minute)...")
        subprocess.check_call([
            sys.executable, "-m", "playwright", "install", "chromium"
        ])
        print("✅ Browsers installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install browsers")
        return False


def create_shortcuts():
    """Create desktop shortcuts."""
    print_header("Creating Shortcuts")
    
    desktop = Path.home() / "Desktop"
    
    if platform.system() == "Windows":
        # Windows batch file
        shortcut_path = desktop / "Universal LLM Bridge.bat"
        with open(shortcut_path, "w") as f:
            f.write('''@echo off
cd /d "{}"
python -m streamlit run src/webui_bridge_v2/ui.py --server.headless true
cd /d "{}"
pause
'''.format(
                Path(__file__).parent.absolute(),
                os.getcwd()
            ))
        print(f"✅ Created: {shortcut_path}")
    
    elif platform.system() == "Darwin":  # macOS
        # macOS app shortcut would be more complex
        shortcut_path = desktop / "Universal LLM Bridge.command"
        with open(shortcut_path, "w") as f:
            f.write(f'''#!/bin/bash
cd "{Path(__file__).parent.absolute()}"
python -m streamlit run src/webui_bridge_v2/ui.py
''')
        os.chmod(shortcut_path, 0o755)
        print(f"✅ Created: {shortcut_path}")
    
    else:  # Linux
        shortcut_path = desktop / "Universal-LLM-Bridge.desktop"
        with open(shortcut_path, "w") as f:
            f.write(f'''[Desktop Entry]
Name=Universal LLM Bridge
Exec=python -m streamlit run {Path(__file__).parent.absolute()}/src/webui_bridge_v2/ui.py
Icon={Path(__file__).parent.absolute()}/icon.png
Type=Application
Terminal=false
''')
        os.chmod(shortcut_path, 0o755)
        print(f"✅ Created: {shortcut_path}")


def verify_installation():
    """Verify everything is working."""
    print_header("Verifying Installation")
    
    try:
        import webui_bridge_v2
        print("✅ Package imports successfully")
        
        from playwright.sync_api import sync_playwright
        print("✅ Playwright installed")
        
        print("\n🎉 Installation complete!")
        print(f"\nDesktop shortcut created.")
        print("\nTo start the bridge:")
        print("  - Double-click the Desktop shortcut")
        print("  - Or run: python -m webui_bridge_v2.ui")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def main():
    """Run installation."""
    print_header("Universal WebUI Bridge v2.0 Installer")
    print("Setting up your bridge...\n")
    
    try:
        check_python()
        install_package()
        install_playwright()
        create_shortcuts()
        verify_installation()
        
        print_header("Installation Complete! 🎉")
        print("\nNext steps:")
        print("1. Double-click the 'Universal LLM Bridge' shortcut on your Desktop")
        print("2. Your browser will open automatically")
        print("3. Select your LLM and start chatting!")
        print("\nFor help, visit the documentation or run with --help")
        
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled")
    except Exception as e:
        print(f"\n\n❌ Installation failed: {e}")
        print("Please report this issue with the full error message above.")


if __name__ == "__main__":
    main()
