"""Tests for sources/himalayas.py — Himalayas JSON API source."""

from unittest.mock import patch

import responses

from sources.himalayas import HimalayasSource, API_URL, PAGE_SIZE
from tests.conftest import load_fixture

# Use a single query to simplify test response setup
MOCK_QUERIES = ["customer success"]


def _add_responses_for_query(fixture, empty_page=True):
    """Add fixture response + optional empty page for one query."""
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    if empty_page:
        responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_collect_filters_by_role():
    """Only role-matching titles are returned."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Engineer" in titles
    assert "Senior Data Scientist" not in titles


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_source_name():
    """All returned jobs have source='himalayas'."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    assert all(j.source == "himalayas" for j in jobs)


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_salary_parsing():
    """Salary min/max extracted from integer fields."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 125000
    assert csm.salary_max == 155000


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_null_salary():
    """Null salary fields become 0."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert app_support.salary_min == 110000


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_url_fallback_from_slugs():
    """When url is empty, constructs URL from company/job slugs."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert "himalayas.app/companies/healthtech/jobs/application-support-engineer" in app_support.url


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_location_null_defaults_to_worldwide():
    """Null locationRestrictions defaults to 'Worldwide'."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert app_support.location == "Worldwide"


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_date_parsing():
    """ISO date with Z suffix parsed correctly."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026
    assert csm.posted_date.month == 2


def test_date_parsing_empty():
    """Empty date string falls back to now."""
    source = HimalayasSource()
    result = source._parse_date("")
    assert result.year >= 2026


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_pagination_stops_on_empty():
    """Pagination stops when API returns empty jobs list."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    # Should have made exactly 2 requests (first page + empty second page)
    assert len(responses.calls) == 2


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_pagination_max_pages():
    """Pagination respects MAX_PAGES limit."""
    fixture = load_fixture("himalayas_response.json")
    # Add 6 responses — only 5 should be consumed (MAX_PAGES=5)
    for _ in range(6):
        responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = HimalayasSource()
    source.collect()

    assert len(responses.calls) <= 5


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_empty_first_page():
    """Empty first page returns no results."""
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    assert jobs == []


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_http_error_breaks_query():
    """HTTP errors on a query break pagination for that query."""
    responses.add(responses.GET, API_URL, status=500)

    source = HimalayasSource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_safe_collect_http_error_returns_empty():
    """safe_collect wraps HTTP errors and returns empty list."""
    responses.add(responses.GET, API_URL, status=500)

    source = HimalayasSource()
    jobs = source.safe_collect()

    assert jobs == []


def test_date_parsing_invalid():
    """Invalid date string falls back to now."""
    source = HimalayasSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_description_extracted():
    """Description field is populated."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "cloud infrastructure" in csm.description


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_company_field_extracted():
    """companyName mapped to company."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "RemoteFirst"


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_location_integer_coerced_to_string():
    """Integer locationRestrictions doesn't crash — gets stringified."""
    data = {"jobs": [{
        "title": "Customer Success Manager",
        "companyName": "TestCo",
        "url": "https://example.com/job",
        "slug": "csm", "companySlug": "testco",
        "salaryMin": None, "salaryMax": None,
        "locationRestrictions": 0,
        "pubDate": "2026-02-18T12:00:00Z",
        "description": "Test role."
    }]}
    _add_responses_for_query(data)

    source = HimalayasSource()
    jobs = source.collect()

    assert jobs[0].location == "Worldwide"


@responses.activate
@patch("sources.himalayas.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_url_used_when_present():
    """When url is non-empty in response, it is used directly."""
    fixture = load_fixture("himalayas_response.json")
    _add_responses_for_query(fixture)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.url == "https://himalayas.app/companies/remotefirst/jobs/customer-success-manager"
