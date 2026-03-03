"""Tests for sources/base.py — BaseSource abstract class and safe_collect."""

import logging
from unittest.mock import MagicMock

from sources.base import BaseSource


class ConcreteSource(BaseSource):
    """Minimal concrete subclass for testing."""

    name = "test_source"

    def __init__(self, jobs=None, error=None):
        self._jobs = jobs or []
        self._error = error

    def collect(self):
        if self._error:
            raise self._error
        return self._jobs


def test_safe_collect_returns_results(make_job):
    """Successful collect() returns the list."""
    job = make_job()
    source = ConcreteSource(jobs=[job])
    result = source.safe_collect()
    assert len(result) == 1
    assert result[0].title == "Customer Success Manager"


def test_safe_collect_catches_exception():
    """collect() raising → safe_collect returns []."""
    source = ConcreteSource(error=RuntimeError("API down"))
    result = source.safe_collect()
    assert result == []


def test_safe_collect_logs_error(caplog):
    """Logger.error called on exception."""
    source = ConcreteSource(error=ValueError("timeout"))
    with caplog.at_level(logging.ERROR, logger="sources.base"):
        source.safe_collect()
    assert any("test_source" in r.message and "timeout" in r.message for r in caplog.records)


def test_safe_collect_logs_success(make_job, caplog):
    """Logger.info called with count on success."""
    job = make_job()
    source = ConcreteSource(jobs=[job])
    with caplog.at_level(logging.INFO, logger="sources.base"):
        source.safe_collect()
    assert any("test_source" in r.message and "1" in r.message for r in caplog.records)
