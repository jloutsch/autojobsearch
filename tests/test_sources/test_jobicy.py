"""Tests for sources/jobicy.py — Jobicy JSON API source."""

from unittest.mock import patch

import responses

from sources.jobicy import JobicySource, API_URL
from tests.conftest import load_fixture

MOCK_QUERIES = ["application support", "customer success"]


def _add_responses_for_queries(fixture=None):
    """Add mock responses for each query in MOCK_QUERIES."""
    for _ in MOCK_QUERIES:
        if fixture:
            responses.add(responses.GET, API_URL, json=fixture, status=200)
        else:
            responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_collect_filters_by_role():
    """Only role-matching titles are returned."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Solutions Engineering Manager" in titles
    assert "Frontend Developer" not in titles


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_source_name():
    """All returned jobs have source='jobicy'."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    assert all(j.source == "jobicy" for j in jobs)


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_salary_parsing():
    """Annual salary min/max extracted from integer fields."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 130000
    assert csm.salary_max == 160000


def test_null_salary():
    """Null salary fields become 0."""
    source = JobicySource()
    assert source._parse_int(None) == 0
    assert source._parse_int("") == 0
    assert source._parse_int("abc") == 0


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_cross_query_dedup():
    """Duplicate URLs across queries are deduplicated."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_two_queries_made():
    """Source makes exactly len(SEARCH_QUERIES) API calls."""
    _add_responses_for_queries()

    source = JobicySource()
    source.collect()

    assert len(responses.calls) == len(MOCK_QUERIES)


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_location_empty_defaults_to_worldwide():
    """Empty jobGeo defaults to 'Worldwide'."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    sol = next(j for j in jobs if j.title == "Solutions Engineering Manager")
    assert sol.location == "Worldwide"


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_date_parsing():
    """ISO date parsed correctly."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026


def test_date_parsing_empty():
    """Empty date string falls back to now."""
    source = JobicySource()
    result = source._parse_date("")
    assert result.year >= 2026


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_description_extracted():
    """jobExcerpt mapped to description."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "cybersecurity" in csm.description


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_empty_jobs_both_queries():
    """Empty results from both queries returns no jobs."""
    _add_responses_for_queries()

    source = JobicySource()
    jobs = source.collect()

    assert jobs == []


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", ["application support"])
def test_http_error_skips_query():
    """HTTP errors on a query are logged and skipped."""
    responses.add(responses.GET, API_URL, status=500)

    source = JobicySource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_safe_collect_http_error_returns_empty():
    """safe_collect wraps HTTP errors and returns empty list."""
    # All queries fail
    for _ in MOCK_QUERIES:
        responses.add(responses.GET, API_URL, status=500)

    source = JobicySource()
    jobs = source.safe_collect()

    assert jobs == []


def test_date_parsing_invalid():
    """Invalid date string falls back to now."""
    source = JobicySource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_company_field_extracted():
    """companyName mapped to company."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "SecureOps"


@responses.activate
@patch("sources.jobicy.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_url_field_extracted():
    """URL from API response is set on job."""
    fixture = load_fixture("jobicy_response.json")
    _add_responses_for_queries(fixture)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "jobicy.com" in csm.url


def test_parse_int_valid():
    """Valid integer values parsed correctly."""
    source = JobicySource()
    assert source._parse_int(130000) == 130000
    assert source._parse_int("150000") == 150000
