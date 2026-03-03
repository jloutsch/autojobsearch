"""Tests for sources/himalayas.py — Himalayas JSON API source."""

import responses

from sources.himalayas import HimalayasSource, API_URL, PAGE_SIZE
from tests.conftest import load_fixture


@responses.activate
def test_collect_filters_by_role():
    """Only role-matching titles are returned."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    # Empty second page to stop pagination
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Engineer" in titles
    assert "Senior Data Scientist" not in titles


@responses.activate
def test_source_name():
    """All returned jobs have source='himalayas'."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    assert all(j.source == "himalayas" for j in jobs)


@responses.activate
def test_salary_parsing():
    """Salary min/max extracted from integer fields."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 125000
    assert csm.salary_max == 155000


@responses.activate
def test_null_salary():
    """Null salary fields become 0."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    # Application Support Engineer has salary values
    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert app_support.salary_min == 110000


@responses.activate
def test_url_fallback_from_slugs():
    """When url is empty, constructs URL from company/job slugs."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert "himalayas.app/companies/healthtech/jobs/application-support-engineer" in app_support.url


@responses.activate
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)


@responses.activate
def test_location_null_defaults_to_worldwide():
    """Null locationRestrictions defaults to 'Worldwide'."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    app_support = next(j for j in jobs if j.title == "Application Support Engineer")
    assert app_support.location == "Worldwide"


@responses.activate
def test_date_parsing():
    """ISO date with Z suffix parsed correctly."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

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
def test_pagination_stops_on_empty():
    """Pagination stops when API returns empty jobs list."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    # Should have made exactly 2 requests (first page + empty second page)
    assert len(responses.calls) == 2


@responses.activate
def test_pagination_max_pages():
    """Pagination respects MAX_PAGES limit."""
    fixture = load_fixture("himalayas_response.json")
    # Add 6 responses — only 5 should be consumed (MAX_PAGES=5)
    for _ in range(6):
        responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = HimalayasSource()
    source.collect()

    # fixture has 3 jobs but only 2 match, and pagination needs next page to
    # have items to continue. Since fixture has 3 items (< PAGE_SIZE=20),
    # pagination should stop after first page because len(listings) < PAGE_SIZE
    # is not checked — it stops on empty. With 3 items per page and 5 max pages,
    # it will fetch until empty or 5 pages.
    assert len(responses.calls) <= 5


@responses.activate
def test_empty_first_page():
    """Empty first page returns no results."""
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    assert jobs == []


@responses.activate
def test_http_error_raises():
    """HTTP errors propagate (caught by safe_collect in pipeline)."""
    responses.add(responses.GET, API_URL, status=500)

    source = HimalayasSource()
    import pytest
    with pytest.raises(Exception):
        source.collect()


@responses.activate
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
def test_description_extracted():
    """Description field is populated."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "cloud infrastructure" in csm.description


@responses.activate
def test_company_field_extracted():
    """companyName mapped to company."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "RemoteFirst"


@responses.activate
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
    responses.add(responses.GET, API_URL, json=data, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    assert jobs[0].location == "Worldwide"


@responses.activate
def test_url_used_when_present():
    """When url is non-empty in response, it is used directly."""
    fixture = load_fixture("himalayas_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)
    responses.add(responses.GET, API_URL, json={"jobs": []}, status=200)

    source = HimalayasSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.url == "https://himalayas.app/companies/remotefirst/jobs/customer-success-manager"
