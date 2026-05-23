"""
Browser session management for the Universal WebUI Bridge.

Uses a Playwright *persistent context* backed by an on-disk profile directory.
This is the whole trick behind "stay logged in": the profile (cookies,
localStorage, IndexedDB, service workers) lives on disk, so once the user logs
in to a service, that login is reused on every future run of the bridge.

There is deliberately no cookie capture/replay and no Chrome debug-port dance.
The browser the user logs into IS the browser the bridge automates.
"""

from __future__ import annotations

import logging
import subprocess as _sp
import sys as _sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path.home() / ".universal_webui_bridge" / "profile"


def _kill_lingering_chrome(profile_dir: Path) -> None:
    """Kill any browser processes that are holding this profile directory open."""
    profile_str = str(profile_dir.resolve())
    if _sys.platform == "win32":
        try:
            _sp.run(
                ["wmic", "process", "where",
                 f'commandline like "%{profile_str}%" and name like "%chrome%"',
                 "delete"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        try:
            _sp.run(
                ["wmic", "process", "where",
                 f'commandline like "%{profile_str}%" and name like "%msedge%"',
                 "delete"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        try:
            _sp.run(
                ["wmic", "process", "where",
                 f'commandline like "%{profile_str}%" and name like "%chromium%"',
                 "delete"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
    else:
        for signal in ("SIGTERM", "SIGKILL"):
            try:
                _sp.run(["pkill", "-f", "-{}".format(signal), profile_str],
                       capture_output=True, timeout=5)
            except Exception:
                pass


def _clean_profile_locks(profile_dir: Path) -> None:
    """Remove Chrome/Chromium lock files from the profile directory.

    If a previous browser session crashed or was killed without cleanup, these
    files prevent a new session from starting with "Opening in existing browser
    session" / "SingletonLock" errors.
    """
    lock_files = [
        "SingletonLock",
        "SingletonSocket",
        "SingletonCookie",
        "Lockfile",
        ".lock",
    ]
    for name in lock_files:
        lock_path = profile_dir / name
        if lock_path.exists():
            try:
                lock_path.unlink()
                logger.debug("Removed stale lock: %s", lock_path)
            except OSError:
                pass
    # Also check for a "lockfile" in parent (sometimes Chromium writes it one level up)
    parent_lock = profile_dir.parent / "SingletonLock"
    if parent_lock.exists():
        try:
            parent_lock.unlink()
        except OSError:
            pass


@dataclass
class BrowserResult:
    """Outcome of a browser operation."""

    success: bool
    error: str = ""
    hint: str = ""


class BrowserSession:
    """A long-lived browser backed by a persistent on-disk profile."""

    def __init__(self, profile_dir: Optional[Path] = None, headless: bool = False):
        self.profile_dir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
        self.headless = headless
        self._pw: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.channel: str = ""

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def is_open(self) -> bool:
        return self._context is not None and self._page is not None

    async def start(self) -> BrowserResult:
        """Launch the persistent browser. Idempotent within a session."""
        if self.is_open:
            return BrowserResult(success=True)

        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # Clean up stale locks and lingering processes from a previous crash.
        _clean_profile_locks(self.profile_dir)
        _kill_lingering_chrome(self.profile_dir)

        try:
            self._pw = await async_playwright().start()
        except Exception as exc:  # pragma: no cover - environment dependent
            return BrowserResult(
                success=False,
                error=f"Could not start Playwright: {exc}",
                hint="Run: pip install playwright && python -m playwright install chromium",
            )

        common = dict(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1280,860",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Prefer the user's real Chrome/Edge: better with logins, less likely to
        # trip bot-detection than bundled Chromium. Fall back down the list.
        last_error: Optional[Exception] = None
        for channel in ("chrome", "msedge", None):
            try:
                kwargs = dict(common)
                if channel:
                    kwargs["channel"] = channel
                self._context = await self._pw.chromium.launch_persistent_context(**kwargs)
                self.channel = channel or "chromium"
                logger.info(
                    "Browser launched (channel=%s, profile=%s)", self.channel, self.profile_dir
                )
                break
            except Exception as exc:
                last_error = exc
                logger.warning("Launch with channel=%s failed: %s", channel, exc)

        if self._context is None:
            return BrowserResult(
                success=False,
                error=f"Could not launch a browser: {last_error}",
                hint=(
                    "Install Google Chrome, or run: python -m playwright install chromium. "
                    "If you see a 'profile in use' / 'SingletonLock' error, close any "
                    "browser window the bridge opened earlier and try again."
                ),
            )

        # A persistent context opens with one page; keep exactly one.
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        for extra in pages[1:]:
            try:
                await extra.close()
            except Exception:
                pass

        return BrowserResult(success=True)

    async def goto(self, url: str, timeout: float = 60.0) -> BrowserResult:
        """Navigate the active page to a URL."""
        if not self._page:
            return BrowserResult(success=False, error="Browser not started")
        try:
            # domcontentloaded, not networkidle: chat apps hold connections open
            # (SSE / websockets) so networkidle frequently never fires.
            await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            return BrowserResult(success=True)
        except Exception as exc:
            msg = str(exc)
            hint = "Check the URL and your internet connection."
            if "ERR_CONNECTION_REFUSED" in msg:
                hint = "Nothing is running there. If it's a local LLM, start it first."
            elif "ERR_NAME_NOT_RESOLVED" in msg:
                hint = "That address does not exist. Check the URL for typos."
            elif "Timeout" in msg:
                hint = "The page took too long to load. Try again."
            return BrowserResult(success=False, error=f"Could not open {url}: {msg}", hint=hint)

    async def current_url(self) -> str:
        return self._page.url if self._page else ""

    async def close(self) -> None:
        """Close the browser. The profile directory is persisted automatically."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = None
        self._page = None
        self._pw = None
        logger.info("Browser closed; profile saved at %s", self.profile_dir)
