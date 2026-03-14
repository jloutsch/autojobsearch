"""Base class for Chrome browser-based job sources.

Launches a real Chrome instance with the user's profile and connects via
Playwright CDP. This allows scraping bot-protected sites (Wellfound, Indeed,
Remote.co) that block headless browsers and plain HTTP requests.

Chrome sources are opt-in (disabled by default) and gracefully skip when
Chrome isn't available, in Docker, or in CI.
"""

import logging
import os
import random
import subprocess
import threading
import time
from pathlib import Path

import requests as http_requests

from playwright.sync_api import sync_playwright

from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# Only one Chrome instance at a time across all ChromeBrowserSource subclasses
_chrome_lock = threading.Lock()

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]

CDP_PORT = 9222
CDP_STARTUP_TIMEOUT = 15
PROFILE_NAME = "AutoJobSearch"


def _find_chrome() -> str | None:
    for path in CHROME_PATHS:
        if Path(path).exists():
            return path
    return None


def _is_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("DOCKER_CONTAINER") == "true"


def _is_ci() -> bool:
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _chrome_sources_enabled() -> bool:
    env_val = os.environ.get("CHROME_SOURCES_ENABLED", "").lower()
    if env_val in ("true", "1", "yes"):
        return True
    if env_val in ("false", "0", "no"):
        return False
    # Fall back to profile.json
    try:
        from user_profile import get_profile
        return get_profile().get("chrome_sources_enabled", False)
    except Exception:
        return False


def _wait_for_cdp(port: int, timeout: int = CDP_STARTUP_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = http_requests.get(f"http://localhost:{port}/json/version", timeout=2)
            if resp.status_code == 200:
                return True
        except http_requests.ConnectionError:
            pass
        time.sleep(0.5)
    return False


class ChromeBrowserSource(BaseSource):
    """Abstract base for sources that need a real Chrome browser."""

    name = "chrome_base"

    # Subclasses set this
    _page = None
    _browser = None
    _playwright = None

    def safe_collect(self) -> list[JobListing]:
        if not _chrome_sources_enabled():
            logger.info(f"[{self.name}] Chrome sources disabled — skipping")
            return []

        if _is_docker():
            logger.info(f"[{self.name}] Running in Docker — skipping Chrome source")
            return []

        if _is_ci():
            logger.info(f"[{self.name}] Running in CI — skipping Chrome source")
            return []

        chrome_path = _find_chrome()
        if not chrome_path:
            logger.warning(f"[{self.name}] Chrome not found — skipping")
            return []

        if not _chrome_lock.acquire(blocking=False):
            logger.info(f"[{self.name}] Another Chrome source is running — skipping")
            return []

        process = None
        try:
            process = self._launch_chrome(chrome_path)
            if not _wait_for_cdp(CDP_PORT):
                logger.warning(f"[{self.name}] Chrome CDP not ready after {CDP_STARTUP_TIMEOUT}s — skipping")
                return []

            self._connect()
            jobs = self.collect()
            logger.info(f"[{self.name}] Collected {len(jobs)} listings")
            return jobs

        except Exception as e:
            logger.error(f"[{self.name}] Failed to collect: {e}")
            return []
        finally:
            self._disconnect()
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            _chrome_lock.release()

    def _launch_chrome(self, chrome_path: str) -> subprocess.Popen:
        # Use a dedicated data directory — Chrome rejects --user-data-dir
        # pointing to the default profile location when debugging is enabled.
        user_data_dir = str(Path.home() / ".autojobsearch-chrome")

        cmd = [
            chrome_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        logger.info(f"[{self.name}] Launching Chrome with CDP on port {CDP_PORT}")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _connect(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(
            f"http://localhost:{CDP_PORT}"
        )
        context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self._page = context.new_page()

    def _disconnect(self):
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None

    def _navigate(self, url: str, wait_range: tuple[float, float] = (1.0, 3.0)):
        delay = random.uniform(*wait_range)
        time.sleep(delay)
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

    def _wait_for_selector(self, selector: str, timeout: int = 10000):
        self._page.wait_for_selector(selector, timeout=timeout)

    def _get_page_html(self) -> str:
        return self._page.content()

    def _scroll_to_bottom(self, max_scrolls: int = 5, pause: float = 1.5):
        for _ in range(max_scrolls):
            prev_height = self._page.evaluate("document.body.scrollHeight")
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(pause)
            new_height = self._page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break
