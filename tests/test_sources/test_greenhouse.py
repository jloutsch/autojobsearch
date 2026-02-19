"""Tests for sources/greenhouse.py — Greenhouse ATS API source."""

import json
import os

import responses

from sources.greenhouse import GreenhouseSource
from tests.conftest import load_fixture

API_BASE = "https://boards-api.greenhouse.io/v1/boards"


@responses.activate
def test_collect_fetches_all_boards():
    """One GET per board in GREENHOUSE_BOARDS."""
    fixture = load_fixture("greenhouse_response.json")

    responses.add(
        responses.GET,
        f"{API_BASE}/sentinellabs/jobs",
        json=fixture,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/datadog/jobs",
        json={"jobs": []},
        status=200,
    )

    source = GreenhouseSource()
    jobs = source.collect()

    assert len(responses.calls) == 2
    # Fixture has 2 role-matching jobs (Application Support Manager, Customer Success Manager)
    assert any(j.title == "Application Support Manager" for j in jobs)


@responses.activate
def test_role_filter_applied():
    """Non-matching titles are excluded."""
    fixture = load_fixture("greenhouse_response.json")
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", json=fixture, status=200)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", json={"jobs": []}, status=200)

    source = GreenhouseSource()
    jobs = source.collect()
    titles = [j.title for j in jobs]

    # "Senior Software Engineer" should be excluded
    assert "Senior Software Engineer" not in titles


@responses.activate
def test_location_extraction():
    """location.name extracted correctly."""
    fixture = load_fixture("greenhouse_response.json")
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", json=fixture, status=200)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", json={"jobs": []}, status=200)

    source = GreenhouseSource()
    jobs = source.collect()
    support_mgr = next(j for j in jobs if j.title == "Application Support Manager")
    assert support_mgr.location == "Remote - US"


@responses.activate
def test_missing_location_handled():
    """Missing location field → empty string."""
    fixture = load_fixture("greenhouse_response.json")
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", json=fixture, status=200)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", json={"jobs": []}, status=200)

    source = GreenhouseSource()
    jobs = source.collect()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.location == ""


@responses.activate
def test_date_parsing_iso():
    """ISO 8601 date parsed correctly."""
    fixture = load_fixture("greenhouse_response.json")
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", json=fixture, status=200)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", json={"jobs": []}, status=200)

    source = GreenhouseSource()
    jobs = source.collect()
    support_mgr = next(j for j in jobs if j.title == "Application Support Manager")
    assert support_mgr.posted_date.year == 2026
    assert support_mgr.posted_date.month == 2


def test_date_parsing_failure():
    """Invalid date → datetime.now() fallback."""
    source = GreenhouseSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


@responses.activate
def test_api_error_returns_empty():
    """HTTP 500 → safe_collect returns []."""
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", status=500)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", status=500)

    source = GreenhouseSource()
    jobs = source.safe_collect()
    assert jobs == []


@responses.activate
def test_empty_response():
    """API returns {"jobs": []} → empty list."""
    responses.add(responses.GET, f"{API_BASE}/sentinellabs/jobs", json={"jobs": []}, status=200)
    responses.add(responses.GET, f"{API_BASE}/datadog/jobs", json={"jobs": []}, status=200)

    source = GreenhouseSource()
    jobs = source.collect()
    assert jobs == []
