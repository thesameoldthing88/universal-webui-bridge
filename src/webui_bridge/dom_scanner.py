import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from playwright.async_api import Page

from .theme_detector import Theme, ThemeDetector
from .utils import score_chat_container, score_input_element, score_send_button

logger = logging.getLogger(__name__)


@dataclass
class KnownUIConfig:
    """Configuration for a known UI framework."""
    name: str
    input_selectors: List[str]
    send_button_selectors: List[str]
    chat_container_selectors: List[str]
    detection_score: float = 10.0  # Higher score means higher priority


# Registry of known UI configurations
KNOWN_UI_REGISTRY: Dict[str, KnownUIConfig] = {
    "openwebui": KnownUIConfig(
        name="OpenWebUI",
        input_selectors=['textarea[placeholder*="message" i]'],
        send_button_selectors=['button[type="submit"]', '[data-testid="send-button"]'],
        chat_container_selectors=['.chat-container', '#chat-messages', '[data-testid="chat-messages"]'],
    ),
    "oobabooga": KnownUIConfig(
        name="Oobabooga Text Generation WebUI",
        input_selectors=['#chat-input textarea', '#chat-input input'],
        send_button_selectors=['#chat-input button', '.send-button'],
        chat_container_selectors=['.chat-messages', '#chat-messages'],
    ),
    "lmstudio": KnownUIConfig(
        name="LM Studio",
        input_selectors=['[data-testid="chat-input"]', 'textarea[placeholder*="Ask" i]'],
        send_button_selectors=['[data-testid="send-button"]', 'button:has(svg)'],
        chat_container_selectors=['[data-testid="chat-messages"]', '.message-list'],
    ),
    "jan": KnownUIConfig(
        name="Jan",
        input_selectors=['#chat-input textarea', '[data-testid="input-message"]'],
        send_button_selectors=['#chat-input button:last-child', '[data-testid="send-message"]'],
        chat_container_selectors=['#chat-messages', '.message-list'],
    ),
    "huggingface": KnownUIConfig(
        name="Hugging Face Chat",
        input_selectors=['textarea[data-target*="input"]', '[data-target*="Input"]'],
        send_button_selectors=['button:has-text("Send")', '[data-testid="send" i]'],
        chat_container_selectors=['[data-target*="Chat"]', '.chat-wrapper'],
    ),
}


