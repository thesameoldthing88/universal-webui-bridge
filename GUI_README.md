# GUI Quick Start Guide

## Easy Installation

```bash
# Install with GUI support
pip install -e ".[gui]"

# Install Playwright browsers
playwright install chromium
```

## Running the GUI

### Option 1: Simple Launch
```bash
python run_gui.py
```

### Option 2: Streamlit Command
```bash
streamlit run gui/bridge_gui.py
```

### Option 3: Installed Command
```bash
webui-bridge-gui
```

## GUI Features

### 🏠 Home Page
- Quick overview of features
- Connection wizard
- Supported LLMs list

### 🔗 Connect Page
- **Quick Select**: Choose from presets (OpenWebUI, LM Studio, Claude, etc.)
- **Custom URL**: Enter any web LLM address
- **Auto-Detection**: Automatically finds elements and API
- **Advanced Options**: Configure detection settings

### 💬 Chat Page
- Real-time chat interface
- Message history
- Streaming output
- Clear chat button

### 🤖 Agent Setup Page
- Pi integration
- OpenCode configuration
- Claude Desktop setup
- Codex adapter
- Generic agent support

### ⚙️ Settings Page
- General settings
- Detection parameters
- Advanced options
- System information

### 📊 Diagnostics Page
- Connection status
- Element detection status
- Agent server control
- System info

## Connecting to Popular LLMs

### OpenWebUI
1. Select "OpenWebUI" from Quick Select
2. URL: `http://localhost:3000`
3. Click "Connect"

### LM Studio
1. Select "LM Studio" from Quick Select
2. Start LM Studio server (port 1234)
3. Click "Connect"

### Claude Web
1. Select "Claude Web"
2. URL: `https://claude.ai`
3. Connect and log in manually in browser
4. Start chatting

### ChatGPT
1. Select "ChatGPT"
2. URL: `https://chat.openai.com`
3. Connect and log in manually in browser

## Integrating with Coding Agents

### Pi
Configure Pi to use the bridge:
```bash
# In Pi settings, set:
Provider: Universal Bridge
Bridge URL: http://localhost:8000
```

### OpenCode
```bash
opencode config set provider universal-bridge
opencode config set bridge_url http://localhost:8000
```

### Claude Desktop
1. Install MCP server config
2. Point to bridge server
3. Restart Claude Desktop

## Features for Non-Technical Users

✅ **No coding required** - Just click and connect
✅ **Visual interface** - See what the bridge is doing
✅ **Quick presets** - Popular LLMs pre-configured
✅ **Auto-detection** - Finds everything automatically
✅ **Clear status** - Always know if you're connected
✅ **Error messages** - Helpful explanations when things go wrong

## Troubleshooting

### Browser not showing
- Check "Headless Mode" is not enabled in Advanced Options
- Browser opens in separate window

### Connection fails
- Verify LLM service is running
- Check URL is correct (include http:// or https://)
- Try "Test Connection" button

### Elements not detected
- Increase "Detection Confidence" in Advanced Options
- Make sure chat interface is fully loaded
- Try manual element selector

### Agent won't connect
- Start Agent Server from Diagnostics page
- Check firewall settings (port 8000)
- Verify agent configuration

## Getting Help

1. Check Diagnostics page for status
2. Enable Debug Logging in Settings
3. Check log files
4. Create issue on GitHub
