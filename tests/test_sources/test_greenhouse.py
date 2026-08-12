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


@responses.activate
def test_one_dead_board_does_not_discard_the_others():
    """A 404 on a single board must not take the whole source down.

    Reproduces a real failure: board 22 of 22 (creditkarma) returned 404, the
    exception escaped collect() into safe_collect(), and all 103 roles already
    gathered from the previous 21 boards were discarded — so Greenhouse, the
    primary source, silently contributed zero jobs to every run.
    """
    import config

    fixture = load_fixture("greenhouse_response.json")
    tokens = list(config.GREENHOUSE_BOARDS.values())
    assert len(tokens) >= 2, "test needs at least two boards configured"

    # Fail the first board so the assertion also proves the loop continued
    # rather than merely that earlier results were retained.
    for i, token in enumerate(tokens):
        if i == 0:
            responses.add(responses.GET, f"{API_BASE}/{token}/jobs", status=404)
        else:
            responses.add(responses.GET, f"{API_BASE}/{token}/jobs", json=fixture, status=200)

    jobs = GreenhouseSource().collect()

    # Every board was still attempted, and the healthy ones still returned jobs.
    assert len(responses.calls) == len(tokens), "a dead board stopped later boards being fetched"
    assert jobs, "a single dead board discarded every other board's results"


@responses.activate
def test_dead_board_survives_safe_collect():
    """The same failure through the wrapper the pipeline actually calls."""
    import config

    fixture = load_fixture("greenhouse_response.json")
    tokens = list(config.GREENHOUSE_BOARDS.values())
    for i, token in enumerate(tokens):
        if i == 0:
            responses.add(responses.GET, f"{API_BASE}/{token}/jobs", status=404)
        else:
            responses.add(responses.GET, f"{API_BASE}/{token}/jobs", json=fixture, status=200)

    assert GreenhouseSource().safe_collect(), "safe_collect returned nothing"
