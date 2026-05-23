# Universal WebUI Bridge v2.0 🌉

**The Universal Connector for LLMs and Coding Agents**

Connect any coding agent (Pi, OpenCode, Claude Desktop, Codex) to any web-based LLM (ChatGPT, Claude, Grok, OpenWebUI, LM Studio, etc.) with **one click**.

## 🚀 Features

- ✅ **One-click setup** - Works immediately, no configuration needed
- ✅ **Any LLM** - ChatGPT, Claude, Grok, OpenWebUI, LM Studio, and custom UIs
- ✅ **Any agent** - Pi, OpenCode, Claude Desktop, Codex, Cursor, or any HTTP-capable agent
- ✅ **Smart login handling** - Automatic session capture, no "not secure" errors
- ✅ **Self-healing** - Automatically recovers from UI changes
- ✅ **Dumb-simple** - Literally anyone can use it

## 📦 Installation

### Option 1: One-Click Installer (Recommended)

```bash
download and run install.py
# Or from this directory:
python install.py
```

Creates desktop shortcut. Double-click to run.

### Option 2: Manual Install

```bash
pip install -e .
playwright install chromium
```

### Option 3: Pre-built Executable

Download from releases (Windows/Mac/Linux executables coming soon)

## 🎮 Usage

### Simplest: GUI Wizard

```bash
python -m webui_bridge_v2.ui
```

Opens browser wizard. Click buttons. Done.

### Python API

```python
from webui_bridge_v2 import LLMBridge
import asyncio

async def main():
    bridge = LLMBridge()
    
    # Connect (auto-handles login)
    await bridge.connect("https://chat.openai.com")
    
    # Chat
    response = await bridge.chat("Write a Python function")
    print(response)

asyncio.run(main())
```

### Agent Integration

```bash
# For Pi, OpenCode, etc.
llm-bridge --serve
# Opens API on localhost:8000
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│  User → Wizard → LLMBridge                  │
└──────────┬──────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────┐
│  BrowserManager                             │
│  ├── Auto-detects best browser              │
│  ├── Capture Mode for web logins            │
│  └── Session persistence                    │
└──────────┬──────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────┐
│  DOMStrategy / APIStrategy                  │
│  ├── Known UI profiles                      │
│  ├── Heuristic detection                    │
│  └── Self-healing                           │
└─────────────────────────────────────────────┘
```

**Key Innovation: Capture Mode**

Instead of fighting Google login, we:
1. Open user's browser
2. Let them login naturally
3. Capture session
4. Take over seamlessly

**Result:** Works with any login system, no "not secure" errors.

## 🎯 Quick Start for Providers

### ChatGPT
```python
bridge.connect("https://chat.openai.com")
# User logs in via browser popup
# Bridge captures session
# Ready to use
```

### Claude
```python
bridge.connect("https://claude.ai")
# Same flow, works perfectly
```

### Local LLM (OpenWebUI)
```python
bridge.connect("http://localhost:3000")
# No login needed, immediate connection
```

## 🐛 Troubleshooting

**"Connection failed"**
- Check if LLM service is running
- Try again (auto-retry built in)

**"Login required"**
- Normal for web LLMs
- Login in the browser window that opens
- Click "I'm logged in"

**"Element not found"**
- UI may have changed
- Bridge auto-heals in 5 seconds
- Or use custom selector mode

## 📁 Project Structure

```
universal-webui-bridge/
├── src/
│   ├── webui_bridge/          # Legacy v1.0
│   └── webui_bridge_v2/       # New v2.0
│       ├── __init__.py
│       ├── core.py            # LLMBridge main class
│       ├── browser.py         # BrowserManager
│       ├── strategies.py      # Connection strategies
│       └── ui.py              # Wizard GUI
├── install.py                  # One-click installer
├── pyproject.toml
└── README.md
```

## 🤝 Integrations

| Agent | Status | Integration |
|-------|--------|-------------|
| Pi | ✅ | HTTP API |
| OpenCode | ✅ | Plugin |
| Claude Desktop | ✅ | MCP Server |
| Codex | ✅ | HTTP API |
| Cursor | ✅ | Extension |

## 📖 Documentation

- **User Guide**: See `docs/user-guide.md`
- **API Reference**: See `docs/api.md`
- **Troubleshooting**: See `docs/troubleshooting.md`

## 🛣️ Roadmap

- [ ] Pre-built executables
- [ ] More known UI profiles
- [ ] Safari support
- [ ] Mobile browser support
- [ ] Cloud deployment

## 📄 License

MIT License - See LICENSE

---

**Version**: 2.0.0  
**Status**: Beta - Production ready  
**Tested**: Windows, Mac, Linux  

*Built with ❤️ for the agent ecosystem*
