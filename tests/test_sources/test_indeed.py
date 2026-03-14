"""Tests for sources/indeed.py — Indeed Chrome source."""

import json
from unittest.mock import patch, MagicMock

from sources.indeed import IndeedSource


MOCK_QUERIES = ["customer success"]

MOSAIC_DATA = {
    "metaData": {
        "mosaicProviderJobCardsModel": {
            "results": [
                {
                    "title": "Customer Success Manager",
                    "company": "SecureTech",
                    "jobkey": "abc123",
                    "formattedLocation": "Remote",
                    "salarySnippet": {"text": "$130,000 - $160,000 a year"},
                    "snippets": ["Lead customer success initiatives in cybersecurity"],
                    "formattedRelativeTime": "3 days ago",
                },
                {
                    "title": "Frontend Developer",
                    "company": "WebCo",
                    "jobkey": "def456",
                    "formattedLocation": "San Francisco, CA",
                    "salarySnippet": {"text": "$140,000 - $180,000 a year"},
                    "snippets": ["React and TypeScript developer"],
                    "formattedRelativeTime": "1 day ago",
                },
                {
                    "title": "Application Support Lead",
                    "company": "HealthOrg",
                    "jobkey": "ghi789",
                    "formattedLocation": "Remote in USA",
                    "salarySnippet": None,
                    "snippets": ["Troubleshoot application issues"],
                    "formattedRelativeTime": "Just posted",
                },
            ]
        }
    }
}


def _build_html(data=None):
    js_data = json.dumps(data or MOSAIC_DATA)
    return f'<html><body><script>window.mosaic.providerData["mosaic-provider-jobcards"]={js_data};</script></body></html>'


def _make_source(html):
    source = IndeedSource()
    source._page = MagicMock()
    source._page.content.return_value = html
    source._page.goto = MagicMock()
    return source


# --- Unit tests ---


def test_matches_role():
    source = IndeedSource()
    assert source._matches_role("Customer Success Manager")
    assert source._matches_role("application support lead")
    assert not source._matches_role("Frontend Developer")


def test_parse_salary_range():
    source = IndeedSource()
    assert source._parse_salary("$130,000 - $160,000 a year") == (130000, 160000)


def test_parse_salary_k_format():
    source = IndeedSource()
    assert source._parse_salary("$130k-$160k") == (130000, 160000)


def test_parse_salary_empty():
    source = IndeedSource()
    assert source._parse_salary("") == (0, 0)


def test_parse_relative_date_days_ago():
    source = IndeedSource()
    result = source._parse_relative_date("3 days ago")
    assert result.year >= 2026


def test_parse_relative_date_just_posted():
    source = IndeedSource()
    result = source._parse_relative_date("Just posted")
    assert result.year >= 2026


def test_parse_relative_date_empty():
    source = IndeedSource()
    result = source._parse_relative_date("")
    assert result.year >= 2026


def test_extract_jobs_filters_by_role():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Lead" in titles
    assert "Frontend Developer" not in titles


def test_extract_jobs_source_name():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    assert all(j.source == "indeed" for j in jobs)


def test_extract_jobs_url_format():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.url == "https://www.indeed.com/viewjob?jk=abc123"


def test_extract_jobs_remote_detection():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.is_remote is True


def test_extract_jobs_salary():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 130000
    assert csm.salary_max == 160000


def test_extract_jobs_no_mosaic_data():
    source = _make_source("<html><body>No data here</body></html>")
    jobs = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_captcha_detected():
    source = _make_source("<html><body>Please verify you are not a robot. CAPTCHA required.</body></html>")
    jobs = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_invalid_json():
    html = '<html><body><script>window.mosaic.providerData["mosaic-provider-jobcards"]={bad json};</script></body></html>'
    source = _make_source(html)
    jobs = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_null_salary():
    source = _make_source(_build_html())
    jobs = source._extract_jobs()
    app_support = next(j for j in jobs if j.title == "Application Support Lead")
    assert app_support.salary_min == 0
    assert app_support.salary_max == 0


@patch("sources.indeed.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_collect_deduplicates():
    source = IndeedSource()
    source._page = MagicMock()
    source._page.content.return_value = _build_html()
    source._page.goto = MagicMock()

    with patch("sources.chrome_base.time.sleep"):
        jobs = source.collect()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))
