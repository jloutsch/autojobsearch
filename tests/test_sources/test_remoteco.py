"""Tests for sources/remoteco.py — Remote.co Chrome source."""

from unittest.mock import patch, MagicMock

from sources.remoteco import RemoteCoSource


MOCK_QUERIES = ["customer success"]

SAMPLE_HTML = """
<html><body>
<a href="/job-details/customer-success-manager-at-techco/">New!Today Customer Success Manager</a>
<a href="/job-details/frontend-developer/">Frontend Developer</a>
<a href="/job-details/application-support-lead/">Application Support Lead</a>
<a href="/about/">About Us</a>
</body></html>
"""


def _make_source(html):
    source = RemoteCoSource()
    source._page = MagicMock()
    source._page.content.return_value = html
    source._page.goto = MagicMock()
    source._page.wait_for_selector = MagicMock()
    return source


# --- Unit tests ---


def test_matches_role():
    source = RemoteCoSource()
    assert source._matches_role("Customer Success Manager")
    assert source._matches_role("application support lead")
    assert not source._matches_role("Frontend Developer")


def test_extract_jobs_filters_by_role():
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    titles = [j.title for j in jobs]
    assert "Customer Success Manager" in titles
    assert "Application Support Lead" in titles
    assert "Frontend Developer" not in titles


def test_extract_jobs_strips_badge_prefix():
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.title == "Customer Success Manager"
    assert "New!" not in csm.title
    assert "Today" not in csm.title


def test_extract_jobs_source_name():
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    assert all(j.source == "remoteco" for j in jobs)


def test_extract_jobs_url_prefix():
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    csm = next(j for j in jobs if "Customer Success" in j.title)
    assert csm.url.startswith("https://remote.co/")
    assert "/job-details/" in csm.url


def test_extract_jobs_relative_url_gets_domain():
    """Relative hrefs get https://remote.co prepended."""
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    for job in jobs:
        assert job.url.startswith("https://remote.co")


def test_extract_jobs_all_remote():
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    assert all(j.is_remote is True for j in jobs)


def test_extract_jobs_company_empty():
    """Company is not available in Remote.co search results."""
    source = _make_source(SAMPLE_HTML)
    jobs = source._extract_jobs()
    assert all(j.company == "" for j in jobs)


def test_extract_jobs_empty_page():
    source = _make_source("<html><body>No jobs found</body></html>")
    jobs = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_ignores_non_job_links():
    """Links without /job-details/ in href are ignored."""
    html = """
    <html><body>
    <a href="/about/">About</a>
    <a href="/remote-jobs/">Browse</a>
    </body></html>
    """
    source = _make_source(html)
    jobs = source._extract_jobs()
    assert jobs == []


def test_extract_jobs_absolute_url_kept():
    html = '<html><body><a href="https://remote.co/job-details/support-manager/">Customer Success Manager</a></body></html>'
    source = _make_source(html)
    jobs = source._extract_jobs()
    assert len(jobs) == 1
    assert jobs[0].url == "https://remote.co/job-details/support-manager/"


def test_extract_jobs_badge_variations():
    """Various badge prefixes are stripped."""
    html = """
    <html><body>
    <a href="/job-details/a/">New! Customer Success Lead</a>
    <a href="/job-details/b/">Yesterday Application Support Specialist</a>
    <a href="/job-details/c/">3 days ago Solutions Engineering Lead</a>
    </body></html>
    """
    source = _make_source(html)
    jobs = source._extract_jobs()
    titles = [j.title for j in jobs]
    assert "Customer Success Lead" in titles
    assert "Application Support Specialist" in titles
    assert "Solutions Engineering Lead" in titles


@patch("sources.remoteco.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_collect_deduplicates():
    source = RemoteCoSource()
    source._page = MagicMock()
    source._page.content.return_value = SAMPLE_HTML
    source._page.goto = MagicMock()
    source._page.wait_for_selector = MagicMock()

    with patch("sources.chrome_base.time.sleep"):
        jobs = source.collect()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


@patch("sources.remoteco.config.SEARCH_QUERIES", MOCK_QUERIES)
def test_search_stops_on_no_selector():
    """If wait_for_selector raises, pagination stops."""
    source = RemoteCoSource()
    source._page = MagicMock()
    source._page.content.return_value = SAMPLE_HTML
    source._page.goto = MagicMock()
    source._page.wait_for_selector = MagicMock(side_effect=Exception("timeout"))

    with patch("sources.chrome_base.time.sleep"):
        jobs = source._search("customer success")

    assert jobs == []
