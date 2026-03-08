"""Contract/snapshot tests for HTML dashboard and markdown report output.

Verifies structural contracts — elements, attributes, and content patterns that
downstream consumers (browser JS, CSS selectors) depend on. These tests catch
regressions in the HTML/markdown output format without pixel-level comparison.
"""

import json
import re

import pytest
from freezegun import freeze_time

from archive import save_daily_report
from dashboard import _render_row, generate_dashboard, generate_landing_page


def _make_job(**overrides):
    """Create a job dict with sensible defaults."""
    defaults = {
        "title": "Customer Success Manager",
        "company": "TestCorp",
        "url": "https://example.com/job/1",
        "source": "greenhouse",
        "score": 72,
        "priority": "high",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote - US",
        "posted_date": "2026-02-18T10:00:00+00:00",
        "description": "A cybersecurity SaaS role.",
        "summary": "Good fit for technical background.",
        "key_matches": ["cybersecurity"],
        "gaps": [],
    }
    defaults.update(overrides)
    return defaults


_THREE_JOBS = [
    _make_job(),
    _make_job(
        title="TAM", company="Datadog", url="https://example.com/2",
        score=45, priority="medium", salary_min=120000, salary_max=140000,
    ),
    _make_job(
        title="AM", company="Acme", url="https://example.com/3",
        score=20, priority="low", salary_min=0, salary_max=0,
    ),
]


# ============================================================
# HTML Dashboard Contract Tests
# ============================================================


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
class TestDashboardHtmlStructure:
    """Verify the structural contract of the generated HTML dashboard."""

    @pytest.fixture
    def dashboard_html(self, tmp_path):
        path = generate_dashboard(_THREE_JOBS, output_dir=str(tmp_path))
        with open(path) as f:
            return f.read()

    def test_has_doctype(self, dashboard_html):
        assert dashboard_html.startswith("<!DOCTYPE html>")

    def test_has_charset_meta(self, dashboard_html):
        assert '<meta charset="UTF-8">' in dashboard_html

    def test_has_viewport_meta(self, dashboard_html):
        assert "viewport" in dashboard_html

    def test_has_job_table(self, dashboard_html):
        assert 'id="jobTable"' in dashboard_html

    def test_table_has_expected_headers(self, dashboard_html):
        for header in ["Score", "Priority", "Title", "Company", "Salary",
                        "Location", "Posted", "Source", "Summary"]:
            assert f">{header} " in dashboard_html or f">{header}<" in dashboard_html

    def test_has_stat_cards(self, dashboard_html):
        assert 'id="statTotal"' in dashboard_html
        assert 'id="statHigh"' in dashboard_html
        assert 'id="statMed"' in dashboard_html
        assert 'id="statLow"' in dashboard_html

    def test_stat_card_counts_match(self, dashboard_html):
        assert 'id="statHigh">1<' in dashboard_html
        assert 'id="statMed">1<' in dashboard_html
        assert 'id="statLow">1<' in dashboard_html

    def test_has_search_box(self, dashboard_html):
        assert 'id="searchBox"' in dashboard_html

    def test_has_priority_filter_buttons(self, dashboard_html):
        assert 'data-priority="all"' in dashboard_html
        assert 'data-priority="high"' in dashboard_html
        assert 'data-priority="medium"' in dashboard_html
        assert 'data-priority="low"' in dashboard_html

    def test_has_age_filter_buttons(self, dashboard_html):
        assert 'data-age="all"' in dashboard_html
        assert 'data-age="1"' in dashboard_html
        assert 'data-age="7"' in dashboard_html

    def test_has_profile_panel(self, dashboard_html):
        assert 'id="profilePanel"' in dashboard_html
        assert 'id="profileToggle"' in dashboard_html

    def test_has_profile_fields(self, dashboard_html):
        assert 'id="resumeSummary"' in dashboard_html
        assert 'id="roleTags"' in dashboard_html
        assert 'id="industryTags"' in dashboard_html
        assert 'id="skillTags"' in dashboard_html
        assert 'id="companyTags"' in dashboard_html
        assert 'id="salaryMin"' in dashboard_html
        assert 'id="salaryMax"' in dashboard_html
        assert 'id="salaryFloor"' in dashboard_html

    def test_has_resume_upload(self, dashboard_html):
        assert 'id="resumeFileInput"' in dashboard_html
        assert 'id="uploadResumeBtn"' in dashboard_html

    def test_has_history_dropdown(self, dashboard_html):
        assert 'id="historyDropdown"' in dashboard_html
        assert 'id="historyBtn"' in dashboard_html

    def test_has_ollama_panel(self, dashboard_html):
        assert 'id="modelSelect"' in dashboard_html
        assert 'id="rescoreBtn"' in dashboard_html

    def test_has_run_search_button(self, dashboard_html):
        assert 'id="runSearchBtn"' in dashboard_html

    def test_has_toast_element(self, dashboard_html):
        assert 'id="toast"' in dashboard_html

    def test_embedded_json_valid(self, dashboard_html):
        """Job data and profile data are valid embedded JSON."""
        match = re.search(r"const jobData = (.+?);$", dashboard_html, re.MULTILINE)
        assert match, "jobData not found in script"
        job_json = match.group(1).replace("\\/", "/")
        jobs = json.loads(job_json)
        assert len(jobs) == 3
        assert all("title" in j for j in jobs)

        match = re.search(r"const DEFAULT_PROFILE = (.+?);$", dashboard_html, re.MULTILINE)
        assert match, "DEFAULT_PROFILE not found in script"
        profile_json = match.group(1).replace("\\/", "/")
        profile = json.loads(profile_json)
        assert "role_tags" in profile

    def test_js_functions_present(self, dashboard_html):
        """Key JavaScript functions exist in the script block."""
        for fn in ["filterTable", "sortTable", "setPriority", "setAge",
                    "toggleProfile", "saveProfile", "resetProfile",
                    "downloadProfile", "rescoreAll", "runSearch",
                    "toggleHistory", "loadHistory", "renderProfile",
                    "addTag", "removeTag", "clearTags", "autoSaveProfile",
                    "handleResumeUpload", "analyzeResumeText"]:
            assert f"function {fn}" in dashboard_html or f"{fn} =" in dashboard_html, \
                f"JS function {fn}() missing from dashboard"


