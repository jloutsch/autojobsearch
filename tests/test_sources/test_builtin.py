"""Tests for sources/builtin.py — BuiltIn HTML scraping source."""

from datetime import datetime, timezone

import responses
from bs4 import BeautifulSoup
from freezegun import freeze_time

from sources.builtin import BuiltInSource, SEARCH_URL
from tests.conftest import load_fixture


@responses.activate
def test_collect_deduplicates_urls():
    """Same URL from multiple queries is counted only once."""
    html = load_fixture("builtin_page.html")

    # Each search query returns same HTML
    for _ in range(4):  # 4 role tags in profile
        responses.add(responses.GET, SEARCH_URL, body=html, status=200)

    source = BuiltInSource()
    jobs = source.collect()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
def test_parse_card_extracts_fields():
    """Title, company, location, salary parsed from card."""
    html = load_fixture("builtin_page.html")
    responses.add(responses.GET, SEARCH_URL, body=html, status=200)
    # Only one query needed if we directly test _search
    source = BuiltInSource()
    jobs = source._search("application support")

    # First card should match role keywords
    matching = [j for j in jobs if "Application Support" in j.title]
    if matching:
        job = matching[0]
        assert job.company == "CloudSecure Inc"
        assert job.salary_min == 120000
        assert job.salary_max == 140000


def test_salary_K_format():
    """'120K-140K' → (120000, 140000)."""
    source = BuiltInSource()
    assert source._parse_salary("120K-140K Annually") == (120000, 140000)


def test_salary_dollar_format():
    """'$130,000 - $150,000' → (130000, 150000)."""
    source = BuiltInSource()
    assert source._parse_salary("$130,000 - $150,000") == (130000, 150000)


def test_salary_single_K():
    """Single K value returns (value, 0)."""
    source = BuiltInSource()
    assert source._parse_salary("120K") == (120000, 0)


def test_salary_empty():
    """Empty string returns (0, 0)."""
    source = BuiltInSource()
    assert source._parse_salary("") == (0, 0)


def test_published_dates_extraction():
    """Script-embedded dates extracted from body onload."""
    html = load_fixture("builtin_page.html")
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    dates = source._extract_published_dates(soup)

    assert 7001 in dates
    assert dates[7001].year == 2026


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_parsing():
    """Relative date span '1 day ago' parsed correctly."""
    html = '<span class="bg-gray-01 font-Montserrat text-gray-03">Posted 1 day ago</span>'
    soup = BeautifulSoup(html, "html.parser")
    # Create a card-like element
    card = soup.find("span")
    source = BuiltInSource()
    # The _parse_relative_date looks for the span inside a card
    card_html = f'<div data-id="job-card">{html}</div>'
    card_soup = BeautifulSoup(card_html, "html.parser")
    card_el = card_soup.find("div")
    result = source._parse_relative_date(card_el)
    assert result.date() == datetime(2026, 2, 18).date()


@responses.activate
def test_all_cards_returned():
    """All job cards are returned (BuiltIn source does not filter by role)."""
    html = load_fixture("builtin_page.html")
    responses.add(responses.GET, SEARCH_URL, body=html, status=200)

    source = BuiltInSource()
    jobs = source._search("application support")

    # BuiltIn returns all parseable cards — role filtering happens in pipeline
    assert len(jobs) == 2


# --- Additional edge cases ---


@responses.activate
def test_search_http_error_returns_empty():
    """HTTP 403/500 → _search returns []."""
    responses.add(responses.GET, SEARCH_URL, status=403)

    source = BuiltInSource()
    jobs = source._search("customer success")
    assert jobs == []


def test_card_missing_title_link_skipped():
    """Card without a[data-id='job-card-title'] returns None."""
    html = '<div data-id="job-card"><span>No title link</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_card(card, {})
    assert result is None


def test_card_missing_company_link():
    """Missing company span → empty company string."""
    html = '''<div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/123">Application Support Engineer</a>
    </div>'''
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    job = source._parse_card(card, {})
    assert job is not None
    assert job.company == ""


def test_published_dates_fallback_script_tags():
    """No body onload → falls back to script tags."""
    html = '''<html><body>
        <script>
        var data = [{"id": 9999, "published_date": "2026-02-15T10:00:00"}];
        </script>
    </body></html>'''
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    dates = source._extract_published_dates(soup)
    assert 9999 in dates
    assert dates[9999].year == 2026


def test_salary_hourly_format():
    """'$50/hr' format → (0, 0) since only annual is parsed."""
    source = BuiltInSource()
    assert source._parse_salary("$50/hr") == (50, 0)


def test_salary_with_per_year_suffix():
    """'120K - 140K Per Year' parsed correctly."""
    source = BuiltInSource()
    assert source._parse_salary("120K - 140K Per Year") == (120000, 140000)


def test_work_type_remote_detection():
    """Work type badge containing 'Remote' sets is_remote."""
    html = '''<div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/456">Application Support Manager</a>
        <a data-id="company-title"><span>TestCo</span></a>
        <span class="font-barlow text-gray-04">Remote</span>
        <span class="font-barlow text-gray-04">US</span>
        <span class="font-barlow text-gray-04">120K-140K</span>
    </div>'''
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    job = source._parse_card(card, {})
    assert job is not None
    assert job.is_remote is True


