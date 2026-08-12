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


# --- untrusted text in markdown ---
#
# Job titles, companies and URLs are scraped. In a markdown link they can both
# break out of the link label and supply a script URL as the destination, so the
# scheme check alone is not sufficient — the link structure has to hold too.


def _hostile_job(**overrides):
    job = {
        "title": "Nice Job](javascript:alert(1)) and [more",
        "company": "Evil\nCo",
        "url": "javascript:alert(1)",
        "score": 90,
        "priority": "high",
        "source": "x",
        "location": "Remote\n### Forged Heading",
        "summary": "Line1\n## Forged\n\n[click](javascript:x)",
        "salary_min": 0,
        "salary_max": 0,
        "posted_date": "2026-02-18T10:00:00+00:00",
    }
    job.update(overrides)
    return job


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_no_script_url_reaches_a_link_destination(tmp_path):
    import re

    path = save_daily_report([_hostile_job()], output_dir=str(tmp_path))
    md = open(path).read()

    destinations = re.findall(r"\[(?:[^\]\\]|\\.)*\]\(([^)]*)\)", md)
    assert destinations, "expected at least one markdown link"
    for dest in destinations:
        assert not dest.lower().startswith(("javascript:", "data:", "vbscript:"))


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_scraped_text_cannot_forge_headings(tmp_path):
    """Newlines are collapsed, so '###' can never begin a line."""
    import re

    path = save_daily_report([_hostile_job()], output_dir=str(tmp_path))
    md = open(path).read()

    headings = [ln for ln in md.splitlines() if re.match(r"^#{1,6}\s", ln)]
    assert not [h for h in headings if "Forged" in h]


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
def test_legitimate_url_is_preserved(tmp_path):
    path = save_daily_report(
        [_hostile_job(title="Real Job", url="https://boards.greenhouse.io/x/jobs/1")],
        output_dir=str(tmp_path),
    )
    assert "https://boards.greenhouse.io/x/jobs/1" in open(path).read()
