"""Tests for filters.py — hard filtering logic."""

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from filters import (
    _is_boston,
    _is_non_us,
    _is_us_wide_remote,
    _passes_age_filter,
    _passes_location_filter,
    passes_hard_filters,
)


# --- Role keyword matching ---


def test_matching_role_remote_passes(make_job):
    """Job with matching role keyword + remote location passes."""
    job = make_job(title="Customer Success Manager", location="Remote - US")
    assert passes_hard_filters(job) is True


def test_no_role_keyword_match_fails(make_job):
    """Job title with no role keyword is rejected."""
    job = make_job(title="Senior Software Engineer", location="Remote - US")
    assert passes_hard_filters(job) is False


def test_case_insensitive_role_match(make_job):
    """Role matching is case-insensitive."""
    job = make_job(title="CUSTOMER SUCCESS Manager", location="Remote - US")
    assert passes_hard_filters(job) is True


def test_partial_role_match(make_job):
    """Partial keyword match in title passes."""
    job = make_job(title="VP of Customer Success Operations", location="Remote")
    assert passes_hard_filters(job) is True


# --- Junior role rejection ---


def test_junior_role_rejected(make_job):
    """Titles containing 'junior', 'intern', 'entry level' are rejected."""
    for signal in ["Junior Customer Success", "Customer Success Intern",
                    "Entry Level Application Support"]:
        job = make_job(title=signal, location="Remote")
        assert passes_hard_filters(job) is False, f"Should reject: {signal}"


def test_associate_role_rejected(make_job):
    """Associate-level roles are rejected."""
    job = make_job(title="Associate Customer Success Manager", location="Remote")
    assert passes_hard_filters(job) is False


# --- Salary floor ---


def test_salary_below_floor_rejected(make_job):
    """salary_max > 0 but below SALARY_FLOOR is rejected."""
    job = make_job(salary_min=60000, salary_max=80000, location="Remote")
    assert passes_hard_filters(job) is False


def test_salary_zero_passes(make_job):
    """Jobs with no salary info (salary_max=0) pass the salary filter."""
    job = make_job(salary_min=0, salary_max=0, location="Remote")
    assert passes_hard_filters(job) is True


def test_salary_at_floor_passes(make_job):
    """Salary exactly at the floor passes."""
    job = make_job(salary_min=90000, salary_max=100000, location="Remote")
    assert passes_hard_filters(job) is True


# --- Age filter ---


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_age_filter_old_job_rejected(make_job):
    """Job posted 45 days ago is rejected when MAX_JOB_AGE_DAYS=30."""
    old_date = datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc)
    job = make_job(posted_date=old_date, location="Remote")
    assert passes_hard_filters(job) is False


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_age_filter_recent_job_passes(make_job):
    """Job posted 5 days ago passes."""
    recent = datetime(2026, 2, 14, 10, 0, 0, tzinfo=timezone.utc)
    job = make_job(posted_date=recent, location="Remote")
    assert passes_hard_filters(job) is True


def test_age_filter_disabled(make_job, monkeypatch):
    """MAX_JOB_AGE_DAYS=0 disables age filtering."""
    import config
    monkeypatch.setattr(config, "MAX_JOB_AGE_DAYS", 0)
    old_date = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    job = make_job(posted_date=old_date, location="Remote")
    assert _passes_age_filter(job) is True


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_age_filter_naive_datetime(make_job):
    """Naive datetime (no tzinfo) is treated as UTC."""
    recent = datetime(2026, 2, 18, 10, 0, 0)  # no tzinfo
    job = make_job(posted_date=recent, location="Remote")
    assert _passes_age_filter(job) is True


# --- Location filter ---


def test_non_us_location_rejected(make_job):
    """Locations clearly indicating non-US are rejected."""
    for loc in ["London, UK", "Berlin, Germany", "Bangalore, India", "Toronto, Canada"]:
        job = make_job(location=loc)
        assert passes_hard_filters(job) is False, f"Should reject: {loc}"


def test_us_remote_passes(make_job):
    """US-wide remote locations pass."""
    for loc in ["Remote - US", "United States (Remote)", "Remote", "Worldwide"]:
        job = make_job(location=loc)
        assert passes_hard_filters(job) is True, f"Should pass: {loc}"


def test_pinned_non_preferred_city_rejected(make_job):
    """City-restricted remote roles in non-preferred cities are rejected."""
    for loc in ["Austin, TX", "San Francisco, CA", "FL, USA, Remote"]:
        job = make_job(location=loc)
        result = passes_hard_filters(job)
        assert result is False, f"Should reject pinned: {loc}"


def test_preferred_city_boston_passes(make_job):
    """Boston area locations pass."""
    for loc in ["Boston, MA", "Cambridge, MA", "Waltham, MA"]:
        job = make_job(location=loc, is_remote=False)
        assert passes_hard_filters(job) is True, f"Should pass Boston: {loc}"


def test_default_deny_fallthrough(make_job):
    """Ambiguous remote location returns False (default deny)."""
    job = make_job(location="Some Random Place", is_remote=True)
    assert _passes_location_filter(job) is False


def test_n_locations_accepted(make_job):
    """BuiltIn-style '2 Locations' passes for remote jobs."""
    job = make_job(location="2 Locations", is_remote=True)
    assert _passes_location_filter(job) is True


# --- Helper functions ---


def test_is_boston():
    """_is_boston detects Boston-area signals."""
    assert _is_boston("boston, ma") is True
    assert _is_boston("cambridge, ma office") is True
    assert _is_boston("new york, ny") is False


def test_is_non_us():
    """_is_non_us detects international signals."""
    assert _is_non_us("london office") is True
    assert _is_non_us("emea region") is True
    assert _is_non_us("remote - us") is False


def test_is_non_us_short_signals_word_boundary():
    """Short signals like 'uk' use word boundaries to avoid false matches."""
    assert _is_non_us("uk") is True
    assert _is_non_us("bulk order") is False
    assert _is_non_us("uae") is True
