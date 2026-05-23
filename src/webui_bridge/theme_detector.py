import logging
from enum import Enum
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class Theme(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    UNKNOWN = "unknown"


class ThemeDetector:
    """Detects the current color theme of a web page via JavaScript evaluation."""

    async def detect(self, page: Page) -> Theme:
        """Run all detection heuristics and return the most likely theme."""
        # 1. CSS media query
        media_dark = await self._detect_via_media_query(page)
        if media_dark is True:
            logger.debug("Theme detected via media query: dark")
            return Theme.DARK
        if media_dark is False:
            logger.debug("Theme detected via media query: light")
            return Theme.LIGHT

        # 2. HTML / body class names
        class_theme = await self._detect_via_class_names(page)
        if class_theme is not None:
            logger.debug("Theme detected via class names: %s", class_theme)
            return class_theme

        # 3. data-theme attribute
        attr_theme = await self._detect_via_data_attribute(page)
        if attr_theme is not None:
            logger.debug("Theme detected via data-theme attribute: %s", attr_theme)
            return attr_theme

        # 4. Background brightness heuristic
        brightness_theme = await self._detect_via_brightness(page)
        if brightness_theme is not None:
            logger.debug("Theme detected via brightness: %s", brightness_theme)
            return brightness_theme

        logger.debug("Unable to detect theme")
        return Theme.UNKNOWN

    # ------------------------------------------------------------------
    # JS-based heuristics
    # ------------------------------------------------------------------

    async def _detect_via_media_query(self, page: Page) -> Optional[bool]:
        try:
            return await page.evaluate(
                """() => {
                    const mql = window.matchMedia('(prefers-color-scheme: dark)');
                    if (mql.matches) return true;
                    const mqlLight = window.matchMedia('(prefers-color-scheme: light)');
                    if (mqlLight.matches) return false;
                    return null;
                }"""
            )
        except Exception as exc:
            logger.warning("Media query detection failed: %s", exc)
            return None

    async def _detect_via_class_names(self, page: Page) -> Optional[Theme]:
        try:
            result = await page.evaluate(
                """() => {
                    const targets = [document.documentElement, document.body];
                    const darkTokens = ['dark', 'theme-dark'];
                    const lightTokens = ['light', 'theme-light'];
                    for (const el of targets) {
                        if (!el) continue;
                        const classes = Array.from(el.classList).map(c => c.toLowerCase());
                        for (const token of darkTokens) {
                            if (classes.includes(token)) return 'dark';
                        }
                        for (const token of lightTokens) {
                            if (classes.includes(token)) return 'light';
                        }
                    }
                    return null;
                }"""
            )
            if result == "dark":
                return Theme.DARK
            if result == "light":
                return Theme.LIGHT
            return None
        except Exception as exc:
            logger.warning("Class-name detection failed: %s", exc)
            return None

    async def _detect_via_data_attribute(self, page: Page) -> Optional[Theme]:
        try:
            result = await page.evaluate(
                """() => {
                    const targets = [document.documentElement, document.body];
                    for (const el of targets) {
                        if (!el) continue;
                        const val = (el.getAttribute('data-theme') || '').toLowerCase();
                        if (val === 'dark' || val === 'theme-dark') return 'dark';
                        if (val === 'light' || val === 'theme-light') return 'light';
                    }
                    return null;
                }"""
            )
            if result == "dark":
                return Theme.DARK
            if result == "light":
                return Theme.LIGHT
            return None
        except Exception as exc:
            logger.warning("Data-attribute detection failed: %s", exc)
            return None

    async def _detect_via_brightness(self, page: Page) -> Optional[Theme]:
        try:
            avg_brightness = await page.evaluate(
                """() => {
                    function rgbFromString(str) {
                        const m = str.match(/\\d+/g);
                        if (!m || m.length < 3) return null;
                        return [parseInt(m[0],10), parseInt(m[1],10), parseInt(m[2],10)];
                    }
                    function luminance(r, g, b) {
                        // Relative luminance per WCAG 2.1
                        const rs = r / 255;
                        const gs = g / 255;
                        const bs = b / 255;
                        const R = rs <= 0.03928 ? rs / 12.92 : Math.pow((rs + 0.055) / 1.055, 2.4);
                        const G = gs <= 0.03928 ? gs / 12.92 : Math.pow((gs + 0.055) / 1.055, 2.4);
                        const B = bs <= 0.03928 ? bs / 12.92 : Math.pow((bs + 0.055) / 1.055, 2.4);
                        return 0.2126 * R + 0.7152 * G + 0.0722 * B;
                    }
                    const selectors = ['html', 'body', 'main', '#app', '#root', '[class*="container"]'];
                    let total = 0;
                    let count = 0;
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        const style = window.getComputedStyle(el);
                        const bg = style.backgroundColor;
                        const rgb = rgbFromString(bg);
                        if (!rgb) continue;
                        total += luminance(rgb[0], rgb[1], rgb[2]);
                        count += 1;
                    }
                    return count > 0 ? total / count : null;
                }"""
            )
            if avg_brightness is None:
                return None
            # Threshold based on WCAG: 0.0 = black, 1.0 = white
            return Theme.DARK if avg_brightness < 0.35 else Theme.LIGHT
        except Exception as exc:
            logger.warning("Brightness detection failed: %s", exc)
            return None
