"""
Universal WebUI Bridge v2

Connects coding agents (and humans) to any web-based LLM chat UI by automating
a real browser. Logins persist via an on-disk browser profile, so you log in
once per service and stay logged in.

    from webui_bridge_v2 import LLMBridge

    bridge = LLMBridge()
    await bridge.connect("https://chatgpt.com")   # log in once in the window
    reply = await bridge.chat("Hello!")
    await bridge.close()
"""

__version__ = "2.1.0"


def __getattr__(name):
    # Lazy imports keep `import webui_bridge_v2.browser` cheap and avoid
    # pulling Playwright in until the bridge is actually used.
    if name in ("LLMBridge", "BridgeState", "BridgeStatus"):
        from . import core

        return getattr(core, name)
    if name in ("BrowserSession", "BrowserResult"):
        from . import browser

        return getattr(browser, name)
    if name in ("CodingAgent", "AgentTools", "ToolResult"):
        from . import agent

        return getattr(agent, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMBridge",
    "BridgeState",
    "BridgeStatus",
    "BrowserSession",
    "BrowserResult",
    "CodingAgent",
    "AgentTools",
    "ToolResult",
    "__version__",
]
