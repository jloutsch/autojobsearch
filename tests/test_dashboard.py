"""Tests for dashboard.py — HTML dashboard generation."""

import os

from freezegun import freeze_time

import pytest

from dashboard import _format_age, _render_row, generate_dashboard
from sanitize import safe_url as _safe_url


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_generate_creates_file(tmp_path):
    """HTML file created at expected path."""
    jobs = [
        {
            "title": "CSM",
            "company": "TestCorp",
            "url": "https://example.com/1",
            "source": "test",
            "score": 45,
            "priority": "high",
            "salary_min": 130000,
            "salary_max": 150000,
            "location": "Remote",
            "posted_date": "2026-02-18T10:00:00+00:00",
            "description": "A test job.",
            "summary": "Good fit.",
            "key_matches": [],
            "gaps": [],
        }
    ]
    filepath = generate_dashboard(jobs, output_dir=str(tmp_path))
    assert os.path.exists(filepath)
    assert filepath.endswith(".html")


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_empty_jobs_list(tmp_path):
    """Empty input produces valid HTML with no rows."""
    filepath = generate_dashboard([], output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert "No new matching jobs" in content


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_profile_embedded_as_json(tmp_path):
    """Profile dict serialized in <script> tag."""
    filepath = generate_dashboard([], output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()
    assert "DEFAULT_PROFILE" in content
    # Profile JSON should contain role_tags from the fixture
    assert "application support" in content


def test_xss_prevention_priority():
    """Invalid priority value whitelisted to 'low'."""
    job = {
        "title": "Test",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 10,
        "priority": '<script>alert(1)</script>',
        "salary_min": 0,
        "salary_max": 0,
        "location": "Remote",
        "posted_date": "",
        "summary": "",
    }
    html = _render_row(job)
    assert '<script>alert(1)</script>' not in html
    assert 'priority-low' in html


def test_xss_prevention_posted_date():
    """Script tag in posted_date is escaped."""
    job = {
        "title": "Test",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 10,
        "priority": "low",
        "salary_min": 0,
        "salary_max": 0,
        "location": "Remote",
        "posted_date": '<script>alert(1)</script>',
        "summary": "",
    }
    html = _render_row(job)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_just_now():
    """30 seconds ago → 'Just now'."""
    assert _format_age("2026-02-19T11:59:30+00:00") == "Just now"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_hours():
    """3 hours ago → '3h ago'."""
    assert _format_age("2026-02-19T09:00:00+00:00") == "3h ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_days():
    """2 days ago → '2 days ago'."""
    assert _format_age("2026-02-17T12:00:00+00:00") == "2 days ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_empty():
    """Empty string → empty string."""
    assert _format_age("") == ""


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_invalid():
    """Invalid date → empty string."""
    assert _format_age("not-a-date") == ""


def test_render_row_salary_range():
    """Salary range rendered correctly."""
    job = {
        "title": "CSM",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 30,
        "priority": "medium",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote",
        "posted_date": "",
        "summary": "Good fit.",
    }
    html = _render_row(job)
    assert "$130,000" in html
    assert "$150,000" in html


def test_render_row_no_salary():
    """No salary → empty salary cell."""
    job = {
        "title": "CSM",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 30,
        "priority": "low",
        "salary_min": 0,
        "salary_max": 0,
        "location": "Remote",
        "posted_date": "",
        "summary": "",
    }
    html = _render_row(job)
    assert 'class="salary">' in html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_landing_page(tmp_path):
    """generate_dashboard with filename='index.html' creates landing page."""
    from dashboard import generate_landing_page

    filepath = generate_landing_page(output_dir=str(tmp_path))
    assert filepath.endswith("index.html")
    with open(filepath) as f:
        content = f.read()
    assert "Run Search" in content


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_past_results_button_rendered(tmp_path):
    """Dashboard HTML contains the Past Results button and dropdown."""
    filepath = generate_dashboard([], output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()
    assert "Past Results" in content
    assert "historyDropdown" in content
    assert "toggleHistory()" in content


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_past_results_js_included(tmp_path):
    """Dashboard includes JavaScript for loading and displaying past reports."""
    filepath = generate_dashboard([], output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()
    assert "/api/reports" in content
    assert "loadHistory" in content


# --- Additional edge cases ---


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_generate_landing_page_creates_index(tmp_path):
    """generate_landing_page creates index.html with correct content."""
    from dashboard import generate_landing_page
    filepath = generate_landing_page(output_dir=str(tmp_path))
    assert filepath.endswith("index.html")
    assert os.path.exists(filepath)
    with open(filepath) as f:
        content = f.read()
    assert "Run Search" in content
    assert "<!DOCTYPE html>" in content


def test_render_row_with_summary():
    """AI summary rendered in row."""
    job = {
        "title": "CSM",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 45,
        "priority": "high",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote",
        "posted_date": "2026-02-18T10:00:00+00:00",
        "summary": "Great fit for cybersecurity background.",
    }
    html = _render_row(job)
    assert "Great fit for cybersecurity background." in html
    assert "priority-high" in html


def test_render_row_html_escaping_title():
    """XSS in title/company escaped."""
    job = {
        "title": '<script>alert("xss")</script>',
        "company": '<img onerror="alert(1)">',
        "url": "https://example.com",
        "source": "test",
        "score": 10,
        "priority": "low",
        "salary_min": 0,
        "salary_max": 0,
        "location": "Remote",
        "posted_date": "",
        "summary": "",
    }
    html = _render_row(job)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert '<img' not in html
    assert '&lt;img' in html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_generate_dashboard_custom_filename(tmp_path):
    """Custom filename parameter works."""
    filepath = generate_dashboard(
        [], output_dir=str(tmp_path), filename="custom.html"
    )
    assert filepath.endswith("custom.html")
    assert os.path.exists(filepath)


def test_salary_min_only():
    """salary_min > 0 but salary_max = 0 → '$X+' display."""
    job = {
        "title": "CSM",
        "company": "Corp",
        "url": "https://example.com",
        "source": "test",
        "score": 30,
        "priority": "medium",
        "salary_min": 120000,
        "salary_max": 0,
        "location": "Remote",
        "posted_date": "",
        "summary": "",
    }
    html = _render_row(job)
    assert "$120,000+" in html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_naive_datetime():
    """Naive datetime (no tzinfo) treated as UTC (line 1334-1335)."""
    result = _format_age("2026-02-19T11:00:00")
    assert result == "1h ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_one_week():
    """8 days ago → '1 week ago' (line 1347-1348)."""
    result = _format_age("2026-02-11T12:00:00+00:00")
    assert result == "1 week ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_weeks():
    """16 days ago → '2 weeks ago' (line 1349-1350)."""
    result = _format_age("2026-02-03T12:00:00+00:00")
    assert result == "2 weeks ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_one_month():
    """35 days ago → '1 month ago' (line 1351-1352)."""
    result = _format_age("2026-01-15T12:00:00+00:00")
    assert result == "1 month ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_age_months():
    """90 days ago → '3 months ago' (line 1353-1354)."""
    result = _format_age("2025-11-21T12:00:00+00:00")
    assert result == "3 months ago"


# --- href scheme safety ---
#
# Job URLs are scraped from third parties and the dashboard is served over HTTP
# alongside the /api/profile endpoints, so a script URL here would run against
# an origin that can read the user's resume. html.escape does not stop one.


@pytest.mark.parametrize("hostile", [
    "javascript:eval(atob(YWxlcnQoMSk))",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "",
    None,
])
def test_safe_url_rejects_non_http_schemes(hostile):
    assert _safe_url(hostile) == "#"


@pytest.mark.parametrize("legit", [
    "https://boards.greenhouse.io/foo/jobs/123",
    "http://example.com/job?a=1&b=2",
    "https://www.linkedin.com/jobs/view/456/",
])
def test_safe_url_preserves_real_links(legit):
    assert _safe_url(legit) == legit


def test_render_row_strips_script_url():
    """End to end: a hostile URL never reaches the rendered href."""
    row = _render_row({
        "title": "Job", "company": "C", "url": "javascript:eval(atob(x))",
        "score": 80, "priority": "high", "source": "s", "location": "Remote",
        "summary": "", "posted_date": "2026-02-18T00:00:00+00:00",
        "salary_min": 0, "salary_max": 0,
    })
    assert "javascript:" not in row
    assert 'href="#"' in row


# --- company links ---


def _row(**overrides):
    job = {
        "title": "CSM", "company": "Datadog", "url": "https://example.com/1",
        "score": 80, "priority": "high", "source": "greenhouse",
        "location": "Remote", "summary": "", "posted_date": "2026-02-18T00:00:00+00:00",
        "salary_min": 0, "salary_max": 0,
    }
    job.update(overrides)
    return _render_row(job)


def test_company_renders_as_a_search_link():
    row = _row(company="Datadog")
    assert 'class="company-link"' in row
    assert "https://www.google.com/search?q=Datadog" in row
    assert ">Datadog</a>" in row


def test_company_link_opens_in_a_new_tab_safely():
    row = _row(company="Datadog")
    assert 'target="_blank"' in row
    assert 'rel="noopener noreferrer"' in row


def test_empty_company_renders_plain_text_not_an_empty_link():
    row = _row(company="")
    assert "company-link" not in row
    assert 'href="#"' not in row


def test_hostile_company_name_cannot_escape_the_href():
    """The name must not be able to terminate the href attribute.

    The bare substring "onmouseover=" legitimately survives in the visible link
    text: html.escape() neutralises the quotes around it but has no reason to
    escape "=". What matters is that no attribute-breaking form reaches the
    markup and that the href itself is fully percent-encoded.
    """
    row = _row(company='Evil" onmouseover="alert(1)')

    # No attribute-breaking form: the quote that would close href is escaped.
    assert 'onmouseover="' not in row
    # The hostile characters are percent-encoded inside the href.
    assert "onmouseover%3D" in row
    assert 'class="company-link"' in row


def test_job_title_link_is_unaffected():
    """Regression: the title anchor keeps its own safe_url treatment."""
    row = _row(url="https://example.com/1")
    assert '<a href="https://example.com/1"' in row
    assert 'class="job-title"' in row

    blocked = _row(url="javascript:alert(1)")
    assert "javascript:" not in blocked
    assert 'href="#"' in blocked
