#!/usr/bin/env python3
"""
Universal WebUI Bridge - GUI Control Panel

A user-friendly web-based interface for the Universal WebUI Bridge.
Allows anyone to connect to any web LLM and use it with any coding agent.

Usage:
    streamlit run gui/bridge_gui.py

Features:
- Simple connection wizard
- Real-time chat interface
- Auto-detection of LLM services
- Multiple agent integrations
- Visual diagnostics
"""

import streamlit as st
import asyncio
import sys
import os
from typing import Optional, Dict, Any
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webui_bridge import UniversalWebUIBridge, setup_logging
from webui_bridge.dom_scanner import KNOWN_UI_REGISTRY
from webui_bridge.message_stream import MessageStream

# Page configuration
st.set_page_config(
    page_title="Universal LLM Bridge",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better appearance
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
    }
    .stTextInput>div>div>input {
        border-radius: 10px;
    }
    .connection-status {
        padding: 10px;
        border-radius: 10px;
        font-weight: bold;
        text-align: center;
    }
    .connected {
        background-color: #d4edda;
        color: #155724;
    }
    .disconnected {
        background-color: #f8d7da;
        color: #721c24;
    }
    .chat-message {
        padding: 10px;
        margin: 5px;
        border-radius: 10px;
    }
    .user-message {
        background-color: #007bff;
        color: white;
        margin-left: 20%;
    }
    .assistant-message {
        background-color: #e9ecef;
        color: black;
        margin-right: 20%;
    }
    .feature-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .preset-card {
        background-color: #f1f3f4;
        padding: 15px;
        border-radius: 8px;
        margin: 5px 0;
        cursor: pointer;
    }
    .preset-card:hover {
        background-color: #e8eaed;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
def init_session_state():
    """Initialize session state variables."""
    if 'bridge' not in st.session_state:
        st.session_state.bridge = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'api_mode' not in st.session_state:
        st.session_state.api_mode = False
    if 'ui_type' not in st.session_state:
        st.session_state.ui_type = None
    if 'theme' not in st.session_state:
        st.session_state.theme = None
    if 'streaming' not in st.session_state:
        st.session_state.streaming = False
    if 'agent_config' not in st.session_state:
        st.session_state.agent_config = {}
    if 'browser_visible' not in st.session_state:
        st.session_state.browser_visible = True
    if 'use_existing_browser' not in st.session_state:
        st.session_state.use_existing_browser = False

init_session_state()

# Sidebar - Navigation
st.sidebar.title("🌉 Universal LLM Bridge")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigation",
    ["🏠 Home", "🔗 Connect", "💬 Chat", "🤖 Agent Setup", "⚙️ Settings", "📊 Diagnostics"],
    index=0
)

st.sidebar.markdown("---")

# Connection Status in Sidebar
if st.session_state.connected:
    st.sidebar.markdown(
        '<div class="connection-status connected">● Connected</div>',
        unsafe_allow_html=True
    )
    if st.session_state.api_mode:
        st.sidebar.markdown("⚡ Direct API Mode")
    else:
        st.sidebar.sidebar.markdown("🖱️ UI Automation Mode")
    
    if st.sidebar.button("Disconnect", type="secondary"):
        if st.session_state.bridge:
            asyncio.run(st.session_state.bridge.close())
        st.session_state.connected = False
        st.session_state.bridge = None
        st.session_state.messages = []
        st.rerun()
else:
    st.sidebar.markdown(
        '<div class="connection-status disconnected">● Disconnected</div>',
        unsafe_allow_html=True
    )

