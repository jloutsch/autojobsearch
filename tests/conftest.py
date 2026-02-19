"""Shared test fixtures for the autojobsearch test suite."""

import json
import os
from datetime import datetime, timezone

import pytest

from models import JobListing

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_sample_profile():
    with open(os.path.join(FIXTURES_DIR, "sample_profile.json")) as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def mock_profile(monkeypatch):
    """Autouse fixture that injects a known test profile for every test.

    Resets user_profile._profile so get_profile() returns the test data,
    and calls config.reload() to refresh all config globals.
    """
    import config
    import user_profile

    profile = _load_sample_profile()
    monkeypatch.setattr(user_profile, "_profile", profile)
    config.reload()
    yield profile


@pytest.fixture
def make_job():
    """Factory fixture for creating JobListing instances with defaults."""

    def _make(**overrides):
        defaults = {
            "title": "Customer Success Manager",
            "company": "TestCorp",
            "url": "https://example.com/job/1",
            "source": "test",
            "description": "A customer success role in a cybersecurity saas company.",
            "salary_min": 130000,
            "salary_max": 150000,
            "location": "Remote - US",
            "is_remote": True,
            "posted_date": datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        return JobListing(**defaults)

    return _make


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database for dedup tests."""
    from dedup import init_db

    db_path = str(tmp_path / "test_seen_jobs.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def fixture_path():
    """Return the path to the fixtures directory."""
    return FIXTURES_DIR


def load_fixture(filename):
    """Load a fixture file by name."""
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path) as f:
        if filename.endswith(".json"):
            return json.load(f)
        return f.read()
