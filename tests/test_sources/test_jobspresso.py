"""Tests for sources/jobspresso.py — Jobspresso RSS source."""

from unittest.mock import patch

import responses

from sources.jobspresso import FEED_BASE, JobspressoSource
from tests.conftest import load_fixture

MOCK_QUERIES = ["application support", "customer success"]


def _mock_feed_urls():
    """Return the feed URLs that would be built from MOCK_QUERIES."""
    return [FEED_BASE + q.replace(" ", "+") for q in MOCK_QUERIES]


def _add_responses_for_queries(body):
    """Add mock responses for each query's feed URL."""
    for url in _mock_feed_urls():
        responses.add(responses.GET, url, body=body, status=200)


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_collect_both_feeds():
    """Both keyword feed URLs are fetched."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    source.collect()

    assert len(responses.calls) == len(MOCK_QUERIES)


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_role_filter_applied():
    """Non-matching titles excluded."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()
    titles = [j.title for j in jobs]

    assert "Senior Software Engineer" not in titles


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_dc_creator_company_extraction():
    """Company parsed from dc:creator field."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.company == "SecureTech"


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_dc_creator_location_extraction():
    """Location parsed from dc:creator after <br> marker."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert "Remote" in csm.location


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_salary_extraction_from_description():
    """Salary range extracted from content:encoded text."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.salary_min == 130000
    assert csm.salary_max == 150000


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_salary_k_format():
    """k-notation salary extracted correctly."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    asl = next(j for j in jobs if "Application Support" in j.title)
    assert asl.salary_min == 120000
    assert asl.salary_max == 140000


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_dedup_across_queries():
    """Same URL from both keyword queries counted once."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()
    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_date_parsing_rfc2822():
    """RFC 2822 date parsed correctly."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    if jobs:
        assert jobs[0].posted_date.year == 2026


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_all_remote():
    """Every returned job has is_remote=True."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()
    assert all(j.is_remote is True for j in jobs)


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_html_stripped_from_description():
    """HTML tags stripped from description text."""
    xml = load_fixture("jobspresso_feed.xml")
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert "<p>" not in csm.description
    assert "Customer Success Manager" in csm.description


# --- Edge cases ---


def test_parse_creator_with_br():
    """Company<br>location split correctly."""
    source = JobspressoSource()
    company, location = source._parse_creator("Acme Corp<br>&#9906;&nbsp;New York, NY")
    assert company == "Acme Corp"
    assert "New York" in location


def test_parse_creator_no_br():
    """No <br> → company only, empty location."""
    source = JobspressoSource()
    company, location = source._parse_creator("Solo Company")
    assert company == "Solo Company"
    assert location == ""


def test_parse_creator_empty():
    """Empty string returns empty tuple."""
    source = JobspressoSource()
    assert source._parse_creator("") == ("", "")


def test_extract_salary_empty():
    """No salary text returns (0, 0)."""
    source = JobspressoSource()
    assert source._extract_salary("") == (0, 0)


def test_extract_salary_no_match():
    """Text without salary pattern returns (0, 0)."""
    source = JobspressoSource()
    assert source._extract_salary("Competitive salary with benefits.") == (0, 0)


def test_date_parsing_empty():
    """Empty date string → datetime.now()."""
    source = JobspressoSource()
    result = source._parse_date("")
    assert result.year >= 2026


def test_date_parsing_invalid():
    """Invalid date → datetime.now() fallback."""
    source = JobspressoSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_channel_missing_returns_empty():
    """RSS with no <channel> → empty list."""
    xml = '<?xml version="1.0" encoding="UTF-8"?><rss></rss>'
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_xml_parse_error_returns_empty():
    """Malformed XML → exception caught by safe_collect."""
    _add_responses_for_queries("not xml at all")

    source = JobspressoSource()
    jobs = source.safe_collect()
    assert jobs == []


@responses.activate
@patch("sources.jobspresso.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_description_fallback_to_description_tag():
    """When content:encoded missing, falls back to <description>."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <item>
          <title>Customer Success Manager</title>
          <link>https://jobspresso.co/job/1</link>
          <pubDate>Tue, 18 Feb 2026 10:00:00 +0000</pubDate>
          <description>Fallback description text.</description>
        </item>
      </channel>
    </rss>"""
    _add_responses_for_queries(xml)

    source = JobspressoSource()
    jobs = source.collect()
    assert len(jobs) >= 1
    assert "Fallback description" in jobs[0].description
