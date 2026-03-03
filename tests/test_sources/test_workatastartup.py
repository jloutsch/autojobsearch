"""Tests for sources/workatastartup.py — YC Work at a Startup HTML scraping source."""

import responses

from sources.workatastartup import BASE_URL, WorkAtAStartupSource
from tests.conftest import load_fixture


@responses.activate
def test_collect_fetches_both_roles():
    """Both role=support and role=sales are fetched."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    source.collect()

    assert len(responses.calls) == 2


@responses.activate
def test_role_filter_applied():
    """Non-matching titles excluded."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    titles = [j.title for j in jobs]

    assert "Senior Software Engineer" not in titles


@responses.activate
def test_matching_jobs_returned():
    """Jobs matching role keywords are returned."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    titles = [j.title for j in jobs]

    assert "Customer Success Lead" in titles
    assert "Customer Success Engineer" in titles
    assert "Application Support Engineer" in titles


@responses.activate
def test_company_yc_batch_stripped():
    """YC batch suffix like '(W25)' stripped from company name."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.company == "SecureAI"
    assert "(W25)" not in csm.company


@responses.activate
def test_company_without_batch():
    """Company without YC batch kept as-is."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    cse = next(j for j in jobs if "Customer Success Engineer" in j.title)
    assert cse.company == "CloudMetrics"


@responses.activate
def test_url_construction():
    """Relative hrefs get full URL prefix."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    for job in jobs:
        assert job.url.startswith("https://")


@responses.activate
def test_remote_detection():
    """Location containing 'Remote' sets is_remote=True."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success Lead" in j.title)
    assert csm.is_remote is True

    cse = next(j for j in jobs if "Customer Success Engineer" in j.title)
    assert cse.is_remote is True


@responses.activate
def test_non_remote_detection():
    """Location without 'Remote' sets is_remote=False."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    app = next(j for j in jobs if "Application Support" in j.title)
    assert app.is_remote is False


@responses.activate
def test_dedup_across_roles():
    """Same URL from both role queries counted once."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@responses.activate
def test_source_name():
    """Source set to 'workatastartup'."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    assert all(j.source == "workatastartup" for j in jobs)


@responses.activate
def test_posted_date_is_now():
    """posted_date set to datetime.now() since page has no dates."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    for job in jobs:
        assert job.posted_date.year >= 2026


# --- Edge cases ---


def test_clean_company_w_batch():
    """'Company (W25)' → 'Company'."""
    source = WorkAtAStartupSource()
    assert source._clean_company("SecureAI (W25)") == "SecureAI"


def test_clean_company_s_batch():
    """'Company (S24)' → 'Company'."""
    source = WorkAtAStartupSource()
    assert source._clean_company("DataFlow (S24)") == "DataFlow"


def test_clean_company_no_batch():
    """'CloudMetrics' → 'CloudMetrics' unchanged."""
    source = WorkAtAStartupSource()
    assert source._clean_company("CloudMetrics") == "CloudMetrics"


@responses.activate
def test_http_error_returns_empty():
    """HTTP error → returns [] from _fetch_page."""
    responses.add(responses.GET, BASE_URL, status=403)
    responses.add(responses.GET, BASE_URL, status=403)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
def test_empty_html_page():
    """Page with no job links returns []."""
    html = "<html><body><div>No jobs here</div></body></html>"
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()
    assert jobs == []


@responses.activate
def test_location_extraction():
    """Location parsed from second span in p.job-details."""
    html = load_fixture("workatastartup_page.html")
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    jobs = source.collect()

    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert "Remote" in csm.location


@responses.activate
def test_parse_exception_caught():
    """Exception during job parsing caught gracefully."""
    html = """<html><body>
    <div class="company-details">
        <span class="font-bold">TestCo (W25)</span>
        <a data-jobid="1" class="font-bold" href="/jobs/1">Customer Success Manager</a>
    </div>
    <div class="company-details">
        <span class="font-bold">OtherCo</span>
        <a data-jobid="2" class="font-bold" href="/jobs/2">Application Support Lead</a>
    </div>
    </body></html>"""
    responses.add(responses.GET, BASE_URL, body=html, status=200)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    source = WorkAtAStartupSource()
    from unittest.mock import patch

    original_parse = source._parse_job
    call_count = [0]

    def flaky_parse(link, soup):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")
        return original_parse(link, soup)

    with patch.object(source, "_parse_job", side_effect=flaky_parse):
        jobs = source._fetch_page("support")

    # Second job should still be parsed despite first failing
    assert len(jobs) >= 1
