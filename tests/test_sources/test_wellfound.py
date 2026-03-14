"""Tests for sources/wellfound.py — Wellfound Chrome source."""

import json
from unittest.mock import patch, MagicMock

from sources.wellfound import WellfoundSource, WELLFOUND_ROLE_SLUGS


NEXT_DATA = {
    "props": {
        "pageProps": {
            "apolloState": {
                "data": {
                    "ROOT_QUERY": {
                        "search_1": {
                            "pageCount": 1,
                            "page": 1,
                        }
                    },
                    "JobListingSearchResult:1001": {
                        "__typename": "JobListingSearchResult",
                        "id": 1001,
                        "title": "Customer Success Manager",
                        "slug": "customer-success-manager-at-techco",
                        "description": "Lead customer success initiatives",
                        "remote": True,
                        "locationNames": ["Remote", "US"],
                        "compensation": "$130k \u2013 $160k",
                        "liveStartAt": 1773000000,
                    },
                    "JobListingSearchResult:1002": {
                        "__typename": "JobListingSearchResult",
                        "id": 1002,
                        "title": "Frontend Developer",
                        "slug": "frontend-dev",
                        "description": "React developer",
                        "remote": False,
                        "locationNames": ["San Francisco"],
                        "compensation": "$140k \u2013 $180k",
                        "liveStartAt": 1773000000,
                    },
                    "JobListingSearchResult:1003": {
                        "__typename": "JobListingSearchResult",
                        "id": 1003,
                        "title": "Application Support Engineer",
                        "slug": "app-support-eng",
                        "description": "Troubleshoot and support customers",
                        "remote": True,
                        "locationNames": ["Remote"],
                        "compensation": "$110k \u2013 $140k",
                        "liveStartAt": 1773000000,
                    },
                    "StartupResult:500": {
                        "__typename": "StartupResult",
                        "name": "TechCo",
                        "slug": "techco",
                        "highlightedJobListings": [
                            {"__ref": "JobListingSearchResult:1001"},
                        ],
                    },
                    "StartupResult:501": {
                        "__typename": "StartupResult",
                        "name": "WebDev Inc",
                        "slug": "webdev-inc",
                        "highlightedJobListings": [
                            {"__ref": "JobListingSearchResult:1002"},
                        ],
                    },
                    "StartupResult:502": {
                        "__typename": "StartupResult",
                        "name": "HealthApp",
                        "slug": "healthapp",
                        "highlightedJobListings": [
                            {"__ref": "JobListingSearchResult:1003"},
                        ],
                    },
                },
            },
        },
    },
}


def _build_html(next_data=None):
    data = json.dumps(next_data or NEXT_DATA)
    return f'<html><head><script id="__NEXT_DATA__" type="application/json">{data}</script></head><body></body></html>'


def _make_source_with_mock_page(html):
    source = WellfoundSource()
    source._page = MagicMock()
    source._page.content.return_value = html
    source._page.goto = MagicMock()
    source._page.wait_for_selector = MagicMock()
    source._page.url = "https://wellfound.com/role/r/account-manager"
    return source


# --- Unit tests ---


def test_matches_role():
    source = WellfoundSource()
    assert source._matches_role("Customer Success Manager")
    assert source._matches_role("application support engineer")
    assert not source._matches_role("Frontend Developer")


def test_parse_compensation_k_range():
    source = WellfoundSource()
    assert source._parse_compensation("$130k \u2013 $160k") == (130000, 160000)


def test_parse_compensation_full_range():
    source = WellfoundSource()
    assert source._parse_compensation("$130,000 - $160,000") == (130000, 160000)


def test_parse_compensation_empty():
    source = WellfoundSource()
    assert source._parse_compensation("") == (0, 0)
    assert source._parse_compensation(None) == (0, 0)


def test_parse_date_unix_timestamp():
    source = WellfoundSource()
    result = source._parse_date(1773000000)
    assert result.year >= 2026


def test_parse_date_empty():
    source = WellfoundSource()
    result = source._parse_date("")
    assert result.year >= 2026


def test_parse_date_iso():
    source = WellfoundSource()
    result = source._parse_date("2026-03-10T12:00:00Z")
    assert result.year == 2026


def test_extract_jobs_filters_by_role():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, has_more = source._extract_jobs()
    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Engineer" in titles
    assert "Frontend Developer" not in titles


def test_extract_jobs_source_name():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    assert all(j.source == "wellfound" for j in jobs)


def test_extract_jobs_remote_flag():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.is_remote is True


def test_extract_jobs_location():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "Remote" in csm.location


def test_extract_jobs_salary():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 130000
    assert csm.salary_max == 160000


def test_extract_jobs_company_from_startup_ref():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.company == "TechCo"


def test_extract_jobs_url_format():
    html = _build_html()
    source = _make_source_with_mock_page(html)
    jobs, _ = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "wellfound.com/jobs/" in csm.url


def test_extract_jobs_no_next_data():
    source = _make_source_with_mock_page("<html><body>No data</body></html>")
    jobs, has_more = source._extract_jobs()
    assert jobs == []
    assert has_more is False


def test_extract_jobs_invalid_json():
    html = '<html><script id="__NEXT_DATA__" type="application/json">not json</script></html>'
    source = _make_source_with_mock_page(html)
    jobs, has_more = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_pagination_has_more():
    data = json.loads(json.dumps(NEXT_DATA))
    data["props"]["pageProps"]["apolloState"]["data"]["ROOT_QUERY"]["search_1"] = {
        "pageCount": 3,
        "page": 1,
    }
    html = _build_html(data)
    source = _make_source_with_mock_page(html)
    _, has_more = source._extract_jobs()
    assert has_more is True


def test_role_slugs_defined():
    assert len(WELLFOUND_ROLE_SLUGS) >= 3
    assert "account-manager" in WELLFOUND_ROLE_SLUGS
    assert "customer-support" in WELLFOUND_ROLE_SLUGS


def test_collect_skips_redirected_roles():
    """If a role redirects to /remote, skip it."""
    source = WellfoundSource()
    source._page = MagicMock()
    source._page.url = "https://wellfound.com/remote"
    source._page.goto = MagicMock()

    with patch("sources.chrome_base.time.sleep"):
        jobs = source._fetch_role("nonexistent-role")

    assert jobs == []
