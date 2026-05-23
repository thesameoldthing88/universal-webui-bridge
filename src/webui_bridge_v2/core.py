"""
LLMBridge - the public API.

Typical use:

    bridge = LLMBridge()
    status = await bridge.connect("https://chatgpt.com")
    if status.state is BridgeState.NEEDS_LOGIN:
        # ... user logs in inside the browser window ...
        status = await bridge.finish_login()
    reply = await bridge.chat("Hello!")
    await bridge.close()

The browser uses a persistent on-disk profile, so a service only needs to be
logged into once - every later run reuses that session.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .browser import BrowserSession
from .engine import ChatEngine
from .profiles import detect_profile

logger = logging.getLogger(__name__)


class BridgeState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    NEEDS_LOGIN = "needs_login"
    READY = "ready"
    ERROR = "error"


@dataclass
class BridgeStatus:
    state: BridgeState = BridgeState.IDLE
    url: str = ""
    service: str = ""
    message: str = ""
    hint: str = ""


def normalize_url(url: str) -> str:
    """Add a scheme if the user left it off."""
    url = (url or "").strip()
    if not url:
        return url
    if re.match(r"^[a-zA-Z]+://", url):
        return url
    local = url.startswith(("localhost", "127.", "0.0.0.0", "192.168.", "10.", "[::1]"))
    return ("http://" if local else "https://") + url


class LLMBridge:
    """Connects to one web LLM and exchanges messages with it."""

    def __init__(self, profile_dir: Optional[Path] = None, headless: bool = False):
        self._browser = BrowserSession(profile_dir=profile_dir, headless=headless)
        self._engine: Optional[ChatEngine] = None
        self._status = BridgeStatus()
        self.history: List[dict] = []

    # -- properties ---------------------------------------------------------

    @property
    def status(self) -> BridgeStatus:
        return self._status

    @property
    def state(self) -> BridgeState:
        return self._status.state

    @property
    def is_ready(self) -> bool:
        return self._status.state is BridgeState.READY

    # -- connection ---------------------------------------------------------

    async def connect(self, url: str) -> BridgeStatus:
        """Open the browser, navigate, and try to get ready for chatting."""
        url = normalize_url(url)
        profile = detect_profile(url)
        self._status = BridgeStatus(
            state=BridgeState.CONNECTING,
            url=url,
            service=profile.name if profile else "Custom",
        )

        try:
            started = await self._browser.start()
            if not started.success:
                return self._fail(started.error, started.hint)

            nav = await self._browser.goto(url)
            if not nav.success:
                return self._fail(nav.error, nav.hint)

            self._engine = ChatEngine(self._browser.page, profile)

            # Short wait: a local LLM or an already-logged-in service is ready now.
            if await self._engine.wait_until_ready(timeout=12.0):
                return await self._become_ready()

            # Otherwise the user probably needs to log in (or finish a prompt)
            # inside the visible browser window.
            self._status.state = BridgeState.NEEDS_LOGIN
            self._status.message = (
                "Couldn't find the chat box yet. If a login or welcome page is "
                "showing in the browser window, finish that, then continue."
            )
            self._status.hint = "You only have to log in once - it is remembered next time."
            return self._status
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("connect failed")
            return self._fail(f"Unexpected error: {exc}", "Try again.")

    async def finish_login(self, timeout: float = 45.0) -> BridgeStatus:
        """Call after the user has logged in / dismissed any landing page."""
        if not self._engine:
            return self._fail("Not connected", "Call connect() first.")
        try:
            if await self._engine.wait_until_ready(timeout=timeout):
                return await self._become_ready()
            self._status.state = BridgeState.NEEDS_LOGIN
            self._status.message = "Still can't see the chat box."
            self._status.hint = (
                "Make sure the chat page is fully open in the browser window "
                "(not a login or settings page), then try again."
            )
            return self._status
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("finish_login failed")
            return self._fail(f"Unexpected error: {exc}", "Try again.")

    async def _become_ready(self) -> BridgeStatus:
        assert self._engine is not None
        if not await self._engine.detect():
            self._status.state = BridgeState.NEEDS_LOGIN
            self._status.message = "Found the page but not the chat input."
            self._status.hint = "Open the actual chat screen, then continue."
            return self._status
        self._status.state = BridgeState.READY
        self._status.message = f"Ready - connected to {self._status.service}."
        self._status.hint = ""
        return self._status

    def _fail(self, message: str, hint: str = "") -> BridgeStatus:
        self._status.state = BridgeState.ERROR
        self._status.message = message
        self._status.hint = hint
        return self._status

    # -- messaging ----------------------------------------------------------

    async def chat(self, message: str, timeout: float = 120.0) -> str:
        """Send a message and return the model's complete reply."""
        self._require_ready()
        assert self._engine is not None
        self.history.append({"role": "user", "content": message})
        reply = await self._engine.chat(message, timeout=timeout)
        self.history.append({"role": "assistant", "content": reply})
        return reply

    async def send(self, message: str) -> None:
        """Send a message without waiting for the reply."""
        self._require_ready()
        assert self._engine is not None
        self.history.append({"role": "user", "content": message})
        await self._engine.send(message)

    async def wait_for_reply(self, timeout: float = 120.0) -> str:
        """Wait for and return the reply to the last sent message."""
        self._require_ready()
        assert self._engine is not None
        reply = await self._engine.wait_for_reply(timeout=timeout)
        self.history.append({"role": "assistant", "content": reply})
        return reply

    async def reset_conversation(self) -> bool:
        """Best-effort: click the web LLM's 'new chat' button and clear local history.

        Used by the HTTP server before the first /v1/chat/completions request,
        so an agent's framing doesn't collide with whatever was in the tab.
        Returns True if a reset was attempted (and the input was found again),
        False if no reset selector is known or detection failed.
        """
        self._require_ready()
        assert self._engine is not None
        ok = await self._engine.reset_conversation()
        if ok:
            self.history.clear()
        return ok

    def _require_ready(self) -> None:
        if self._status.state is not BridgeState.READY:
            raise RuntimeError(
                f"Bridge is not ready (state: {self._status.state.value}). "
                "Call connect() (and finish_login() if needed) first."
            )

    # -- lifecycle ----------------------------------------------------------

    async def close(self) -> None:
        """Close the browser. The login profile is saved for next time."""
        await self._browser.close()
        self._engine = None
        self._status = BridgeStatus(state=BridgeState.IDLE)
