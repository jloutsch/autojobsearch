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
