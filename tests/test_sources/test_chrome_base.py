"""Tests for sources/chrome_base.py — Chrome browser base class."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from models import JobListing
from sources.chrome_base import (
    ChromeBrowserSource,
    _find_chrome,
    _is_ci,
    _is_docker,
    _chrome_sources_enabled,
    _wait_for_cdp,
    _chrome_lock,
    CDP_PORT,
)


class ConcreteSource(ChromeBrowserSource):
    """Concrete subclass for testing."""

    name = "test_chrome"

    def collect(self):
        return [
            JobListing(
                title="Test Job",
                company="TestCo",
                url="https://example.com/job/1",
                source=self.name,
            )
        ]


class FailingSource(ChromeBrowserSource):
    """Source that raises during collect."""

    name = "failing_chrome"

    def collect(self):
        raise RuntimeError("Scraping failed")


# --- Skip logic tests ---


@patch("sources.chrome_base._chrome_sources_enabled", return_value=False)
def test_safe_collect_skips_when_disabled(mock_enabled):
    source = ConcreteSource()
    assert source.safe_collect() == []


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=True)
def test_safe_collect_skips_in_docker(mock_docker, mock_enabled):
    source = ConcreteSource()
    assert source.safe_collect() == []


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=False)
@patch("sources.chrome_base._is_ci", return_value=True)
def test_safe_collect_skips_in_ci(mock_ci, mock_docker, mock_enabled):
    source = ConcreteSource()
    assert source.safe_collect() == []


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=False)
@patch("sources.chrome_base._is_ci", return_value=False)
@patch("sources.chrome_base._find_chrome", return_value=None)
def test_safe_collect_skips_no_chrome(mock_find, mock_ci, mock_docker, mock_enabled):
    source = ConcreteSource()
    assert source.safe_collect() == []


# --- Chrome detection tests ---


def test_is_docker_false_normally():
    assert _is_docker() is False


@patch.dict("os.environ", {"CI": "true"})
def test_is_ci_true():
    assert _is_ci() is True


@patch.dict("os.environ", {"GITHUB_ACTIONS": "true"})
def test_is_ci_github_actions():
    assert _is_ci() is True


@patch.dict("os.environ", {}, clear=True)
def test_is_ci_false():
    assert _is_ci() is False


def test_find_chrome_returns_none_for_invalid_paths():
    with patch("sources.chrome_base.CHROME_PATHS", ["/nonexistent/chrome"]):
        assert _find_chrome() is None


# --- Config tests ---


@patch.dict("os.environ", {"CHROME_SOURCES_ENABLED": "true"})
def test_chrome_enabled_via_env():
    assert _chrome_sources_enabled() is True


@patch.dict("os.environ", {"CHROME_SOURCES_ENABLED": "false"})
def test_chrome_disabled_via_env():
    assert _chrome_sources_enabled() is False


@patch.dict("os.environ", {}, clear=True)
@patch("user_profile.get_profile", return_value={"chrome_sources_enabled": True})
def test_chrome_enabled_via_profile(mock_profile):
    assert _chrome_sources_enabled() is True


@patch.dict("os.environ", {}, clear=True)
@patch("user_profile.get_profile", return_value={})
def test_chrome_disabled_by_default(mock_profile):
    assert _chrome_sources_enabled() is False


# --- Full lifecycle tests ---


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=False)
@patch("sources.chrome_base._is_ci", return_value=False)
@patch("sources.chrome_base._find_chrome", return_value="/usr/bin/google-chrome")
@patch("sources.chrome_base._wait_for_cdp", return_value=True)
def test_safe_collect_full_lifecycle(mock_cdp, mock_find, mock_ci, mock_docker, mock_enabled):
    source = ConcreteSource()

    mock_process = MagicMock()
    mock_page = MagicMock()
    mock_browser = MagicMock()
    mock_browser.contexts = [MagicMock()]
    mock_browser.contexts[0].new_page.return_value = mock_page
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser

    with patch.object(source, "_launch_chrome", return_value=mock_process), \
         patch("sources.chrome_base.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.start.return_value = mock_pw_instance
        jobs = source.safe_collect()

    assert len(jobs) == 1
    assert jobs[0].title == "Test Job"
    mock_process.terminate.assert_called_once()


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=False)
@patch("sources.chrome_base._is_ci", return_value=False)
@patch("sources.chrome_base._find_chrome", return_value="/usr/bin/google-chrome")
@patch("sources.chrome_base._wait_for_cdp", return_value=True)
def test_safe_collect_cleans_up_on_error(mock_cdp, mock_find, mock_ci, mock_docker, mock_enabled):
    source = FailingSource()

    mock_process = MagicMock()
    mock_page = MagicMock()
    mock_browser = MagicMock()
    mock_browser.contexts = [MagicMock()]
    mock_browser.contexts[0].new_page.return_value = mock_page
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser

    with patch.object(source, "_launch_chrome", return_value=mock_process), \
         patch("sources.chrome_base.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.start.return_value = mock_pw_instance
        jobs = source.safe_collect()

    assert jobs == []
    mock_process.terminate.assert_called_once()


@patch("sources.chrome_base._chrome_sources_enabled", return_value=True)
@patch("sources.chrome_base._is_docker", return_value=False)
@patch("sources.chrome_base._is_ci", return_value=False)
@patch("sources.chrome_base._find_chrome", return_value="/usr/bin/google-chrome")
@patch("sources.chrome_base._wait_for_cdp", return_value=False)
def test_safe_collect_skips_cdp_timeout(mock_cdp, mock_find, mock_ci, mock_docker, mock_enabled):
    source = ConcreteSource()

    mock_process = MagicMock()
    with patch.object(source, "_launch_chrome", return_value=mock_process):
        jobs = source.safe_collect()

    assert jobs == []
    mock_process.terminate.assert_called_once()


# --- Navigation helpers ---


def test_navigate_calls_goto_with_delay():
    source = ConcreteSource()
    source._page = MagicMock()

    with patch("sources.chrome_base.time.sleep") as mock_sleep:
        source._navigate("https://example.com", wait_range=(0.1, 0.2))

    source._page.goto.assert_called_once_with(
        "https://example.com", wait_until="domcontentloaded", timeout=30000
    )
    mock_sleep.assert_called_once()
    delay = mock_sleep.call_args[0][0]
    assert 0.1 <= delay <= 0.2


def test_scroll_to_bottom_stops_at_same_height():
    source = ConcreteSource()
    source._page = MagicMock()
    # scroll_to_bottom calls evaluate 3 times per iteration:
    # 1. get scrollHeight, 2. scrollTo, 3. get scrollHeight again
    source._page.evaluate.side_effect = [100, None, 100]

    with patch("sources.chrome_base.time.sleep"):
        source._scroll_to_bottom(max_scrolls=5, pause=0.01)

    assert source._page.evaluate.call_count == 3


def test_get_page_html():
    source = ConcreteSource()
    source._page = MagicMock()
    source._page.content.return_value = "<html><body>test</body></html>"

    assert source._get_page_html() == "<html><body>test</body></html>"
