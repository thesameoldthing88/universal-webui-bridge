"""
Known-UI profiles.

A profile is just a set of best-effort CSS selectors for a specific service.
Selectors on big web apps drift over time, so the engine treats profiles as a
*hint*: if a profile selector fails, detection falls back to heuristics. Each
selector field may contain several comma-separated candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class UIProfile:
    """Best-effort selectors and behaviour for one LLM web UI."""

    name: str
    url_patterns: List[str]

    input_selector: str
    send_selector: str
    message_selector: str = ""
    assistant_selector: str = ""           # matches assistant messages only, if known
    streaming_selector: str = ""           # element present only while generating
    new_chat_selector: str = ""            # button to start a fresh conversation

    requires_login: bool = True
    input_kind: str = "auto"               # "auto" | "textarea" | "contenteditable"
    notes: str = ""


# --- Registry --------------------------------------------------------------

PROFILES: Dict[str, UIProfile] = {
    "chatgpt": UIProfile(
        name="ChatGPT",
        url_patterns=["chatgpt.com", "chat.openai.com"],
        input_selector='#prompt-textarea, div[contenteditable="true"], textarea',
        send_selector='button[data-testid="send-button"], button[aria-label*="Send" i]',
        message_selector='[data-message-author-role]',
        assistant_selector='[data-message-author-role="assistant"]',
        streaming_selector='button[data-testid="stop-button"], button[aria-label*="Stop" i]',
        new_chat_selector='a[data-testid="create-new-chat-button"], button[aria-label*="New chat" i], a[aria-label*="New chat" i]',
        requires_login=True,
        input_kind="contenteditable",
        notes="ChatGPT updates its DOM often; heuristics cover selector drift.",
    ),
    "claude": UIProfile(
        name="Claude",
        url_patterns=["claude.ai"],
        input_selector='div[contenteditable="true"].ProseMirror, div[contenteditable="true"], div[role="textbox"]',
        send_selector='button[aria-label="Send message"], button[aria-label*="Send" i]',
        message_selector='div.font-claude-message, [data-testid*="message" i]',
        assistant_selector='div.font-claude-message',
        streaming_selector='button[aria-label*="Stop" i]',
        new_chat_selector='a[aria-label*="New chat" i], button[aria-label*="New chat" i], a[href="/new"]',
        requires_login=True,
        input_kind="contenteditable",
        notes="Claude uses a ProseMirror editor; Shift+Enter inserts newlines.",
    ),
    "gemini": UIProfile(
        name="Gemini",
        url_patterns=["gemini.google.com"],
        input_selector='rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea',
        send_selector='button[aria-label*="Send" i], button.send-button, button[mat-icon-button][aria-label*="Send" i]',
        message_selector='message-content .markdown, message-content, .model-response-text, .markdown, [class*="model-response" i]',
        assistant_selector='message-content .markdown, message-content',
        streaming_selector='button[aria-label*="Stop" i], button[aria-label*="stop" i]',
        new_chat_selector='[data-test-id="new-chat-button"], button[aria-label*="New chat" i], a[aria-label*="New chat" i], expandable-button[aria-label*="New chat" i] button',
        requires_login=True,
        input_kind="contenteditable",
        notes="Google login is strict; persistent profile handles it after one login.",
    ),
    "grok": UIProfile(
        name="Grok",
        url_patterns=["grok.com", "x.com/i/grok"],
        input_selector='textarea, div[contenteditable="true"]',
        send_selector='button[type="submit"], button[aria-label*="Send" i]',
        message_selector='div[class*="message" i], div[class*="prose" i]',
        streaming_selector='button[aria-label*="Stop" i]',
        new_chat_selector='button[aria-label*="New" i], a[href="/" i]',
        requires_login=True,
        input_kind="auto",
    ),
    "openwebui": UIProfile(
        name="OpenWebUI",
        url_patterns=["localhost:3000", "127.0.0.1:3000"],
        input_selector='textarea#chat-input, textarea[placeholder*="message" i], textarea',
        send_selector='button#send-message-button, button[type="submit"], button[aria-label*="send" i]',
        message_selector='div.chat-assistant, div[class*="message" i]',
        assistant_selector='div.chat-assistant',
        streaming_selector='button[aria-label*="stop" i]',
        requires_login=False,
        input_kind="textarea",
    ),
    "lmstudio": UIProfile(
        name="LM Studio",
        url_patterns=["localhost:1234", "127.0.0.1:1234"],
        input_selector='textarea[placeholder*="message" i], #chat-input textarea, textarea',
        send_selector='button[type="submit"], .send-button, button[aria-label*="send" i]',
        message_selector='div[class*="message" i], .chat-message',
        requires_login=False,
        input_kind="textarea",
    ),
    "jan": UIProfile(
        name="Jan",
        url_patterns=["localhost:1337", "127.0.0.1:1337"],
        input_selector='textarea[placeholder*="message" i], textarea',
        send_selector='button[type="submit"], [data-testid*="send" i]',
        message_selector='div[class*="message" i]',
        requires_login=False,
        input_kind="textarea",
    ),
    "oobabooga": UIProfile(
        name="Text Generation WebUI",
        url_patterns=["localhost:7860", "127.0.0.1:7860", ":7860"],
        input_selector='#chat-input textarea, textarea[data-testid*="textbox" i], textarea',
        send_selector='button#Generate, button:has-text("Generate")',
        message_selector='.message-body, div[class*="message" i]',
        requires_login=False,
        input_kind="textarea",
    ),
}

# Friendly groupings for the GUI / CLI menus.
QUICK_PICKS = {
    "Local (no login)": {
        "OpenWebUI": "http://localhost:3000",
        "LM Studio": "http://localhost:1234",
        "Jan": "http://localhost:1337",
        "Oobabooga": "http://localhost:7860",
    },
    "Web (login once)": {
        "ChatGPT": "https://chatgpt.com",
        "Claude": "https://claude.ai",
        "Gemini": "https://gemini.google.com",
        "Grok": "https://grok.com",
    },
}


def detect_profile(url: str) -> Optional[UIProfile]:
    """Return the profile whose URL pattern matches, or None."""
    u = (url or "").lower()
    for profile in PROFILES.values():
        if any(pat.lower() in u for pat in profile.url_patterns):
            return profile
    return None


def get_profile(name_or_url: str) -> Optional[UIProfile]:
    """Look a profile up by registry key, display name, or URL."""
    if not name_or_url:
        return None
    key = name_or_url.strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    for profile in PROFILES.values():
        if profile.name.lower() == key:
            return profile
    return detect_profile(name_or_url)


# --- Backwards-compatible shims (older modules import these names) ---------

class ProfileRegistry:
    """Thin compatibility wrapper kept so older imports keep working."""

    PROFILES = PROFILES

    @classmethod
    def get_profile(cls, service_name: str) -> Optional[UIProfile]:
        return get_profile(service_name)

    @classmethod
    def detect_by_url(cls, url: str) -> Optional[UIProfile]:
        return detect_profile(url)

    @classmethod
    def list_available(cls) -> List[str]:
        return [p.name for p in PROFILES.values()]
