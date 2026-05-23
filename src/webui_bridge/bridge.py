import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .dom_scanner import DOMScanner
from .message_stream import MessageStream
from .network_sniffer import NetworkSniffer
from .theme_detector import Theme, ThemeDetector
from .utils import setup_logging

logger = logging.getLogger(__name__)


class UniversalWebUIBridge:
    def __init__(
        self,
        headless: bool = False,
        browser_type: str = "chromium",
        min_confidence: float = 2.0,
        auto_scroll: bool = True,
        use_existing_browser: bool = False,
        existing_browser_endpoint: Optional[str] = None,
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.min_confidence = min_confidence
        self.auto_scroll = auto_scroll
        self.use_existing_browser = use_existing_browser
        self.existing_browser_endpoint = existing_browser_endpoint or "http://localhost:9222"

        self._playwright: Optional[Any] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._owns_browser = True  # Whether we launched the browser or connected to existing

        self._scanner = DOMScanner(min_confidence=min_confidence)
        self._stream = MessageStream()
        self._sniffer = NetworkSniffer()

        self._connected = False
        self._api_mode = False
        self._input_selector: Optional[str] = None
        self._send_selector: Optional[str] = None
        self._chat_selector: Optional[str] = None

    # ------------------------------------------------------------------
    # URL Validation
    # ------------------------------------------------------------------

    def _validate_url(self, url: str) -> str:
        """Validate and correct URL format.
        
        Ensures URL has proper protocol prefix (http:// or https://).
        Common LLM services get automatic https:// prefix.
        """
        url = url.strip()
        
        # Already valid URL?
        if url.startswith(('http://', 'https://')):
            return url
        
        # Common services that should use https
        https_services = [
            'www.', 
            'chat.', 
            'claude.',
            'grok.',
            'chatgpt.',
            'openai.',
            'anthropic.',
            'llm.',
            'ai.',
            'app.',
            'platform.',
        ]
        
        # Check if it looks like it should be https
        needs_https = any(url.startswith(svc) for svc in https_services)
        needs_https = needs_https or '.' in url and not url.startswith('localhost')
        
        if needs_https:
            corrected = f"https://{url}"
            logger.info(f"URL corrected: {url} -> {corrected}")
            return corrected
        
        # Local development defaults to http
        if url.startswith('localhost') or url.startswith('127.'):
            corrected = f"http://{url}"
            logger.info(f"URL corrected: {url} -> {corrected}")
            return corrected
        
        # Default fallback
        corrected = f"https://{url}"
        logger.info(f"URL corrected (default): {url} -> {corrected}")
        return corrected

    # ------------------------------------------------------------------
    # Connection / lifecycle
    # ------------------------------------------------------------------

    async def connect(self, url: str) -> None:
        """Connect to the LLM WebUI.
        
        Can either launch a new browser or connect to an existing Chrome
        instance for reuse of logins and cookies.
        """
        # URL validation and correction
        url = self._validate_url(url)
        
        logger.info("Launching %s (headless=%s, use_existing=%s)", 
                   self.browser_type, self.headless, self.use_existing_browser)
        
        self._playwright = await async_playwright().start()

        if self.use_existing_browser:
            # Connect to existing Chrome
            await self._connect_to_existing_browser()
        else:
            # Launch new browser
            await self._launch_new_browser()

        logger.info("Navigating to %s", url)
        await self._page.goto(url, wait_until="networkidle")

        await self._detect_elements()
        await self._stream.start(self._page)
        await self._sniffer.attach(self._page)

        self._connected = True
        logger.info("Bridge connected to %s", url)

        try:
            theme = await self.detect_theme()
            logger.info("Page theme on connect: %s", theme)
        except Exception as exc:
            logger.warning("Theme detection on connect failed: %s", exc)

    async def _launch_new_browser(self) -> None:
        """Launch a new browser instance."""
        browser_launcher = getattr(self._playwright, self.browser_type)
        self._browser = await browser_launcher.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._owns_browser = True
        logger.info("Launched new browser instance (no persistence)")
        
    async def open_manual_login_tab(self, url: str) -> None:
        """Open a separate browser window for manual login."""
        import webbrowser
        import subprocess
        import time
        
        # Open the URL in user's default browser
        webbrowser.open(url)
        
        st = ""
        if 'streamlit' in globals():
            import streamlit as st
            st.info(f"Opened {url} in your browser. Please log in, then return here and click 'I've Logged In'")
        
        return True

    async def _connect_to_existing_browser(self) -> None:
        """Connect to an existing Chrome instance via CDP."""
        try:
            # Connect via Chrome DevTools Protocol
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.existing_browser_endpoint
            )
            
            # Use existing browser context (keeps cookies, logins, extensions)
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                logger.info("Connected to existing browser context with %d pages", 
                           len(self._context.pages))
            else:
                self._context = await self._browser.new_context()
                logger.info("Created new context in existing browser")
            
            # Get or create page
            pages = self._context.pages
            if pages:
                self._page = pages[0]
                logger.info("Using existing page: %s", self._page.url)
            else:
                self._page = await self._context.new_page()
                logger.info("Created new page in existing browser")
            
            self._owns_browser = False
            logger.info("Successfully connected to existing Chrome at %s", 
                       self.existing_browser_endpoint)
            
        except Exception as e:
            logger.error("Failed to connect to existing browser: %s", e)
            logger.warning("Falling back to launching new browser...")
            self.use_existing_browser = False
            await self._launch_new_browser()

    async def close(self) -> None:
        """Close the bridge, but don't close existing browser if we didn't launch it."""
        self._connected = False
        if self._sniffer:
            await self._sniffer.detach()
        if self._stream:
            await self._stream.stop(self._page)
        
        if self._owns_browser:
            # Only close if we launched the browser
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        else:
            logger.info("Leaving existing browser open (not closing)")
        
        if self._playwright:
            await self._playwright.stop()
        
        logger.info("Bridge closed")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def send(self, message: str, retries: int = 3) -> None:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        
        # If in API mode, send via API
        if self._api_mode:
            result = await self._sniffer.send_via_api(message)
            if result is not None:
                logger.info("Message sent via API (%d chars)", len(message))
                return
            else:
                logger.warning("API send failed, falling back to UI automation")
        
        # Fallback to UI automation
        for attempt in range(1, retries + 1):
            try:
                await self._send_once(message)
                if self.auto_scroll:
                    await self._stream.scroll_to_bottom(self._page)
                return
            except Exception as exc:
                logger.warning("Send attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt < retries:
                    await self._heal()
                else:
                    raise RuntimeError(f"Failed to send message after {retries} attempts") from exc

    async def is_generating(self) -> bool:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        return await self._stream.is_generating(self._page)

    async def wait_for_response(
        self,
        timeout: float = 60.0,
        wait_for_generation_complete: bool = False,
    ) -> Optional[str]:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")

        deadline = asyncio.get_event_loop().time() + timeout

        msgs_before = await self._stream.get_messages(self._page)
        assistant_before = len([m for m in msgs_before if m.get("author") == "assistant"])

        msg = await self._stream.wait_for_new_assistant_message(
            self._page,
            previous_count=assistant_before,
            timeout=timeout,
        )

        if msg and wait_for_generation_complete:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining > 0:
                await self._stream.wait_for_generation_complete(
                    self._page,
                    timeout=remaining,
                )

        return msg["text"] if msg else None

    async def stream_response(
        self,
        timeout: float = 60.0,
    ) -> AsyncGenerator[str, None]:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")

        async for token in self._stream.stream_response(self._page, timeout=timeout):
            yield token

    async def get_messages(self) -> list[dict]:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        return await self._stream.get_messages(self._page)

    async def get_streaming_messages(self) -> list[dict]:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        return await self._stream.get_streaming_messages(self._page)

    # ------------------------------------------------------------------
    # API Mode methods
    # ------------------------------------------------------------------

    async def try_enable_direct_api(self, observation_time: float = 5.0) -> bool:
        """
        Attempt to detect and enable direct API mode.
        
        Intercepts network traffic for a short period to detect
        the backend chat API endpoint.
        
        Args:
            observation_time: How long to observe requests before deciding (seconds)
            
        Returns:
            True if API mode was enabled, False otherwise.
        """
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        
        logger.info("Observing network traffic for %s seconds to detect API endpoint...", observation_time)
        await asyncio.sleep(observation_time)
        
        endpoint = await self._sniffer.detect_chat_endpoint(min_candidates=1)
        if endpoint:
            self._api_mode = True
            logger.info("Direct API mode enabled: %s", endpoint)
            return True
        
        logger.info("Could not detect API endpoint, using UI automation")
        return False
    
    async def disable_direct_api(self) -> None:
        """Disable API mode and return to UI automation."""
        self._api_mode = False
        logger.info("Direct API mode disabled, using UI automation")
    
    @property
    def is_api_mode(self) -> bool:
        """Check if currently using direct API mode."""
        return self._api_mode and self._sniffer.get_detected_endpoint() is not None
    
    async def get_detected_api_endpoint(self) -> Optional[str]:
        """Get the currently detected API endpoint."""
        return self._sniffer.get_detected_endpoint()

    async def detect_theme(self) -> str:
        if not self._connected or not self._page:
            raise RuntimeError("Bridge not connected. Call connect() first.")
        detector = ThemeDetector()
        theme = await detector.detect(self._page)
        logger.info("Detected theme: %s", theme.value)
        return theme.value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _detect_elements(self) -> None:
        result = await self._scanner.full_scan(self._page)
        self._input_selector = self._scanner.get_input_selector()
        self._send_selector = self._scanner.get_send_selector()
        self._chat_selector = self._scanner.get_chat_selector()
        self._stream.chat_selector = self._chat_selector

        if not self._input_selector:
            raise RuntimeError("Could not detect chat input element")
        if not self._send_selector:
            logger.warning("Send button not detected — may need manual override or network fallback")

    async def _send_once(self, message: str) -> None:
        page = self._page
        input_selector = self._input_selector

        input_el = page.locator(input_selector).first
        await input_el.wait_for(state="visible", timeout=5000)
        await input_el.fill(message)
        await asyncio.sleep(0.05)

        if self._send_selector:
            send_el = page.locator(self._send_selector).first
            await send_el.click()
        else:
            await input_el.press("Enter")

        logger.info("Message sent (%d chars)", len(message))

    async def _heal(self) -> None:
        logger.info("Healing DOM references...")
        try:
            await self._detect_elements()
            await self._stream.reset(self._page)
            await self._stream.start(self._page)
        except Exception as exc:
            logger.error("Heal failed: %s", exc)
            raise