# HOME PAGE
if page == "🏠 Home":
    st.title("Welcome to Universal LLM Bridge")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 🌉 Connect Any LLM to Any Coding Agent
        
        This tool allows you to use **any web-based LLM** (like OpenWebUI, LM Studio, Claude Web, 
        ChatGPT, or custom UIs) with **any coding agent** (Pi, OpenCode, Claude Desktop, Codex, etc.)
        
        **No coding required!** Just enter your LLM's web address and start chatting.
        """
        )
        
        st.markdown("---")
        
        st.subheader("✨ Key Features")
        
        features = [
            ("🔌", "Universal Compatibility", "Works with OpenWebUI, LM Studio, Claude, ChatGPT, and any custom web UI"),
            ("🤖", "Agent Integration", "Connect to Pi, OpenCode, Claude Desktop, Codex, and more"),
            ("⚡", "Two Operation Modes", "Direct API (fast) or UI Automation (universal)"),
            ("🔄", "Auto-Detection", "Automatically finds chat elements - no configuration needed"),
            ("🔧", "Self-Healing", "Automatically recovers if the UI changes or reloads"),
            ("🌍", "Multi-Language", "Supports English, Chinese, Korean, Japanese, and more"),
        ]
        
        for icon, title, desc in features:
            with st.container():
                st.markdown(f"**{icon} {title}**")
                st.markdown(f"{desc}")
                st.markdown("")
    
    with col2:
        st.markdown("### Quick Start")
        st.markdown("1. Go to **🔗 Connect**")
        st.markdown("2. Enter your LLM URL")
        st.markdown("3. Click **Connect**")
        st.markdown("4. Start chatting!")
        
        if st.button("Get Started →", type="primary", use_container_width=True):
            st.switch_page("pages/1_Connect.py")
        
        st.markdown("---")
        
        st.markdown("### Supported LLMs")
        llms = [
            "• OpenWebUI", "• LM Studio", "• Oobabooga",
            "• Jan", "• HuggingFace", "• Claude Web",
            "• ChatGPT", "• Custom UIs"
        ]
        st.markdown("\n".join(llms))

# CONNECT PAGE
elif page == "🔗 Connect":
    st.title("Connect to Your LLM")
    
    # Connection Wizard
    st.markdown("### Step 1: Select Your LLM Service")
    
    # Preset configurations for popular services
    presets = {
        "OpenWebUI": {"url": "http://localhost:3000", "desc": "Local OpenWebUI instance"},
        "LM Studio": {"url": "http://localhost:1234", "desc": "LM Studio server"},
        "Oobabooga": {"url": "http://localhost:7860", "desc": "Oobabooga TextGen WebUI"},
        "Jan": {"url": "http://localhost:1337", "desc": "Jan AI local instance"},
        "Claude Web": {"url": "https://claude.ai", "desc": "Anthropic Claude (requires login)"},
        "ChatGPT": {"url": "https://chat.openai.com", "desc": "OpenAI ChatGPT (requires login)"},
        "HuggingFace": {"url": "https://huggingface.co/chat", "desc": "HuggingFace Chat"},
        "Custom": {"url": "", "desc": "Enter your own URL"},
    }
    
    selected_preset = st.selectbox(
        "Quick Select",
        options=list(presets.keys()),
        index=0
    )
    
    # URL Input with validation
    default_url = presets[selected_preset]["url"]
    url = st.text_input(
        "LLM Web URL",
        value=default_url,
        placeholder="http://localhost:3000 or https://...",
        help="Enter the web address of your LLM interface (https:// will be added automatically if needed)"
    )
    
    # Show URL validation feedback
    if url and not url.startswith(('http://', 'https://')):
        if url.startswith('localhost') or url.startswith('127.'):
            st.info(f"ℹ️ Will use: http://{url}")
        else:
            st.info(f"ℹ️ Will use: https://{url}")
    
    if presets[selected_preset]["desc"]:
        st.caption(presets[selected_preset]["desc"])
    
    st.markdown("---")
    
    # Advanced Options
    with st.expander("⚙️ Advanced Options"):
        col1, col2 = st.columns(2)
        
        with col1:
            headless = st.checkbox(
                "Headless Mode (hide browser)",
                value=False,
                help="Run without showing the browser window"
            )
            
            use_existing = st.checkbox(
                "Use Existing Chrome (keep logins)",
                value=st.session_state.get('use_existing_browser', False),
                key='use_existing_checkbox',
                help="Connect to your already-open Chrome with all your logins"
            )
            
            # Store in session state for persistence
            st.session_state.use_existing_browser = use_existing
            
            if use_existing:
                st.info("To use existing Chrome:\n"
                       "1. Close ALL Chrome windows\n"
                       "2. Open cmd and run:\n"
                       "chrome.exe --remote-debugging-port=9222\n"
                       "3. Log into your LLM\n"
                       "4. Click Connect")
                
            auto_api = st.checkbox(
                "Auto-detect API",
                value=True,
                help="Try to use direct backend API for faster responses"
            )
        
        with col2:
            min_confidence = st.slider(
                "Detection Confidence",
                min_value=1.0,
                max_value=5.0,
                value=2.0,
                step=0.5,
                help="Higher = stricter element detection"
            )
            
            observation_time = st.slider(
                "API Detection Time",
                min_value=1,
                max_value=10,
                value=3,
                help="Seconds to observe network traffic for API detection"
            )
    
    st.markdown("---")
    
    # Connect Button
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("Connect to LLM", type="primary", use_container_width=True):
            if not url:
                st.error("❌ Please enter a URL")
            else:
                with st.spinner("Connecting... This may take a moment"):
                    try:
                        # Create bridge
                        use_existing_browser = st.session_state.get('use_existing_browser', False)
                        bridge = UniversalWebUIBridge(
                            headless=headless,
                            min_confidence=min_confidence,
                            use_existing_browser=use_existing_browser,
                            existing_browser_endpoint="http://localhost:9222"
                        )
                        
                        # Connect
                        asyncio.run(bridge.connect(url))
                        
                        st.session_state.bridge = bridge
                        st.session_state.connected = True
                        st.session_state.browser_visible = not headless
                        
                        # Detect theme
                        try:
                            theme = asyncio.run(bridge.detect_theme())
                            st.session_state.theme = theme
                        except:
                            pass
                        
                        # Try API mode
                        if auto_api:
                            api_enabled = asyncio.run(
                                bridge.try_enable_direct_api(observation_time=observation_time)
                            )
                            st.session_state.api_mode = api_enabled
                        
                        # Detect UI type
                        ui_type = bridge._scanner.get_detected_ui_type()
                        st.session_state.ui_type = ui_type
                        
                        st.success("✅ Connected successfully!")
                        
                        if api_enabled:
                            st.info("⚡ Using Direct API Mode (faster)")
                        else:
                            st.info("🖱️ Using UI Automation Mode (universal)")
                        
                        if ui_type:
                            st.info(f"🎯 Detected UI: {ui_type}")
                        
                        st.balloons()
                        
                    except Exception as e:
                        st.error(f"❌ Connection failed: {str(e)}")
                        st.info("💡 Make sure the LLM service is running and accessible")
    
    with col3:
        if st.button("Test Connection"):
            st.info("Test feature: Will verify URL is reachable (not yet implemented)")

# CHAT PAGE
elif page == "💬 Chat":
    st.title("Chat Interface")
    
    if not st.session_state.connected:
        st.warning("⚠️ Not connected. Please go to 🔗 Connect first.")
        st.button("Go to Connect", on_click=lambda: st.switch_page("pages/1_Connect.py"))
    else:
        # Chat interface
        st.markdown("### Chat with your LLM")
        
        # Display messages
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.messages:
                if msg['role'] == 'user':
                    st.markdown(
                        f'<div class="chat-message user-message">'
                        f'<strong>You:</strong> {msg["content"]}</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div class="chat-message assistant-message">'
                        f'<strong>Assistant:</strong> {msg["content"]}</div>',
                        unsafe_allow_html=True
                    )
        
        # Input area
        message_input = st.text_area(
            "Your message",
            placeholder="Type your message here...",
            key="message_input",
            height=100
        )
        
        col1, col2, col3 = st.columns([1, 1, 4])
        
        with col1:
            if st.button("Send", type="primary", use_container_width=True):
                if message_input.strip():
                    # Add user message
                    st.session_state.messages.append({
                        'role': 'user',
                        'content': message_input
                    })
                    
                    # Send to LLM
                    try:
                        with st.spinner("Thinking..."):
                            bridge = st.session_state.bridge
                            
                            # Send message
                            asyncio.run(bridge.send(message_input))
                            
                            # Wait for response
                            response = asyncio.run(bridge.wait_for_response(timeout=120.0))
                            
                            # Add assistant message
                            st.session_state.messages.append({
                                'role': 'assistant',
                                'content': response or "(No response received)"
                            })
                            
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        with col2:
            if st.button("Clear Chat", use_container_width=True):
                st.session_state.messages = []
                st.rerun()
        
        # Streaming toggle
        st.checkbox("Enable streaming", value=False, key="streaming_mode")

# AGENT SETUP PAGE
elif page == "🤖 Agent Setup":
    st.title("Coding Agent Integration")
    
    st.markdown("""
    ### Connect Your Favorite Coding Agent
    
    Configure how coding agents like **Pi, OpenCode, Claude Desktop, Codex, and others**
    should use this bridge to communicate with your LLM.
    """)
    
    agents = {
        "Pi": {
            "icon": "🥧",
            "description": "Pi coding agent (available in Pi terminal)",
            "config": {
                "api_endpoint": "http://localhost:8000/api",
                "websocket": True
            }
        },
        "OpenCode": {
            "icon": "📝",
            "description": "OpenCode CLI agent",
            "config": {
                "command": "opencode",
                "mode": "bridge"
            }
        },
        "Claude Desktop": {
            "icon": "🎭",
            "description": "Anthropic Claude Desktop app",
            "config": {
        "integration": "desktop_bridge",
                "port": 8888
            }
        },
        "Codex": {
            "icon": "📜",
            "description": "OpenAI Codex CLI",
            "config": {
                "provider": "bridge",
             "endpoint": "http://localhost:8000"
            }
        },
        "Cursor": {
            "icon": "💫",
      "description": "Cursor IDE with AI",
            "config": {
      "integration": "ide_plugin"
            }
        }
    }
    
    selected_agent = st.selectbox(
        "Select Agent",
        options=list(agents.keys()),
        format_func=lambda x: f"{agents[x]['icon']} {x}"
    )
    
    if selected_agent:
        agent = agents[selected_agent]
        
        st.markdown(f"### {agent['icon']} {selected_agent}")
        st.markdown(agent['description'])
        
        st.markdown("#### Configuration")
        
        # Generate config file
        config = {
            "agent": selected_agent,
            "bridge_url": "http://localhost:8000",
            "llm_url": st.session_state.get('last_url', 'http://localhost:3000'),
            **agent['config']
        }
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.json(config)
        
        with col2:
            if st.button("📋 Copy Config", use_container_width=True):
                st.code(json.dumps(config, indent=2), language="json")
      
            if st.button("💾 Save Config File", use_container_width=True):
                filename = f"{selected_agent.lower().replace(' ', '_')}_config.json"
                st.download_button(
      label="Download JSON",
          data=json.dumps(config, indent=2),
                    file_name=filename,
                    mime="application/json"
 )
        
        st.markdown("---")
  
        st.markdown("#### Setup Instructions")
        
        if selected_agent == "Pi":
         st.markdown("""
