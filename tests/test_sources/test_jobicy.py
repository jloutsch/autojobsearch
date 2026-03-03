"""Tests for sources/jobicy.py — Jobicy JSON API source."""

import responses

from sources.jobicy import JobicySource, API_URL, QUERIES
from tests.conftest import load_fixture


@responses.activate
def test_collect_filters_by_role():
    """Only role-matching titles are returned."""
    fixture = load_fixture("jobicy_response.json")
    # Two queries = two API calls
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Solutions Engineering Manager" in titles
    assert "Frontend Developer" not in titles


@responses.activate
def test_source_name():
    """All returned jobs have source='jobicy'."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    assert all(j.source == "jobicy" for j in jobs)


@responses.activate
def test_salary_parsing():
    """Annual salary min/max extracted from integer fields."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 130000
    assert csm.salary_max == 160000


@responses.activate
def test_null_salary():
    """Null salary fields become 0."""
    source = JobicySource()
    assert source._parse_int(None) == 0
    assert source._parse_int("") == 0
    assert source._parse_int("abc") == 0


@responses.activate
def test_cross_query_dedup():
    """Duplicate URLs across queries are deduplicated."""
    fixture = load_fixture("jobicy_response.json")
    # Same fixture for both queries — should dedup by URL
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = JobicySource()
    jobs = source.collect()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
def test_two_queries_made():
    """Source makes exactly 2 API calls (one per query)."""
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    source.collect()

    assert len(responses.calls) == 2


@responses.activate
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)


@responses.activate
def test_location_empty_defaults_to_worldwide():
    """Empty jobGeo defaults to 'Worldwide'."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    sol = next(j for j in jobs if j.title == "Solutions Engineering Manager")
    assert sol.location == "Worldwide"


@responses.activate
def test_date_parsing():
    """ISO date parsed correctly."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

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
def test_description_extracted():
    """jobExcerpt mapped to description."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "cybersecurity" in csm.description


@responses.activate
def test_empty_jobs_both_queries():
    """Empty results from both queries returns no jobs."""
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    assert jobs == []


@responses.activate
def test_http_error_raises():
    """HTTP errors propagate (caught by safe_collect in pipeline)."""
    responses.add(responses.GET, API_URL, status=500)

    source = JobicySource()
    import pytest
    with pytest.raises(Exception):
        source.collect()


@responses.activate
def test_safe_collect_http_error_returns_empty():
    """safe_collect wraps HTTP errors and returns empty list."""
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
def test_company_field_extracted():
    """companyName mapped to company."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "SecureOps"


@responses.activate
def test_url_field_extracted():
    """URL from API response is set on job."""
    fixture = load_fixture("jobicy_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = JobicySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "jobicy.com" in csm.url


def test_parse_int_valid():
    """Valid integer values parsed correctly."""
    source = JobicySource()
    assert source._parse_int(130000) == 130000
    assert source._parse_int("150000") == 150000
