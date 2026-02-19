"""Tests for archive.py — markdown report generation."""

import os

from freezegun import freeze_time

from archive import _format_posted, save_daily_report


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_creates_markdown_file(tmp_path):
    """A .md file is created in output dir."""
    filepath = save_daily_report([], output_dir=str(tmp_path))
    assert os.path.exists(filepath)
    assert filepath.endswith(".md")


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_jobs_grouped_by_priority(tmp_path):
    """High/medium/low sections present."""
    jobs = [
        {"title": "High Job", "company": "A", "url": "#", "score": 80,
         "priority": "high", "source": "test", "salary_min": 0, "salary_max": 0},
        {"title": "Med Job", "company": "B", "url": "#", "score": 50,
         "priority": "medium", "source": "test", "salary_min": 0, "salary_max": 0},
        {"title": "Low Job", "company": "C", "url": "#", "score": 20,
         "priority": "low", "source": "test", "salary_min": 0, "salary_max": 0},
    ]
    filepath = save_daily_report(jobs, output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()

    assert "## High Priority" in content
    assert "## Worth a Look" in content
    assert "## Other Matches" in content


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_empty_jobs_list(tmp_path):
    """Empty input produces valid report."""
    filepath = save_daily_report([], output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()

    assert "No new matching jobs" in content


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_posted_today():
    """Today's date → 'Today'."""
    assert _format_posted("2026-02-19T10:00:00+00:00") == "Today"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_posted_yesterday():
    """Yesterday → 'Yesterday'."""
    assert _format_posted("2026-02-18T10:00:00+00:00") == "Yesterday"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_posted_days_ago():
    """3 days ago → '3 days ago'."""
    assert _format_posted("2026-02-16T10:00:00+00:00") == "3 days ago"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_format_posted_old():
    """10+ days ago → YYYY-MM-DD format."""
    assert _format_posted("2026-02-01T10:00:00+00:00") == "2026-02-01"


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_report_includes_job_details(tmp_path):
    """Report includes job title, company, score, source."""
    jobs = [
        {"title": "Test CSM", "company": "TestCorp", "url": "https://example.com",
         "score": 42, "priority": "high", "source": "greenhouse",
         "salary_min": 130000, "salary_max": 150000,
         "posted_date": "2026-02-18T10:00:00+00:00",
         "location": "Remote", "summary": "Good match."},
    ]
    filepath = save_daily_report(jobs, output_dir=str(tmp_path))
    with open(filepath) as f:
        content = f.read()

    assert "Test CSM" in content
    assert "TestCorp" in content
    assert "greenhouse" in content
    assert "$130,000" in content