class TestRenderRowContract:
    """Verify the HTML contract of individual table rows."""

    def test_row_has_data_priority_attribute(self):
        html = _render_row(_make_job(priority="high"))
        assert 'data-priority="high"' in html

    def test_row_has_data_posted_attribute(self):
        html = _render_row(_make_job(posted_date="2026-02-18T10:00:00+00:00"))
        assert 'data-posted="2026-02-18T10:00:00+00:00"' in html

    def test_row_has_score_data_sort(self):
        html = _render_row(_make_job(score=72))
        assert 'data-sort="72"' in html

    def test_row_has_priority_class(self):
        html = _render_row(_make_job(priority="medium"))
        assert 'class="priority-medium"' in html

    def test_row_has_job_title_link(self):
        html = _render_row(_make_job(url="https://example.com/job/1"))
        assert 'class="job-title"' in html
        assert 'href="https://example.com/job/1"' in html
        assert 'target="_blank"' in html

    def test_row_has_company_class(self):
        html = _render_row(_make_job(company="TestCorp"))
        assert 'class="company"' in html
        assert "TestCorp" in html

    def test_row_has_salary_class(self):
        html = _render_row(_make_job(salary_min=130000, salary_max=150000))
        assert 'class="salary"' in html
        assert "$130,000" in html

    def test_row_has_source_badge(self):
        html = _render_row(_make_job(source="greenhouse"))
        assert 'class="source-badge"' in html
        assert "greenhouse" in html

    def test_row_has_summary_class(self):
        html = _render_row(_make_job(summary="Good fit."))
        assert 'class="summary"' in html
        assert "Good fit." in html

    def test_row_has_age_class(self):
        html = _render_row(_make_job())
        assert 'class="age"' in html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
class TestLandingPageContract:
    """Verify the structural contract of the landing page."""

    @pytest.fixture
    def landing_html(self, tmp_path):
        path = generate_landing_page(output_dir=str(tmp_path))
        with open(path) as f:
            return f.read()

    def test_has_run_search_button(self, landing_html):
        assert "Run Search" in landing_html
        assert 'id="runSearchBtn"' in landing_html

    def test_has_profile_panel(self, landing_html):
        assert 'id="profilePanel"' in landing_html

    def test_has_empty_message_or_table(self, landing_html):
        assert "No new matching jobs" in landing_html or "Run Search" in landing_html


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
class TestEmptyDashboardContract:
    """Verify empty dashboard has correct structure."""

    @pytest.fixture
    def empty_html(self, tmp_path):
        path = generate_dashboard([], output_dir=str(tmp_path))
        with open(path) as f:
            return f.read()

    def test_no_data_rows_when_empty(self, empty_html):
        """Empty dashboard has no data rows (table may exist in JS template)."""
        assert '<tr data-priority=' not in empty_html

    def test_has_empty_message(self, empty_html):
        assert "No new matching jobs" in empty_html

    def test_stat_counts_zero(self, empty_html):
        assert 'id="statTotal">0<' in empty_html
        assert 'id="statHigh">0<' in empty_html