class DOMScanner:
    """
    Enhanced DOM scanner with support for:
    - Known UI configurations
    - Modal dialog detection
    - Multi-language input detection
    - Dynamic UI handling
    - Custom selector overrides
    """

    def __init__(
        self,
        min_confidence: float = 2.0,
        custom_config: Optional[KnownUIConfig] = None,
        use_known_uis: bool = True,
    ):
        self.min_confidence = min_confidence
        self._custom_config = custom_config
        self._use_known_uis = use_known_uis
        
        self._input_info: Optional[dict] = None
        self._send_info: Optional[dict] = None
        self._chat_info: Optional[dict] = None
        self._theme_detector = ThemeDetector()
        self._theme: Theme = Theme.UNKNOWN
        
        # Detection history for self-healing
        self._detection_history: List[Dict] = []
        self._max_history = 10
        
        # Known UI detection
        self._detected_ui_type: Optional[str] = None

    # ------------------------------------------------------------------
    # Configuration API
    # ------------------------------------------------------------------

    def set_custom_config(self, config: KnownUIConfig) -> None:
        """Set a custom UI configuration for detection."""
        self._custom_config = config
        logger.info("Custom UI config set: %s", config.name)

    def register_known_ui(self, ui_type: str, config: KnownUIConfig) -> None:
        """Register a new known UI configuration."""
        KNOWN_UI_REGISTRY[ui_type] = config
        logger.info("Registered known UI: %s", ui_type)

    # ------------------------------------------------------------------
    # Enhanced Detection API
    # ------------------------------------------------------------------

    async def detect_known_ui(self, page: Page) -> Optional[str]:
        """Detect if page matches a known UI framework."""
        if self._custom_config:
            return await self._try_config(page, self._custom_config, "custom")
        
        if not self._use_known_uis:
            return None
            
        # Limit iterations for performance
        max_uis_to_check = min(len(KNOWN_UI_REGISTRY), 3)
        checked = 0
        for ui_type, config in KNOWN_UI_REGISTRY.items():
            if checked >= max_uis_to_check:
                break
            match = await self._try_config(page, config, ui_type)
            if match:
                return match
            checked += 1
        return None

    async def _try_config(self, page: Page, config: KnownUIConfig, ui_type: str) -> Optional[str]:
        """Try to match a specific UI configuration."""
        # Check if at least 2 out of 3 element types are detected
        detected = 0
        
        # Check input
        for selector in config.input_selectors:
            try:
                element = await page.locator(selector).first
                if await element.is_visible(timeout=100):
                    detected += 1
                    break
            except Exception:
                continue
        
        # Check send button
        for selector in config.send_button_selectors:
            try:
                element = await page.locator(selector).first
                if await element.is_visible(timeout=100):
                    detected += 1
                    break
            except Exception:
                continue
        
        # Check chat container
        for selector in config.chat_container_selectors:
            try:
                element = await page.locator(selector).first
                if await element.is_visible(timeout=100):
                    detected += 1
                    break
            except Exception:
                continue
        
        if detected >= 2:
            self._detected_ui_type = ui_type
            logger.info("Detected known UI: %s (score: %d/3)", config.name, detected)
            return ui_type
        return None

    async def detect_input(self, page: Page) -> Optional[dict]:
        """Detect input element, with multi-language support."""
        # First try known UI config
        if self._detected_ui_type and self._detected_ui_type in KNOWN_UI_REGISTRY:
            config = KNOWN_UI_REGISTRY[self._detected_ui_type]
            result = await self._try_selectors(page, config.input_selectors, "input")
            if result:
                return result
        
        # Fallback to heuristic detection
        candidates = await page.evaluate(self._input_detection_js())
        if not candidates:
            candidates = []
        best = self._pick_best(candidates, lambda c: self._apply_theme_adjustment(score_input_element(c)))
        
        if best and best["score"] >= self.min_confidence:
            self._input_info = best
            self._update_history("input", best)
            logger.info(
                "Detected input %s (score=%.1f, selector=%s)",
                best["tag"],
                best["score"],
                best["selector"],
            )
            return best
        
        logger.warning("No input element detected above confidence %.1f", self.min_confidence)
        return None

    async def detect_send_button(self, page: Page, input_info: Optional[dict] = None) -> Optional[dict]:
        """Enhanced send button detection with modal dialog support."""
        # Check if input is inside a modal
        modal_info = await self._detect_modal_context(page)
        
        input_rect = input_info.get("rect") if input_info else None
        
        # First try known UI config
        if self._detected_ui_type and self._detected_ui_type in KNOWN_UI_REGISTRY:
            config = KNOWN_UI_REGISTRY[self._detected_ui_type]
            result = await self._try_selectors(page, config.send_button_selectors, "send")
            if result:
                if input_rect:
                    result["rect"] = input_rect  # Ensure rect is present
                return result
        
        # Check for modal-specific send button
        if isinstance(modal_info, dict):
            modal_send = await self._detect_modal_send_button(page, modal_info)
            if modal_send:
                return modal_send
        
        # Fallback to heuristic detection
        candidates = await page.evaluate(self._send_button_detection_js(), input_rect)
        if not candidates:
            candidates = []
        best = self._pick_best(candidates, lambda c: self._apply_theme_adjustment(score_send_button(c, input_rect)))
        
        if best and best["score"] >= self.min_confidence:
            self._send_info = best
            self._update_history("send", best)
            logger.info(
                "Detected send button (score=%.1f, selector=%s)",
                best["score"],
                best["selector"],
            )
            return best
        
        logger.warning("No send button detected above confidence %.1f", self.min_confidence)
        return None

    async def detect_chat_log(self, page: Page) -> Optional[dict]:
        """Detect chat container, including in modals."""
        # First try known UI config
        if self._detected_ui_type and self._detected_ui_type in KNOWN_UI_REGISTRY:
            config = KNOWN_UI_REGISTRY[self._detected_ui_type]
            result = await self._try_selectors(page, config.chat_container_selectors, "chat")
            if result:
                return result
        
        # Check for modal chat containers
        modal_chat = await self._detect_modal_chat_container(page)
        if modal_chat:
            return modal_chat
        
        # Fallback to heuristic detection
        candidates = await page.evaluate(self._chat_log_detection_js())
        if not candidates:
            candidates = []
        best = self._pick_best(candidates, lambda c: self._apply_theme_adjustment(score_chat_container(c)))
        
        if best and best["score"] >= self.min_confidence:
            self._chat_info = best
            self._update_history("chat", best)
            logger.info(
                "Detected chat container (score=%.1f, selector=%s)",
                best["score"],
                best["selector"],
            )
            return best
        
        logger.warning("No chat container detected above confidence %.1f", self.min_confidence)
        return None

    async def full_scan(self, page: Page) -> dict:
        """Enhanced full scan with known UI detection."""
        self._theme = await self._theme_detector.detect(page)
        logger.info("Detected page theme: %s", self._theme.value)
        
        # Try to detect known UI first
        ui_type = await self.detect_known_ui(page)
        
        result = {
            "input": await self.detect_input(page),
            "send_button": await self.detect_send_button(page, self._input_info),
            "chat_log": await self.detect_chat_log(page),
            "theme": self._theme.value,
            "ui_type": ui_type or "unknown",
        }
        
        # Check for modal dialogs
        modal_info = await self._detect_modal_context(page)
        if modal_info:
            result["modal"] = modal_info
        
        missing = [k for k, v in result.items() if v is None and k not in ["modal", "ui_type"]]
        if missing:
            logger.warning("Full scan incomplete — missing: %s", ", ".join(missing))
        else:
            logger.info("Full scan complete — all elements detected (UI: %s)", ui_type or "unknown")
        return result

    # ------------------------------------------------------------------
    # Modal Dialog Support
    # ------------------------------------------------------------------

    async def _detect_modal_context(self, page: Page) -> Optional[dict]:
        """Detect if there's an active modal dialog."""
        return await page.evaluate("""
            () => {
                // Common modal/dialog selectors
                const modalSelectors = [
                    '[role="dialog"]',
                    '[role="alertdialog"]',
                    '[class*="modal" i]',
                    '[class*="dialog" i]',
                    '.chakra-modal__content',  // Chakra UI
                    '.mantine-Modal-content', // Mantine
                    '.ant-modal-content',      // Ant Design
                    '[class*="MuiDialog-paper"]', // Material-UI
                ];
                
                for (const selector of modalSelectors) {
                    const modals = document.querySelectorAll(selector);
                    for (const modal of modals) {
                        const style = window.getComputedStyle(modal);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return {
                                selector: selector,
                                element: modal.tagName.toLowerCase(),
                                hasInput: !!modal.querySelector('textarea, input'),
                            };
                        }
                    }
                }
                return null;
            }
        """)

    async def _detect_modal_send_button(self, page: Page, modal_info: dict) -> Optional[dict]:
        """Detect send button inside a modal context."""
        selector = modal_info.get("selector", "")
        return await page.evaluate(f"""
            (modalSelector) => {{
                const modal = document.querySelector(modalSelector);
                if (!modal) return null;
                
                // Look for send/submit button inside modal
                const buttons = modal.querySelectorAll('button, [role="button"], input[type="submit"]');
                const candidates = [];
                
                buttons.forEach(el => {{
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return;
                    
                    const text = (el.textContent || '').toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    
                    // Score based on text content
                    let score = 0;
                    if (['send', 'submit', 'save', 'confirm', 'ok'].some(k => text.includes(k) || ariaLabel.includes(k))) score += 5;
                    if (['cancel', 'close', 'dismiss'].some(k => text.includes(k) || ariaLabel.includes(k))) score -= 3;
                    
                    if (score > 2) {{
                        candidates.push({{
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent || '',
                            selector: modalSelector + ' ' + (el.id ? '#' + el.id : el.tagName.toLowerCase()),
                            score: score,
                            rect: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}},
                        }});
                    }}
                }});
                
                return candidates.length > 0 ? candidates[0] : null;
            }}
        """, selector)

    async def _detect_modal_chat_container(self, page: Page) -> Optional[dict]:
        """Detect chat container inside a modal."""
        return await page.evaluate("""
            () => {
                const modalSelectors = [
                    '[role="dialog"]',
                    '[class*="modal" i]',
                ];
                
                for (const selector of modalSelectors) {
                    const modal = document.querySelector(selector);
                    if (!modal) continue;
                    
                    // Look for chat-like containers inside modal
                    const containers = modal.querySelectorAll('*');
                    for (const el of containers) {
                        const text = el.textContent || '';
                        const hasScrollbar = el.scrollHeight > el.clientHeight;
                        const childCount = el.children.length;
                        
                        if (childCount >= 2 && text.length > 50 && hasScrollbar) {
                            return {
                                tag: el.tagName.toLowerCase(),
                                selector: selector + ' ' + el.tagName.toLowerCase(),
                            };
                        }
                    }
                }
                return null;
            }
        """)

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    async def _try_selectors(self, page: Page, selectors: List[str], element_type: str) -> Optional[dict]:
        """Try to find element using known selectors."""
        for selector in selectors:
            try:
                # Try using evaluate first for mock compatibility
                result = await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return null;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return null;
                        return {{
                            selector: '{selector}',
                            tag: el.tagName.toLowerCase(),
                            rect: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}},
                            score: 10.0
                        }};
                    }}
                """)
                if result:
                    return result
            except Exception:
                continue
        return None

    def _update_history(self, element_type: str, info: dict) -> None:
        """Update detection history for self-healing."""
        self._detection_history.append({
            "type": element_type,
            "selector": info.get("selector"),
            "timestamp": logging.time if hasattr(logging, 'time') else 0,
        })
        if len(self._detection_history) > self._max_history:
            self._detection_history.pop(0)

    def get_fallback_selector(self, element_type: str) -> Optional[str]:
        """Get most reliable selector from history."""
        relevant = [h for h in self._detection_history if h["type"] == element_type]
        if relevant:
            # Return most recent
            return relevant[-1]["selector"]
        return None

    def get_input_selector(self) -> Optional[str]:
        """Get input selector, with fallback."""
        if self._input_info:
            return self._input_info["selector"]
        return self.get_fallback_selector("input")

    def get_send_selector(self) -> Optional[str]:
        """Get send button selector, with fallback."""
        if self._send_info:
            return self._send_info["selector"]
        return self.get_fallback_selector("send")

    def get_chat_selector(self) -> Optional[str]:
        """Get chat container selector, with fallback."""
        if self._chat_info:
            return self._chat_info["selector"]
        return self.get_fallback_selector("chat")

    def get_detected_ui_type(self) -> Optional[str]:
        """Get the detected UI framework type."""
        return self._detected_ui_type

    # ------------------------------------------------------------------
    # JavaScript snippets (Enhanced)
    # ------------------------------------------------------------------

    def _input_detection_js(self) -> str:
        return """
        () => {
            function getSelector(el) {
                if (el.id) return '#' + el.id;
                const tag = el.tagName.toLowerCase();
                const cls = Array.from(el.classList).slice(0,2).join('.');
                const attr = el.getAttribute('placeholder') ? '[placeholder]' : '';
                return tag + (cls ? '.' + cls : '') + attr;
            }
            const candidates = [];
            const selectors = [
                'textarea',
                'input[type="text"]',
                'input[type="search"]',
                'input:not([type])',
                '[contenteditable="true"]',
                '[role="textbox"]',
                // Multi-language placeholders
                '[placeholder*="message" i]',
                '[placeholder*="ask" i]',
                '[placeholder*="输入"]',  // Chinese
                '[placeholder*="입력"]',  // Korean
                '[placeholder*="入力"]',  // Japanese
                '[placeholder*="entrée" i]', // French
                '[placeholder*="eingabe" i]', // German
            ];
            
            document.querySelectorAll(selectors.join(', ')).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                if (style.pointerEvents === 'none') return; // Skip disabled elements
                
                // Multi-language placeholder detection
                const placeholder = el.placeholder || el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                
                candidates.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    role: el.getAttribute('role') || '',
                    placeholder: placeholder,
                    ariaLabel: ariaLabel,
                    contenteditable: el.isContentEditable,
                    visible: true,
                    area: rect.width * rect.height,
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    selector: getSelector(el)
                });
            });
            return candidates;
        }
        """

    def _send_button_detection_js(self) -> str:
        return """
        (inputRect) => {
            function getSelector(el) {
                if (el.id) return '#' + el.id;
                const tag = el.tagName.toLowerCase();
                const cls = Array.from(el.classList).slice(0,2).join('.');
                return tag + (cls ? '.' + cls : '');
            }
            function hasSvgChild(el) {
                return el.querySelector('svg') !== null || el.tagName.toLowerCase() === 'svg';
            }
            const candidates = [];
            // Standard button selectors (CSS compatible)
            const selectors = [
                'button',
                '[role="button"]',
                'a',
                'input[type="submit"]',
            ];
            
            document.querySelectorAll(selectors.join(', ')).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                if (style.pointerEvents === 'none') return;
                
                // Multi-language text detection in JavaScript (not via CSS selector)
                const text = (el.textContent || '').trim().substring(0, 30);
                const ariaLabel = el.getAttribute('aria-label') || '';
                
                candidates.push({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    text: text,
                    ariaLabel: ariaLabel,
                    visible: true,
                    hasSvgChild: hasSvgChild(el),
                    hasClickListener: true,
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    selector: getSelector(el)
                });
            });
            return candidates;
        }
        """

    def _chat_log_detection_js(self) -> str:
        return """
        () => {
            function getSelector(el) {
                if (el.id) return '#' + el.id;
                const tag = el.tagName.toLowerCase();
                const cls = Array.from(el.classList).slice(0,2).join('.');
                return tag + (cls ? '.' + cls : '');
            }
            const candidates = [];
            const selectors = [
                'div', 'section', 'article', 'main', 'ul', 'ol',
                '[class*="chat" i]',
                '[class*="message" i]',
                '[class*="conversation" i]',
                '[role="log"]',
                '[role="region"][aria-label*="chat" i]',
            ];
            
            document.querySelectorAll(selectors.join(', ')).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) return;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                const childCount = el.children.length;
                if (childCount < 2) return;
                
                const text = el.innerText || '';
                const textDensity = text.length / (rect.width * rect.height + 1);
                const overflowY = style.overflowY;
                const hasScrollbar = (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                
                // Check for chat-like content patterns
                const hasMessages = /message|chat|conversation|assistant|user/i.test(el.className + ' ' + el.id);
                const mutationCount = el.__mutationCount || 0;
                
                candidates.push({
                    tag: el.tagName.toLowerCase(),
                    visible: true,
                    childCount: childCount,
                    hasScrollbar: hasScrollbar,
                    textDensity: textDensity,
                    hasMessages: hasMessages,
                    mutationCount: mutationCount,
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    selector: getSelector(el)
                });
            });
            return candidates;
        }
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_best(candidates: list[dict], scorer: Any) -> Optional[dict]:
        best: Optional[dict] = None
        best_score = -1.0
        for c in candidates:
            score = scorer(c)
            c["score"] = score
            if score > best_score:
                best_score = score
                best = c
        if best:
            best["score"] = best_score
        return best

    def _apply_theme_adjustment(self, score: float) -> float:
        """Slightly boost scores for dark themes where contrast heuristics may differ."""
        if self._theme == Theme.DARK:
            return score + 0.2
        return score
