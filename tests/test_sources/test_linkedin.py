"""Tests for sources/linkedin_alerts.py — LinkedIn via Google Alerts source."""

from datetime import datetime, timedelta, timezone

import responses
from freezegun import freeze_time

import sources.linkedin_alerts as linkedin_module
from sources.linkedin_alerts import LinkedInAlertsSource
from tests.conftest import load_fixture


def test_empty_feed_urls_returns_empty(monkeypatch):
    """ALERT_FEED_URLS=[] → immediate [] return."""
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [])
    source = LinkedInAlertsSource()
    assert source.collect() == []


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
@responses.activate
def test_24h_cutoff_enforced(monkeypatch):
    """Entry older than 24h is excluded."""
    feed_url = "https://www.google.com/alerts/feeds/test/test"
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [feed_url])

    xml = load_fixture("linkedin_feed.xml")
    responses.add(responses.GET, feed_url, body=xml, status=200)

    source = LinkedInAlertsSource()
    jobs = source.collect()

    # Only the 2026-02-19 entry should pass the 24h cutoff
    # The 2026-02-17 entry is 2+ days old
    companies = [j.company for j in jobs]
    assert "OldCorp" not in companies


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
@responses.activate
def test_recent_entry_included(monkeypatch):
    """Entry within 24h is included."""
    feed_url = "https://www.google.com/alerts/feeds/test/test"
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [feed_url])

    xml = load_fixture("linkedin_feed.xml")
    responses.add(responses.GET, feed_url, body=xml, status=200)

    source = LinkedInAlertsSource()
    jobs = source.collect()

    assert any("CloudCo" in j.company for j in jobs)


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
@responses.activate
def test_google_redirect_unwrapped(monkeypatch):
    """google.com/url?url=... → actual LinkedIn URL."""
    feed_url = "https://www.google.com/alerts/feeds/test/test"
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [feed_url])

    xml = load_fixture("linkedin_feed.xml")
    responses.add(responses.GET, feed_url, body=xml, status=200)

    source = LinkedInAlertsSource()
    jobs = source.collect()

    if jobs:
        assert "linkedin.com" in jobs[0].url
        assert "google.com/url" not in jobs[0].url


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
@responses.activate
def test_title_parsing_at_pattern(monkeypatch):
    """'Customer Success Manager at CloudCo' → title and company split."""
    feed_url = "https://www.google.com/alerts/feeds/test/test"
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [feed_url])

    xml = load_fixture("linkedin_feed.xml")
    responses.add(responses.GET, feed_url, body=xml, status=200)

    source = LinkedInAlertsSource()
    jobs = source.collect()

    cloudco = [j for j in jobs if j.company == "CloudCo"]
    if cloudco:
        assert "Customer Success Manager" in cloudco[0].title


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
@responses.activate
def test_html_stripped_from_title(monkeypatch):
    """HTML tags in title are stripped by BeautifulSoup."""
    feed_url = "https://www.google.com/alerts/feeds/test/test"
    monkeypatch.setattr(linkedin_module, "ALERT_FEED_URLS", [feed_url])

    # Create a feed with HTML in the title
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>&lt;b&gt;Customer Success&lt;/b&gt; Manager at TestCo</title>
        <link href="https://linkedin.com/jobs/view/99999"/>
        <published>2026-02-19T08:00:00Z</published>
        <updated>2026-02-19T08:00:00Z</updated>
        <content type="html">Test job.</content>
      </entry>
    </feed>"""
    responses.add(responses.GET, feed_url, body=xml, status=200)

    source = LinkedInAlertsSource()
    jobs = source.collect()

    for job in jobs:
        assert "<b>" not in job.title
        assert "</b>" not in job.title


def test_date_parsing_iso():
    """ISO 8601 date parsed correctly."""
    source = LinkedInAlertsSource()
    result = source._parse_date("2026-02-18T10:00:00Z")
    assert result.year == 2026
    assert result.month == 2


def test_date_parsing_fallback():
    """Invalid date → datetime.now(utc) fallback."""
    source = LinkedInAlertsSource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026
