"""
Chat engine: the part that actually talks to a web LLM page.

Three jobs:
  * detect()          - find the chat input (and send button) on the page
  * send()            - put a message into the input and submit it
  * wait_for_reply()  - wait for the model to finish and return its text

Detection prefers a known profile's selectors, then falls back to heuristics.
Found elements are tagged with a `data-bridge-*` attribute so they can be
re-addressed reliably even on React/Vue apps with hashed class names.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from playwright.async_api import Page

from .profiles import UIProfile

logger = logging.getLogger(__name__)

INPUT_MARKER = '[data-bridge-input="1"]'
SEND_MARKER = '[data-bridge-send="1"]'


# --- JavaScript snippets ---------------------------------------------------

_JS_FIND_INPUT = r"""
(preferred) => {
  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 60 || r.height < 14) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    if (el.disabled || el.getAttribute('aria-hidden') === 'true') return false;
    return true;
  }
  function kindOf(el) {
    const t = el.tagName.toLowerCase();
    return (t === 'textarea' || t === 'input') ? 'textarea' : 'contenteditable';
  }
  document.querySelectorAll('[data-bridge-input]').forEach(e => e.removeAttribute('data-bridge-input'));

  for (const sel of (preferred || [])) {
    let els = [];
    try { els = [...document.querySelectorAll(sel)]; } catch (e) { continue; }
    for (const el of els) {
      if (visible(el)) {
        el.setAttribute('data-bridge-input', '1');
        return { found: true, kind: kindOf(el), via: 'profile' };
      }
    }
  }
  const all = [...document.querySelectorAll('textarea, input, [contenteditable], [role="textbox"]')];
  let best = null, bestScore = -1;
  for (const el of all) {
    const t = el.tagName.toLowerCase();
    if (t === 'input') {
      const ty = (el.getAttribute('type') || 'text').toLowerCase();
      if (!['text', 'search', 'url', ''].includes(ty)) continue;
    } else if (t !== 'textarea' && !el.isContentEditable && el.getAttribute('role') !== 'textbox') {
      continue;
    }
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    let score = r.width + (r.top / window.innerHeight) * 350;
    const hint = ((el.getAttribute('placeholder') || '') + ' ' +
                  (el.getAttribute('aria-label') || '')).toLowerCase();
    if (/message|ask|send|chat|prompt|reply|type|talk|question/.test(hint)) score += 600;
    if (score > bestScore) { bestScore = score; best = el; }
  }
  if (best) {
    best.setAttribute('data-bridge-input', '1');
    return { found: true, kind: kindOf(best), via: 'heuristic' };
  }
  return { found: false };
}
"""

_JS_FIND_SEND = r"""
(preferred) => {
  function clickable(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    return true;
  }
  document.querySelectorAll('[data-bridge-send]').forEach(e => e.removeAttribute('data-bridge-send'));

  for (const sel of (preferred || [])) {
    let els = [];
    try { els = [...document.querySelectorAll(sel)]; } catch (e) { continue; }
    for (const el of els) {
      if (clickable(el)) { el.setAttribute('data-bridge-send', '1'); return { found: true, via: 'profile' }; }
    }
  }
  const input = document.querySelector('[data-bridge-input="1"]');
  const ir = input ? input.getBoundingClientRect() : null;
  const btns = [...document.querySelectorAll('button, [role="button"], input[type="submit"]')];
  let best = null, bestScore = -1;
  for (const el of btns) {
    if (!clickable(el)) continue;
    const r = el.getBoundingClientRect();
    const label = ((el.getAttribute('aria-label') || '') + ' ' + (el.textContent || '') + ' ' +
                   (el.getAttribute('data-testid') || '') + ' ' + (el.getAttribute('title') || '')).toLowerCase();
    let score = 0;
    if (/send|submit/.test(label)) score += 500;
    if (/stop|cancel|attach|upload|voice|mic|search|menu|close|delete|copy/.test(label)) score -= 500;
    if ((el.getAttribute('type') || '') === 'submit') score += 120;
    if (el.querySelector('svg')) score += 40;
    if (ir) {
      const dy = Math.abs((r.top + r.height / 2) - (ir.top + ir.height / 2));
      if (dy < 90) score += 220;
      score -= dy;
    }
    if (score > bestScore) { bestScore = score; best = el; }
  }
  if (best && bestScore > 0) {
    best.setAttribute('data-bridge-send', '1');
    return { found: true, via: 'heuristic' };
  }
  return { found: false };
}
"""

_JS_COUNT = r"""
(sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return 0; } }
"""

_JS_SET_BASELINE = r"""
() => { window.__bridgeBaseline = document.body.innerText || ''; return true; }
"""

# Polls many candidate selectors at once, plus a body-text diff fallback that
# kicks in for layouts none of the selectors match.
_JS_GATHER = r"""
({selectors, streamSel, lastSent}) => {
  const baseline = window.__bridgeBaseline || '';
  const items = [];
  for (const sel of (selectors || [])) {
    if (sel === '__body__') {
      const t = document.body.innerText || '';
      // Longest common prefix.
      let p = 0;
      while (p < baseline.length && p < t.length &&
             baseline.charCodeAt(p) === t.charCodeAt(p)) p++;
      // Longest common suffix (within the part after the prefix).
      let s = 0;
      while (
        s < (baseline.length - p) &&
        s < (t.length - p) &&
        baseline.charCodeAt(baseline.length - 1 - s) === t.charCodeAt(t.length - 1 - s)
      ) s++;
      let delta = t.slice(p, t.length - s);
      // Strip a leading echo of the user's own message.
      if (lastSent && delta.trimStart().startsWith(lastSent)) {
        const idx = delta.indexOf(lastSent);
        delta = delta.slice(idx + lastSent.length);
      }
      delta = delta.replace(/\n{3,}/g, '\n\n').trim();
      items.push({sel: '__body__', count: 0, text: delta});
      continue;
    }
    let nodes = [];
    try { nodes = [...document.querySelectorAll(sel)]; } catch (e) {}
    const last = nodes.length ? nodes[nodes.length - 1] : null;
    const text = last ? (last.innerText || last.textContent || '').trim() : '';
    items.push({sel, count: nodes.length, text});
  }
  let streaming = false;
  if (streamSel) {
    try {
      const s = document.querySelector(streamSel);
      streaming = !!(s && s.getBoundingClientRect().width > 0);
    } catch (e) {}
  }
  return {streaming, items};
}
"""

# Broad pool of "this might match a message block" CSS selectors. Tried in
# order, so put the most precise patterns first.
_GENERIC_MESSAGE_SELECTORS = [
    "[data-message-author-role]",
    '[class*="model-response" i]',
    "message-content",                # Gemini custom element
    "bard-response",                  # older Gemini
    '[class*="response" i]',
    '[class*="reply" i]',
    '[class*="answer" i]',
    '[class*="markdown" i]',
    ".markdown",
    '[class*="message" i]',
    '[class*="msg" i]',
    '[class*="turn" i]',
    '[class*="bubble" i]',
    "[role='listitem']",
    "article",
]


@dataclass
class Detection:
    """What detection found on the page."""

    input_kind: str = "textarea"        # "textarea" | "contenteditable"
    input_via: str = ""                 # "profile" | "heuristic"
    has_send_button: bool = False
    message_selector: str = ""


class ChatEngine:
    """Drives one chat page: detect -> send -> wait for reply."""

    def __init__(self, page: Page, profile: Optional[UIProfile] = None):
        self.page = page
        self.profile = profile
        self.detection = Detection()
        self._last_sent = ""

    # -- detection ----------------------------------------------------------

    def _input_candidates(self) -> List[str]:
        if self.profile and self.profile.input_selector:
            return [s.strip() for s in self.profile.input_selector.split(",") if s.strip()]
        return []

    def _send_candidates(self) -> List[str]:
        if self.profile and self.profile.send_selector:
            return [s.strip() for s in self.profile.send_selector.split(",") if s.strip()]
        return []

    async def _locate_input(self) -> Optional[dict]:
        """Run input detection once. Returns the JS result dict or None."""
        try:
            return await self.page.evaluate(_JS_FIND_INPUT, self._input_candidates())
        except Exception as exc:
            logger.debug("input detection error: %s", exc)
            return None

    async def wait_until_ready(self, timeout: float = 20.0) -> bool:
        """Poll for the chat input to appear (covers slow loads and login)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await self._locate_input()
            if result and result.get("found"):
                return True
            await asyncio.sleep(0.6)
        return False

    async def reset_conversation(self) -> bool:
        """Best-effort: click the profile's 'new chat' button.

        Returns True if a candidate selector was found, was clicked, and the
        chat input is detectable afterwards. Returns False if no candidate
        matched (we silently keep using the current conversation in that case).
        """
        if not self.profile or not self.profile.new_chat_selector:
            logger.info("No new_chat_selector for this profile; skipping reset")
            return False

        candidates = [s.strip() for s in self.profile.new_chat_selector.split(",")
                      if s.strip()]
        clicked = False
        for sel in candidates:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() == 0:
                    continue
                if not await loc.is_visible(timeout=500):
                    continue
                await loc.click(timeout=3000)
                clicked = True
                logger.info("Clicked new-chat: %s", sel)
                break
            except Exception as exc:
                logger.debug("new-chat candidate %r failed: %s", sel, exc)
                continue

        if not clicked:
            logger.info("No visible new-chat button; staying in current conversation")
            return False

        # Give the page a moment to load the fresh chat and re-find the input.
        await asyncio.sleep(1.0)
        self._last_sent = ""
        self.detection = Detection()
        ready = await self.wait_until_ready(timeout=10.0)
        if ready:
            await self.detect()
        return ready

    async def detect(self) -> bool:
        """Resolve the input, send button, and message selector. Returns success."""
        result = await self._locate_input()
        if not result or not result.get("found"):
            logger.warning("Could not find a chat input on the page")
            return False

        self.detection.input_kind = result.get("kind", "textarea")
        if self.profile and self.profile.input_kind in ("textarea", "contenteditable"):
            self.detection.input_kind = self.profile.input_kind
        self.detection.input_via = result.get("via", "")

        send = await self._locate_send()
        self.detection.has_send_button = bool(send and send.get("found"))

        self.detection.message_selector = await self._resolve_message_selector()
        logger.info(
            "Detected: input(%s,%s) send=%s messages=%r",
            self.detection.input_kind,
            self.detection.input_via,
            self.detection.has_send_button,
            self.detection.message_selector,
        )
        return True

    async def _locate_send(self) -> Optional[dict]:
        try:
            return await self.page.evaluate(_JS_FIND_SEND, self._send_candidates())
        except Exception as exc:
            logger.debug("send detection error: %s", exc)
            return None

    async def _resolve_message_selector(self) -> str:
        """Pick a CSS selector that currently matches message blocks."""
        candidates: List[str] = []
        if self.profile:
            if self.profile.assistant_selector:
                candidates.append(self.profile.assistant_selector)
            if self.profile.message_selector:
                candidates.append(self.profile.message_selector)
        candidates.extend(_GENERIC_MESSAGE_SELECTORS)

        best_sel, best_count = "", 0
        for sel in candidates:
            try:
                count = await self.page.evaluate(_JS_COUNT, sel)
            except Exception:
                count = 0
            # A profile selector that matches anything wins immediately.
            if count > 0 and self.profile and sel in (
                self.profile.assistant_selector,
                self.profile.message_selector,
            ):
                return sel
            if count > best_count:
                best_sel, best_count = sel, count
        return best_sel

    # -- sending ------------------------------------------------------------

    async def send(self, text: str) -> None:
        """Type a message into the input and submit it."""
        if not text.strip():
            raise ValueError("Cannot send an empty message")

        # Re-tag the input every time: chat frameworks often re-render it.
        result = await self._locate_input()
        if not result or not result.get("found"):
            raise RuntimeError("Chat input is no longer on the page")
        kind = self.detection.input_kind or result.get("kind", "textarea")

        # Snapshot the page text BEFORE the user message hits the DOM. This is
        # the baseline wait_for_reply diffs against when no selector matches.
        try:
            await self.page.evaluate(_JS_SET_BASELINE)
        except Exception:
            pass

        inp = self.page.locator(INPUT_MARKER).first
        await inp.scroll_into_view_if_needed(timeout=5000)
        await inp.click(timeout=5000)

        if kind == "textarea":
            await inp.fill(text, timeout=5000)
        else:
            # contenteditable: clear, then type. Shift+Enter keeps newlines from
            # submitting the message early.
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Delete")
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if i > 0:
                    await self.page.keyboard.press("Shift+Enter")
                if line:
                    await self.page.keyboard.type(line)

        await self.page.wait_for_timeout(200)  # let the framework enable Send

        send = await self._locate_send()
        clicked = False
        if send and send.get("found"):
            try:
                await self.page.locator(SEND_MARKER).first.click(timeout=4000)
                clicked = True
            except Exception as exc:
                logger.debug("send-button click failed, will use Enter: %s", exc)
        if not clicked:
            await inp.press("Enter")

        self._last_sent = text.strip()
        logger.info("Message sent (%d chars, send_button=%s)", len(text), clicked)

    # -- receiving ----------------------------------------------------------

    async def wait_for_reply(self, timeout: float = 120.0) -> str:
        """Wait for the model to finish responding and return its text.

        Polls many candidate selectors in parallel each tick, plus a body-text
        diff against a baseline taken right after the user message was sent.
        That body-diff is the safety net for sites whose DOM doesn't match any
        known selector - it catches whatever new text appears on the page.
        """
        # Build the candidate selector list (best signals first).
        candidates: List[str] = []
        if self.profile:
            if self.profile.assistant_selector:
                candidates.append(self.profile.assistant_selector)
            if self.profile.message_selector:
                candidates.append(self.profile.message_selector)
        candidates.extend(_GENERIC_MESSAGE_SELECTORS)
        seen = set()
        candidates = [c for c in candidates if c and not (c in seen or seen.add(c))]
        candidates.append("__body__")

        stream_sel = self.profile.streaming_selector if self.profile else ""
        last_sent = self._last_sent

        async def gather() -> dict:
            try:
                return await self.page.evaluate(
                    _JS_GATHER,
                    {"selectors": candidates, "streamSel": stream_sel, "lastSent": last_sent},
                )
            except Exception:
                return {"streaming": False, "items": []}

        deadline = time.monotonic() + timeout
        stable_for = 2.5
        min_wait = time.monotonic() + 0.8

        last_text = ""
        stable_since: Optional[float] = None
        while time.monotonic() < deadline:
            result = await gather()
            streaming = bool(result.get("streaming"))
            items = result.get("items", [])

            # Pick the first (highest-priority) candidate that has usable text:
            # non-empty, not the user's own echoed message.
            pick = ""
            for it in items:
                text = (it.get("text") or "").strip()
                if not text:
                    continue
                if self._last_sent and text == self._last_sent:
                    continue
                pick = text
                break

            if pick and pick == last_text and not streaming and time.monotonic() >= min_wait:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= stable_for:
                    return pick
            elif pick:
                stable_since = None
                last_text = pick

            await asyncio.sleep(0.4)

        if last_text:
            return last_text
        return (
            "(No reply detected - the page may use an unusual layout. Try again, "
            "or report which site this is so a profile can be added.)"
        )

    async def chat(self, text: str, timeout: float = 120.0) -> str:
        """Send a message and return the complete reply."""
        await self.send(text)
        return await self.wait_for_reply(timeout)
