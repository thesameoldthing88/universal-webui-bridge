import asyncio
import json
import logging
import pathlib
from typing import AsyncGenerator, Optional

from playwright.async_api import Page

from .utils import classify_message_author, extract_code_blocks, extract_markdown_sections

logger = logging.getLogger(__name__)


class MessageStream:
    def __init__(self, chat_selector: Optional[str] = None):
        self.chat_selector = chat_selector
        self._observer_injected = False

    # ------------------------------------------------------------------
    # Injection / lifecycle
    # ------------------------------------------------------------------

    async def inject(self, page: Page) -> None:
        script_path = pathlib.Path(__file__).with_suffix("").parent / "js" / "observer.js"
        script = script_path.read_text(encoding="utf-8")
        await page.add_init_script(script)
        self._observer_injected = True
        logger.info("Observer init-script injected")

    async def start(self, page: Page) -> bool:
        if not self._observer_injected:
            await self.inject(page)
        result = await page.evaluate(
            "(selector) => window.__webui_bridge_start(selector)",
            self.chat_selector,
        )
        if result:
            logger.info("Message observer started")
        else:
            logger.warning("Message observer failed to start — container not found")
        return result

    async def stop(self, page: Page) -> None:
        await page.evaluate("() => window.__webui_bridge_stop()")
        logger.info("Message observer stopped")

    async def reset(self, page: Page) -> None:
        await page.evaluate("() => window.__webui_bridge_clear()")
        logger.info("Message buffer cleared")

    async def scroll_to_bottom(self, page: Page) -> None:
        await page.evaluate(
            "(selector) => window.__webui_bridge_scroll_to_bottom(selector)",
            self.chat_selector,
        )
        logger.debug("Scrolled chat container to bottom")

    # ------------------------------------------------------------------
    # Reading messages
    # ------------------------------------------------------------------

    async def get_messages(self, page: Page) -> list[dict]:
        raw = await page.evaluate("() => window.__webui_bridge_get_messages()")
        return raw

    async def last_assistant_message(self, page: Page) -> Optional[dict]:
        msgs = await self.get_messages(page)
        for m in reversed(msgs):
            if m.get("author") == "assistant":
                return m
        return None

    async def get_last_message_with_blocks(self, page: Page) -> Optional[dict]:
        """Return the last assistant message enriched with extracted code blocks and markdown sections.

        Args:
            page: The Playwright Page instance.

        Returns:
            The last assistant message dict with two extra keys:
            - ``code_blocks``: result of :func:`extract_code_blocks`.
            - ``markdown_sections``: result of :func:`extract_markdown_sections`.
            Returns ``None`` when no assistant message exists.
        """
        msg = await self.last_assistant_message(page)
        if msg is None:
            return None
        text = msg.get("text", "")
        msg["code_blocks"] = extract_code_blocks(text)
        msg["markdown_sections"] = extract_markdown_sections(text)
        return msg

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_response(
        self,
        page: Page,
        timeout: float = 60.0,
        poll_interval: float = 0.15,
    ) -> AsyncGenerator[str, None]:
        deadline = asyncio.get_event_loop().time() + timeout
        previous_text: dict[str, str] = {}

        while asyncio.get_event_loop().time() < deadline:
            msgs = await self.get_messages(page)
            assistant_msgs = [m for m in msgs if m.get("author") == "assistant"]

            if not assistant_msgs:
                await asyncio.sleep(poll_interval)
                continue

            for msg in assistant_msgs:
                msg_id = msg.get("id")
                current_text = msg.get("text", "")

                if msg_id not in previous_text:
                    previous_text[msg_id] = current_text
                    yield current_text
                elif len(current_text) > len(previous_text[msg_id]):
                    delta = current_text[len(previous_text[msg_id]):]
                    previous_text[msg_id] = current_text
                    yield delta

            # Clean up entries for messages that no longer exist
            current_ids = {m.get("id") for m in assistant_msgs}
            previous_text = {k: v for k, v in previous_text.items() if k in current_ids}

            await asyncio.sleep(poll_interval)

        logger.info("Stream ended or timed out after %.1fs", timeout)

    async def get_streaming_messages(self, page: Page) -> list[dict]:
        msgs = await self.get_messages(page)
        return [m for m in msgs if m.get("streaming") is True]

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    async def wait_for_new_assistant_message(
        self,
        page: Page,
        previous_count: int = 0,
        timeout: float = 60.0,
        poll_interval: float = 0.2,
    ) -> Optional[dict]:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            msgs = await self.get_messages(page)
            assistant_msgs = [m for m in msgs if m.get("author") == "assistant"]
            if len(assistant_msgs) > previous_count:
                return assistant_msgs[-1]
            await asyncio.sleep(poll_interval)
        logger.warning("Timeout waiting for new assistant message")
        return None

    # ------------------------------------------------------------------
    # Generation detection
    # ------------------------------------------------------------------

    async def is_generating(self, page: Page) -> bool:
        return await page.evaluate("() => window.__webui_bridge_is_generating()")

    async def wait_for_generation_complete(
        self,
        page: Page,
        timeout: float = 60.0,
        poll_interval: float = 0.2,
    ) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if not await self.is_generating(page):
                return True
            await asyncio.sleep(poll_interval)
        logger.warning("Timeout waiting for generation to complete")
        return False
