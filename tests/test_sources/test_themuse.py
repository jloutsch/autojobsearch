"""Tests for sources/themuse.py — The Muse JSON API source."""

import responses

from sources.themuse import TheMuseSource, API_URL
from tests.conftest import load_fixture


@responses.activate
def test_collect_filters_by_role():
    """Non-matching titles excluded."""
    fixture = load_fixture("themuse_response.json")
    # Single page (page_count=2 but we only register page 0 with page_count=1 override)
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Senior Software Engineer" not in titles
    assert "Customer Success Manager" in titles
    assert "Technical Account Management Lead" in titles


@responses.activate
def test_pagination():
    """Multiple pages are fetched."""
    page1 = load_fixture("themuse_response.json")
    page2 = load_fixture("themuse_page2.json")

    responses.add(responses.GET, API_URL, json=page1, status=200)
    responses.add(responses.GET, API_URL, json=page2, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    # Page 1 has 2 matching roles, page 2 has 1
    assert len(jobs) == 3
    assert len(responses.calls) == 2


@responses.activate
def test_remote_detection():
    """Flexible/Remote locations detected as remote."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.is_remote is True

    tam = next(j for j in jobs if j.title == "Technical Account Management Lead")
    assert tam.is_remote is True


@responses.activate
def test_salary_extraction_full():
    """Salary range extracted from HTML contents."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 130000
    assert csm.salary_max == 150000


@responses.activate
def test_salary_extraction_k_notation():
    """$140k-$170k notation parsed correctly."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    tam = next(j for j in jobs if j.title == "Technical Account Management Lead")
    assert tam.salary_min == 140000
    assert tam.salary_max == 170000


@responses.activate
def test_date_parsing():
    """ISO date parsed correctly."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026
    assert csm.posted_date.month == 2


@responses.activate
def test_html_stripped_from_description():
    """HTML tags removed from description."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "<p>" not in csm.description
    assert "Customer Success Manager" in csm.description


@responses.activate
def test_location_extraction():
    """Multiple locations joined by comma."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    tam = next(j for j in jobs if j.title == "Technical Account Management Lead")
    assert "Remote" in tam.location
    assert "San Francisco" in tam.location


@responses.activate
def test_source_name():
    """All jobs have source='themuse'."""
    fixture = load_fixture("themuse_response.json")
    fixture["page_count"] = 1
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = TheMuseSource()
    jobs = source.collect()
    assert all(j.source == "themuse" for j in jobs)


@responses.activate
def test_dedup_across_pages():
    """Duplicate URLs across pages are skipped."""
    page1 = load_fixture("themuse_response.json")
    # Page 2 has same CSM job URL as page 1
    page2 = {
        "page": 1,
        "page_count": 2,
        "total": 1,
        "results": [page1["results"][0]],
    }
    responses.add(responses.GET, API_URL, json=page1, status=200)
    responses.add(responses.GET, API_URL, json=page2, status=200)

    source = TheMuseSource()
    jobs = source.collect()

    csm_count = sum(1 for j in jobs if j.title == "Customer Success Manager")
    assert csm_count == 1


@responses.activate
def test_empty_response():
    """No results → empty list."""
    data = {"page": 0, "page_count": 1, "total": 0, "results": []}
    responses.add(responses.GET, API_URL, json=data, status=200)

    source = TheMuseSource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
def test_api_error_safe_collect():
    """HTTP 500 → safe_collect returns []."""
    responses.add(responses.GET, API_URL, status=500)

    source = TheMuseSource()
    jobs = source.safe_collect()
    assert jobs == []


def test_date_parsing_invalid():
    """Invalid date → fallback to now."""
    source = TheMuseSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


def test_salary_no_match():
    """No salary in text → (0, 0)."""
    source = TheMuseSource()
    assert source._extract_salary("<p>No salary info here.</p>") == (0, 0)


def test_salary_empty():
    """Empty HTML → (0, 0)."""
    source = TheMuseSource()
    assert source._extract_salary("") == (0, 0)