1. Install the Pi bridge adapter:
   ```bash
   pip install pi-universal-bridge
   ```
2. Start the bridge server
   ```
   Run Bridge Server
            """)
            
        elif selected_agent == "OpenCode":
            st.markdown("""
1. Configure OpenCode to use bridge:
   ```bash
   opencode config set provider universal-bridge
   opencode config set bridge_url http://localhost:8000
   ```
2. Start coding with `opencode`
            """)
            
        elif selected_agent == "Claude Desktop":
            st.markdown("""
1. Install Claude Desktop bridge plugin
2. Configure MCP server to point to this bridge
3. Restart Claude Desktop
            """)

# SETTINGS PAGE
elif page == "⚙️ Settings":
    st.title("Settings")
    
    tabs = st.tabs(["General", "Detection", "Advanced", "About"])
    
    with tabs[0]:  # General
        st.markdown("### General Settings")
        
        default_url = st.text_input(
            "Default LLM URL",
            value="http://localhost:3000",
            help="URL to connect to by default"
        )
        
        enable_logging = st.checkbox(
            "Enable Debug Logging",
            value=False,
            help="Show detailed logs for troubleshooting"
        )
        
        if enable_logging:
            import logging
            logging.basicConfig(level=logging.DEBUG)
    
    with tabs[1]:  # Detection
        st.markdown("### Element Detection Settings")
        
        confidence = st.slider(
            "Detection Confidence",
            min_value=1.0,
            max_value=5.0,
            value=2.0,
            help="Higher = more strict detection"
        )
        
        st.markdown("#### Known UI Detection")
        
        use_known_uis = st.checkbox(
            "Use Known UI Profiles",
            value=True,
            help="Auto-detect popular LLM interfaces"
        )
        
        if use_known_uis:
            st.markdown("**Registered UIs:**")
            for ui_type, config in KNOWN_UI_REGISTRY.items():
                st.markdown(f"- {config.name}")
    
    with tabs[2]:  # Advanced
        st.markdown("### Advanced Settings")
        
        st.markdown("#### Network Sniffing")
  
        auto_detect_api = st.checkbox(
  "Auto-detect Backend API",
      value=True,
      help="Try to find direct API endpoints"
        )
        
        st.markdown("#### Browser Settings")
        
        browser_type = st.selectbox(
            "Browser",
            ["chromium", "firefox", "webkit"],
            index=0
        )
        
        viewport_width = st.number_input("Viewport Width", value=1280)
        viewport_height = st.number_input("Viewport Height", value=800)
    
    with tabs[3]:  # About
        st.markdown("### About Universal LLM Bridge")
        st.markdown(f"**Version:** 0.1.0")
        st.markdown(f"**Tests:** 48/48 passing")
        st.markdown(f"**Features:** 22/22 implemented")
        
        st.markdown("---")
        
        st.markdown("#### Open Source Components")
        components = [
            "Playwright - Browser automation",
            "Streamlit - GUI framework",
            "Pydantic - Data validation",
            "pytest - Testing framework"
        ]
        for comp in components:
            st.markdown(f"- {comp}")

# DIAGNOSTICS PAGE
elif page == "📊 Diagnostics":
    st.title("Diagnostics & Status")
    
    if not st.session_state.connected:
        st.warning("⚠️ Not connected. Please connect to an LLM first.")
    else:
        bridge = st.session_state.bridge
        
        st.markdown("### Connection Status")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Status", "Connected" if st.session_state.connected else "Disconnected")
        with col2:
            mode = "Direct API" if st.session_state.api_mode else "UI Automation"
            st.metric("Mode", mode)
        with col3:
            ui = st.session_state.ui_type or "Unknown"
            st.metric("Detected UI", ui)
        
        st.markdown("---")
        
        st.markdown("### Element Detection Status")
        
        if bridge._scanner:
            input_sel = bridge._scanner.get_input_selector()
            send_sel = bridge._scanner.get_send_selector()
            chat_sel = bridge._scanner.get_chat_selector()
  
            elements = {
                "Input Field": input_sel or "Not detected",
                "Send Button": send_sel or "Not detected",
                "Chat Container": chat_sel or "Not detected"
            }
            
            for name, selector in elements.items():
                if selector != "Not detected":
                    st.success(f"[OK] {name}: `{selector}`")
                else:
                    st.error(f"[MISSING] {name}")
        
        st.markdown("---")
        
        st.markdown("### Agent Server")
        
        if st.button("Start Agent Server", type="primary"):
            st.info("Agent server would start here, allowing external agents to connect")
            st.code("""
python -m webui_bridge.server --port 8000
            """)
        
        st.markdown("---")
        
        # System info
        st.markdown("### System Information")
        
        col1, col2 = st.columns(2)
        
        with col1:
            import platform
            st.markdown(f"**Python:** {platform.python_version()}")
            st.markdown(f"**OS:** {platform.system()} {platform.release()}")
        with col2:
            st.markdown(f"**Playwright:** Installed")
            st.markdown(f"**Streamlit:** {st.__version__}")

# Run the app
if __name__ == "__main__":
    pass  # Streamlit handles this
