"""Tests for sources/remotive.py — Remotive JSON API source."""

import responses

from sources.remotive import RemotiveSource, API_URL
from tests.conftest import load_fixture


@responses.activate
def test_collect_filters_by_role():
    """Only role-matching titles are returned."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Technical Account Management Lead" in titles
    assert "Backend Engineer" not in titles


@responses.activate
def test_source_name():
    """All returned jobs have source='remotive'."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    assert all(j.source == "remotive" for j in jobs)


@responses.activate
def test_salary_parsing_full_format():
    """Salary string like '$120,000 - $150,000' parsed correctly."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 120000
    assert csm.salary_max == 150000


@responses.activate
def test_salary_parsing_k_format():
    """Salary string like '$130k - $160k' normalized to full values."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    tam = next(j for j in jobs if j.title == "Technical Account Management Lead")
    assert tam.salary_min == 130000
    assert tam.salary_max == 160000


def test_salary_empty_string():
    """Empty salary string returns (0, 0)."""
    source = RemotiveSource()
    assert source._parse_salary("") == (0, 0)


def test_salary_single_value():
    """Single salary value returns same for min and max."""
    source = RemotiveSource()
    assert source._parse_salary("$120,000") == (120000, 120000)


@responses.activate
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)


@responses.activate
def test_date_parsing():
    """ISO date parsed correctly."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026
    assert csm.posted_date.month == 2


def test_date_parsing_empty():
    """Empty date string falls back to now."""
    source = RemotiveSource()
    result = source._parse_date("")
    assert result.year >= 2026


@responses.activate
def test_location_extraction():
    """Location field mapped correctly; empty defaults to 'Worldwide'."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.location == "USA Only"

    tam = next(j for j in jobs if j.title == "Technical Account Management Lead")
    assert tam.location == "Worldwide"


@responses.activate
def test_description_extracted():
    """Description field is populated."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "cybersecurity" in csm.description


@responses.activate
def test_empty_jobs_list():
    """Empty jobs list returns no results."""
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    assert jobs == []


@responses.activate
def test_http_error_raises():
    """HTTP errors propagate (caught by safe_collect in pipeline)."""
    responses.add(responses.GET, API_URL, status=500)

    source = RemotiveSource()
    import pytest
    with pytest.raises(Exception):
        source.collect()


@responses.activate
def test_safe_collect_http_error_returns_empty():
    """safe_collect wraps HTTP errors and returns empty list."""
    responses.add(responses.GET, API_URL, status=500)

    source = RemotiveSource()
    jobs = source.safe_collect()

    assert jobs == []


def test_date_parsing_invalid():
    """Invalid date string falls back to now."""
    source = RemotiveSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


def test_salary_no_numbers():
    """Salary string with no numbers returns (0, 0)."""
    source = RemotiveSource()
    assert source._parse_salary("Competitive") == (0, 0)


@responses.activate
def test_company_field_extracted():
    """company_name mapped to company."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "CloudSecure"


@responses.activate
def test_url_field_extracted():
    """URL from API response is set on job."""
    fixture = load_fixture("remotive_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemotiveSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "remotive.com" in csm.url
