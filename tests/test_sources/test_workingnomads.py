"""Tests for sources/workingnomads.py — Working Nomads JSON API source."""

import responses

from sources.workingnomads import API_URL, WorkingNomadsSource
from tests.conftest import load_fixture


@responses.activate
def test_collect_filters_by_category():
    """Only relevant categories returned."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    # "Backend Developer" is in "Development" category — excluded
    titles = [j.title for j in jobs]
    assert "Backend Developer" not in titles


@responses.activate
def test_role_filter_applied():
    """Non-matching titles excluded even in valid category."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    # "Sales Manager" is in Sales category but doesn't match role keywords
    titles = [j.title for j in jobs]
    assert "Sales Manager" not in titles


@responses.activate
def test_matching_jobs_returned():
    """Jobs matching both category and role keywords returned."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Analyst" in titles


@responses.activate
def test_company_name_extracted():
    """Company name parsed from JSON."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.company == "SaaSCo"


@responses.activate
def test_html_description_stripped():
    """HTML tags stripped from description."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert "<p>" not in csm.description
    assert "<strong>" not in csm.description
    assert "SaaS" in csm.description


@responses.activate
def test_iso_date_with_microseconds():
    """ISO 8601 date with microseconds parsed correctly."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if "Application Support" in j.title)
    assert app_support.posted_date.year == 2026
    assert app_support.posted_date.month == 2


@responses.activate
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()
    assert all(j.is_remote is True for j in jobs)


@responses.activate
def test_source_name():
    """Source set to 'workingnomads'."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()
    assert all(j.source == "workingnomads" for j in jobs)


# --- Edge cases ---


@responses.activate
def test_empty_response():
    """Empty array → no jobs."""
    responses.add(responses.GET, API_URL, json=[], status=200)
    source = WorkingNomadsSource()
    jobs = source.collect()
    assert jobs == []


def test_date_parsing_empty():
    """Empty date string → datetime.now()."""
    source = WorkingNomadsSource()
    result = source._parse_date("")
    assert result.year >= 2026


def test_date_parsing_invalid():
    """Invalid date → datetime.now() fallback."""
    source = WorkingNomadsSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


def test_date_parsing_iso_with_offset():
    """ISO date with timezone offset parsed correctly."""
    source = WorkingNomadsSource()
    result = source._parse_date("2026-02-15T09:41:38-05:00")
    assert result.year == 2026
    assert result.month == 2
    assert result.day == 15


@responses.activate
def test_http_error():
    """HTTP error → exception propagated (caught by safe_collect)."""
    responses.add(responses.GET, API_URL, status=500)
    source = WorkingNomadsSource()
    jobs = source.safe_collect()
    assert jobs == []


@responses.activate
def test_location_field():
    """Location extracted from JSON."""
    fixture = load_fixture("workingnomads_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = WorkingNomadsSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.location == "Remote, Worldwide"


@responses.activate
def test_missing_description():
    """Missing description field doesn't crash."""
    data = [{
        "url": "https://example.com/job/1",
        "title": "Customer Success Manager",
        "company_name": "TestCo",
        "category_name": "Customer Success",
        "location": "Remote",
        "pub_date": "2026-02-15T10:00:00-05:00",
    }]
    responses.add(responses.GET, API_URL, json=data, status=200)
    source = WorkingNomadsSource()
    jobs = source.collect()
    assert len(jobs) == 1
    assert jobs[0].description == ""
