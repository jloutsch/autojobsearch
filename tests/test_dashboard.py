"""Tests for dashboard.py — HTML dashboard generation."""

import os

from freezegun import freeze_time

from dashboard import _format_age, _render_row, generate_dashboard


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
