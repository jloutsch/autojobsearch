"""Tests for sources/crowdstrike.py — CrowdStrike Workday API source."""

from datetime import datetime, timezone

import responses
from freezegun import freeze_time

from sources.crowdstrike import CrowdStrikeSource, SEARCH_URL
from tests.conftest import load_fixture


@responses.activate
def test_collect_returns_matching_roles():
    """Collect returns jobs with matching role titles."""
    fixture = load_fixture("crowdstrike_response.json")

    # One response per search query (up to 4)
    for _ in range(4):
        responses.add(responses.POST, SEARCH_URL, json=fixture, status=200)

    source = CrowdStrikeSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Senior Customer Success Manager" in titles


@responses.activate
def test_role_filter_applied():
    """Non-matching titles are filtered out by _posting_to_job."""
    data = {
        "jobPostings": [
            {"title": "Marketing Specialist", "externalPath": "/job/mk-1",
             "locationsText": "Remote", "postedOn": "Today"}
        ],
        "total": 1,
    }
    for _ in range(4):
        responses.add(responses.POST, SEARCH_URL, json=data, status=200)

    source = CrowdStrikeSource()
    jobs = source.collect()
    assert len(jobs) == 0


@responses.activate
def test_dedup_by_external_path():
    """Duplicate externalPath across pages is deduplicated."""
    page = {
        "jobPostings": [
            {"title": "Customer Success Manager", "externalPath": "/job/csm-1",
             "locationsText": "Remote", "postedOn": "Today"}
        ],
        "total": 1,
    }
    # Same result returned for multiple queries
    for _ in range(8):
        responses.add(responses.POST, SEARCH_URL, json=page, status=200)

    source = CrowdStrikeSource()
    jobs = source.collect()
    # Should only appear once despite multiple queries returning same posting
    assert len(jobs) == 1


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_today():
    """'Today' → today's date."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("Today")
    assert result.date() == datetime(2026, 2, 19).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_days_ago():
    """'Posted 3 Days Ago' → 3 days back."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("Posted 3 Days Ago")
    assert result.date() == datetime(2026, 2, 16).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_hours_ago():
    """'5 Hours Ago' → same day."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("5 Hours Ago")
    assert result.date() == datetime(2026, 2, 19).date()


def test_parse_posted_unknown():
    """Unrecognized format → datetime.now()."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("Some random text")
    assert result.year >= 2026


@responses.activate
def test_api_error_returns_empty():
    """Connection error → safe_collect returns []."""
    responses.add(responses.POST, SEARCH_URL, body=ConnectionError("timeout"))

    source = CrowdStrikeSource()
    jobs = source.safe_collect()
    assert jobs == []


# --- Additional edge cases ---


@responses.activate
def test_pagination_multiple_pages():
    """total > 20 triggers additional page requests."""
    page1 = {
        "jobPostings": [
            {"title": "Customer Success Manager", "externalPath": f"/job/csm-{i}",
             "locationsText": "Remote", "postedOn": "Today"}
            for i in range(20)
        ],
        "total": 25,
    }
    page2 = {
        "jobPostings": [
            {"title": "Customer Success Manager", "externalPath": f"/job/csm-{i}",
             "locationsText": "Remote", "postedOn": "Today"}
            for i in range(20, 25)
        ],
        "total": 25,
    }
    # Need responses for each query (up to 4) × each page
    for _ in range(4):
        responses.add(responses.POST, SEARCH_URL, json=page1, status=200)
        responses.add(responses.POST, SEARCH_URL, json=page2, status=200)

    source = CrowdStrikeSource()
    jobs = source.collect()
    # Should have fetched multiple pages for at least the first query
    assert len(responses.calls) > 4


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_weeks_ago():
    """'Posted 2 Weeks Ago' → 14 days back."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("Posted 2 Weeks Ago")
    assert result.date() == datetime(2026, 2, 5).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_months_ago():
    """'Posted 1+ Months Ago' → ~30 days back."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("Posted 1 Months Ago")
    expected = datetime(2026, 1, 20).date()
    assert result.date() == expected


@responses.activate
def test_location_text_extraction():
    """locationsText field mapped to job.location."""
    data = {
        "jobPostings": [
            {"title": "Customer Success Manager", "externalPath": "/job/csm-loc",
             "locationsText": "Remote, USA", "postedOn": "Today"}
        ],
        "total": 1,
    }
    for _ in range(4):
        responses.add(responses.POST, SEARCH_URL, json=data, status=200)

    source = CrowdStrikeSource()
    jobs = source.collect()
    assert jobs[0].location == "Remote, USA"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_parse_posted_empty():
    """Empty string → datetime.now()."""
    source = CrowdStrikeSource()
    result = source._parse_posted_on("")
    assert result.date() == datetime(2026, 2, 19).date()


@responses.activate
def test_search_page_failure_returns_none():
    """HTTP error on one search page → None, continues."""
    responses.add(responses.POST, SEARCH_URL, status=500)

    source = CrowdStrikeSource()
    result = source._search_page("customer success", 0)
    assert result is None