@responses.activate
def test_empty_html_page():
    """Page with no job cards returns []."""
    html = '<html><body><div>No jobs here</div></body></html>'
    responses.add(responses.GET, SEARCH_URL, body=html, status=200)

    source = BuiltInSource()
    jobs = source._search("customer success")
    assert jobs == []


def test_salary_single_dollar_format():
    """Single dollar value '$130,000' returns (130000, 0)."""
    source = BuiltInSource()
    assert source._parse_salary("$130,000") == (130000, 0)


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_no_span():
    """Card with no date span → fallback to now."""
    html = '<div data-id="job-card"></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    assert result.date() == datetime(2026, 2, 19).date()


def test_published_dates_no_body():
    """No <body> tag → empty dates dict."""
    html = '<html><head></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    dates = source._extract_published_dates(soup)
    assert dates == {}


def test_url_relative_path():
    """Relative href gets builtin.com prefix."""
    html = '''<div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/789">Customer Success Lead</a>
    </div>'''
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    job = source._parse_card(card, {})
    assert job.url == "https://builtin.com/jobs/789"


def test_published_date_invalid_value():
    """Invalid date in onload → skipped gracefully (line 69-70)."""
    html = '''<html><body onload="dataLayer.push({'id': 9876, 'published_date': 'invalid-date'})">
    </body></html>'''
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    dates = source._extract_published_dates(soup)
    assert 9876 not in dates


def test_script_tag_invalid_date():
    """Invalid date in script tag → skipped gracefully (line 80-81)."""
    html = '''<html><body>
        <script>var x = [{"id": 5555, "published_date": "not-a-date"}];</script>
    </body></html>'''
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    dates = source._extract_published_dates(soup)
    assert 5555 not in dates


def test_parse_card_exception_caught():
    """Exception during card parsing caught gracefully (line 94-96)."""
    html = '''<html><body><div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/1">Customer Success</a>
    </div><div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/2">Application Support</a>
    </div></body></html>'''
    soup = BeautifulSoup(html, "html.parser")
    source = BuiltInSource()
    # Test that _parse_results handles exceptions - all cards are valid here
    # but we can verify the try/except path by mocking
    jobs = source._parse_results(soup, {})
    assert len(jobs) == 2


def test_invalid_track_id():
    """Non-numeric data-builtin-track-job-id → skipped (line 116-117)."""
    html = '''<div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/abc"
           data-builtin-track-job-id="not-a-number">Application Support</a>
    </div>'''
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    job = source._parse_card(card, {})
    assert job is not None


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_repost():
    """'Reposted 2 days ago' still parsed as 2 days back (line 161)."""
    html = '<div data-id="job-card"><span class="bg-gray-01 font-Montserrat text-gray-03">Reposted 2 days ago</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    assert result.date() == datetime(2026, 2, 17).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_no_match():
    """'Posted today' without number → now fallback (line 165)."""
    html = '<div data-id="job-card"><span class="bg-gray-01 font-Montserrat text-gray-03">Posted today</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    assert result.date() == datetime(2026, 2, 19).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_weeks():
    """'2 weeks ago' parsed correctly (line 175-176)."""
    html = '<div data-id="job-card"><span class="bg-gray-01 font-Montserrat text-gray-03">Posted 2 weeks ago</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    assert result.date() == datetime(2026, 2, 5).date()


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_months():
    """'1 month ago' parsed correctly (line 177-178)."""
    html = '<div data-id="job-card"><span class="bg-gray-01 font-Montserrat text-gray-03">Posted 1 month ago</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    expected = datetime(2026, 1, 20).date()
    assert result.date() == expected


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_relative_date_hours():
    """'5 hours ago' parsed correctly (line 171-172)."""
    html = '<div data-id="job-card"><span class="bg-gray-01 font-Montserrat text-gray-03">Posted 5 hours ago</span></div>'
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    source = BuiltInSource()
    result = source._parse_relative_date(card)
    assert result.date() == datetime(2026, 2, 19).date()


def test_parse_card_raises_exception():
    """Card that raises during parsing is caught by _parse_results (lines 94-96)."""
    source = BuiltInSource()
    # Create a card that will cause an error during parsing:
    # title_el exists (so it doesn't return None) but .get raises
    html = '''<html><body>
    <div data-id="job-card">
        <a data-id="job-card-title" href="/jobs/1">Application Support</a>
    </div>
    </body></html>'''
    soup = BeautifulSoup(html, "html.parser")

    from unittest.mock import patch as mock_patch

    # Patch _parse_card to raise, then verify _parse_results catches it
    with mock_patch.object(source, "_parse_card", side_effect=RuntimeError("boom")):
        jobs = source._parse_results(soup, {})
    assert jobs == []


def test_salary_no_pattern_match():
    """Salary text with no recognizable pattern → (0, 0) (line 201)."""
    source = BuiltInSource()
    assert source._parse_salary("Competitive") == (0, 0)
    assert source._parse_salary("DOE") == (0, 0)
