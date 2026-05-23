#!/usr/bin/env python3
"""Legacy launcher - forwards to `webui-bridge` (webui_bridge_v2.cli)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from webui_bridge_v2.cli import main

if __name__ == "__main__":
    sys.exit(main())