# ============================================================
# Markdown Report Contract Tests
# ============================================================


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
class TestMarkdownReportContract:
    """Verify the structural contract of markdown archive reports."""

    @pytest.fixture
    def report_md(self, tmp_path):
        jobs = [
            _make_job(priority="high"),
            _make_job(
                title="TAM", company="Datadog", url="https://example.com/2",
                score=45, priority="medium",
            ),
            _make_job(
                title="AM", company="Acme", url="https://example.com/3",
                score=20, priority="low",
            ),
        ]
        path = save_daily_report(jobs, output_dir=str(tmp_path))
        with open(path) as f:
            return f.read()

    def test_has_date_header(self, report_md):
        assert "# Job Search Report" in report_md
        assert "2026-02-19" in report_md

    def test_has_summary_line(self, report_md):
        assert "3 new matches" in report_md
        assert "1 high" in report_md
        assert "1 medium" in report_md
        assert "1 low" in report_md

    def test_has_priority_sections(self, report_md):
        assert "## High Priority" in report_md
        assert "## Worth a Look" in report_md
        assert "## Other Matches" in report_md

    def test_job_entries_have_title_link(self, report_md):
        assert "[Customer Success Manager](https://example.com/job/1)" in report_md

    def test_job_entries_have_company(self, report_md):
        assert "TestCorp" in report_md

    def test_job_entries_have_score(self, report_md):
        assert "**Score:**" in report_md

    def test_job_entries_have_source(self, report_md):
        assert "**Source:**" in report_md

    def test_job_entries_have_salary(self, report_md):
        assert "$130,000" in report_md

    def test_job_entries_have_location(self, report_md):
        assert "**Location:** Remote - US" in report_md

    def test_job_entries_have_summary(self, report_md):
        assert "Good fit for technical background." in report_md


@freeze_time("2026-02-19 12:00:00", tz_offset=0)
class TestEmptyMarkdownReport:
    """Verify empty report has correct structure."""

    @pytest.fixture
    def empty_md(self, tmp_path):
        path = save_daily_report([], output_dir=str(tmp_path))
        with open(path) as f:
            return f.read()

    def test_has_date_header(self, empty_md):
        assert "# Job Search Report" in empty_md
        assert "2026-02-19" in empty_md

    def test_has_no_jobs_message(self, empty_md):
        assert "No new matching jobs found today." in empty_md

    def test_no_priority_sections(self, empty_md):
        assert "## High Priority" not in empty_md
        assert "## Worth a Look" not in empty_md


# ============================================================
# Regression snapshot: full HTML output stability
# ============================================================


class TestDashboardSnapshot:
    """Snapshot test ensuring structural stability of dashboard output."""

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_single_job_dashboard_structure(self, tmp_path):
        """Single-job dashboard has all required structural elements."""
        jobs = [_make_job()]
        path = generate_dashboard(jobs, output_dir=str(tmp_path))
        with open(path) as f:
            html = f.read()

        # Document structure — count only the static table, not JS template strings
        assert 'id="jobTable"' in html
        assert html.count("<thead") >= 1
        assert html.count("<tbody") >= 1
        assert html.count("<tr data-priority=") == 1

        # Required CSS classes
        for cls in ["stat-card", "filter-btn", "age-btn", "search",
                     "profile-panel", "profile-toggle", "tag-container",
                     "salary-input", "toast", "progress-panel"]:
            assert cls in html, f"CSS class '{cls}' missing from dashboard"

        # Required data attributes
        assert "data-sort=" in html
        assert "data-priority=" in html
        assert "data-posted=" in html
        assert "data-age=" in html

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_row_count_matches_job_count(self, tmp_path):
        """Number of table rows matches number of input jobs."""
        jobs = [_make_job(url=f"https://example.com/{i}") for i in range(5)]
        path = generate_dashboard(jobs, output_dir=str(tmp_path))
        with open(path) as f:
            html = f.read()

        row_count = html.count("<tr data-priority=")
        assert row_count == 5
