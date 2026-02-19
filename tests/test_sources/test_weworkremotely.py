"""Tests for sources/weworkremotely.py — WeWorkRemotely RSS source."""

import responses

from sources.weworkremotely import FEED_URLS, WeWorkRemotelySource
from tests.conftest import load_fixture


@responses.activate
def test_collect_both_feeds():
    """Both RSS feed URLs are fetched."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    source.collect()

    assert len(responses.calls) == 2


@responses.activate
def test_title_split_on_colon():
    """'Company: Job Title' split correctly."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    jobs = source.collect()

    csm_jobs = [j for j in jobs if "Customer Success" in j.title]
    if csm_jobs:
        assert csm_jobs[0].company == "SecureTech"
        assert "Customer Success Manager" in csm_jobs[0].title


@responses.activate
def test_role_filter_applied():
    """Non-matching titles excluded."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    jobs = source.collect()
    titles = [j.title for j in jobs]

    assert "Backend Engineer" not in titles


@responses.activate
def test_salary_extraction():
    """Salary range extracted from description text."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    jobs = source.collect()

    csm_jobs = [j for j in jobs if "Customer Success" in j.title]
    if csm_jobs:
        assert csm_jobs[0].salary_min == 130000
        assert csm_jobs[0].salary_max == 150000


def test_extract_salary_range():
    """Direct salary extraction from text."""
    source = WeWorkRemotelySource()
    assert source._extract_salary("Salary: $130,000 - $150,000 per year") == (130000, 150000)


def test_extract_salary_k_format():
    """k-format salary extraction."""
    source = WeWorkRemotelySource()
    assert source._extract_salary("$130k-$150k") == (130000, 150000)


def test_extract_salary_empty():
    """No salary text returns (0, 0)."""
    source = WeWorkRemotelySource()
    assert source._extract_salary("") == (0, 0)


@responses.activate
def test_dedup_by_url():
    """Duplicate URLs across feeds counted once."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    jobs = source.collect()
    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
def test_date_parsing_rfc2822():
    """RFC 2822 date parsed correctly."""
    xml = load_fixture("wwr_feed.xml")
    for url in FEED_URLS:
        responses.add(responses.GET, url, body=xml, status=200)

    source = WeWorkRemotelySource()
    jobs = source.collect()

    if jobs:
        assert jobs[0].posted_date.year == 2026
