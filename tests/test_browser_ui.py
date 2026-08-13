"""Browser-level UI tests using Playwright.

Tests the dashboard's JavaScript interactions: filtering, sorting, profile
management, tag editing, stat card filtering, and search box functionality.
"""

import http.server
import json
import os
import threading
from http.server import HTTPServer

import pytest
from freezegun import freeze_time

from dashboard import generate_dashboard, generate_landing_page

pytestmark = pytest.mark.browser


def _sample_jobs():
    """Return a list of ranked job dicts for dashboard generation."""
    return [
        {
            "title": "Customer Success Manager",
            "company": "SentinelOne",
            "url": "https://example.com/1",
            "source": "greenhouse",
            "score": 85,
            "priority": "high",
            "salary_min": 140000,
            "salary_max": 160000,
            "location": "Remote - US",
            "posted_date": "2026-02-18T10:00:00+00:00",
            "description": "Cybersecurity CSM role.",
            "summary": "Excellent fit for cybersecurity background.",
            "key_matches": ["cybersecurity", "remote"],
            "gaps": [],
        },
        {
            "title": "Technical Account Manager",
            "company": "Datadog",
            "url": "https://example.com/2",
            "source": "greenhouse",
            "score": 65,
            "priority": "medium",
            "salary_min": 130000,
            "salary_max": 150000,
            "location": "Remote",
            "posted_date": "2026-02-17T10:00:00+00:00",
            "description": "Monitoring TAM role.",
            "summary": "Good match for technical skills.",
            "key_matches": ["monitoring"],
            "gaps": [],
        },
        {
            "title": "Account Manager",
            "company": "Acme Corp",
            "url": "https://example.com/3",
            "source": "remoteok",
            "score": 30,
            "priority": "low",
            "salary_min": 100000,
            "salary_max": 120000,
            "location": "Remote",
            "posted_date": "2026-02-10T10:00:00+00:00",
            "description": "Generic account management.",
            "summary": "Partial match.",
            "key_matches": [],
            "gaps": ["industry mismatch"],
        },
    ]


@pytest.fixture(scope="module")
def dashboard_html_dir(tmp_path_factory):
    """Generate dashboard HTML files and serve them."""
    reports_dir = str(tmp_path_factory.mktemp("reports"))
    with freeze_time("2026-02-19 12:00:00"):
        generate_dashboard(_sample_jobs(), output_dir=reports_dir)
        generate_landing_page(output_dir=reports_dir)

    # Also create an empty-results dashboard for testing
    with freeze_time("2026-02-18 12:00:00"):
        generate_dashboard([], output_dir=reports_dir, filename="empty.html")

    return reports_dir


@pytest.fixture(scope="module")
def server_url(dashboard_html_dir):
    """Serve dashboard HTML on a random port."""
    reports_dir = dashboard_html_dir

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=reports_dir, **kwargs)

        # Stub API endpoints the JS tries to hit on load
        def do_GET(self):
            if self.path == "/api/reports":
                data = b"[]"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", 0), QuietHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield f"http://localhost:{port}"
    server.shutdown()


# --- Page load and structure ---


def test_dashboard_loads_with_job_table(page, server_url):
    """Dashboard HTML loads and shows a table with job rows."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")
    rows = page.locator("#jobTable tbody tr")
    assert rows.count() == 3


def test_empty_dashboard_shows_no_results(page, server_url):
    """Empty job list shows 'No new matching jobs' message."""
    page.goto(f"{server_url}/empty.html")
    empty_msg = page.locator(".empty")
    assert empty_msg.is_visible()
    assert "No new matching jobs" in empty_msg.text_content()


def test_landing_page_has_run_search(page, server_url):
    """Landing page contains the Run Search button."""
    page.goto(f"{server_url}/index.html")
    btn = page.locator("#runSearchBtn")
    assert btn.is_visible()
    assert btn.text_content() == "Run Search"


# --- Stat cards ---


def test_stat_cards_show_correct_counts(page, server_url):
    """Stat cards display correct counts for each priority."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")
    assert page.locator("#statTotal").text_content() == "3"
    assert page.locator("#statHigh").text_content() == "1"
    assert page.locator("#statMed").text_content() == "1"
    assert page.locator("#statLow").text_content() == "1"


def test_stat_card_filters_by_priority(page, server_url):
    """Clicking a stat card filters the table to that priority."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Click "High Priority" stat card
    page.locator(".stat-high").click()
    page.wait_for_timeout(200)

    visible_rows = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible_rows.count() == 1
    assert "SentinelOne" in visible_rows.first.text_content()


def test_stat_card_all_shows_all_rows(page, server_url):
    """Clicking 'Total' stat card shows all rows again."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Filter to high first
    page.locator(".stat-high").click()
    page.wait_for_timeout(100)
    # Then click Total to reset
    page.locator(".stat-total").click()
    page.wait_for_timeout(200)

    visible_rows = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible_rows.count() == 3


# --- Priority filter buttons ---


def test_priority_filter_buttons(page, server_url):
    """Priority filter buttons toggle row visibility."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Click "Medium" filter
    page.locator('.filter-btn[data-priority="medium"]').click()
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1
    assert "Datadog" in visible.first.text_content()


def test_priority_filter_all_button(page, server_url):
    """'All' priority button restores all rows."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.locator('.filter-btn[data-priority="low"]').click()
    page.wait_for_timeout(100)
    page.locator('.filter-btn[data-priority="all"]').click()
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 3


# --- Search box filtering ---


def test_search_box_filters_by_title(page, server_url):
    """Typing in search box filters rows by title."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "Technical Account")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1
    assert "Datadog" in visible.first.text_content()


def test_search_box_filters_by_company(page, server_url):
    """Search box works with company names."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "SentinelOne")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1
    assert "Customer Success" in visible.first.text_content()


def test_search_box_filters_by_source(page, server_url):
    """Search box matches source badges."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "remoteok")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1
    assert "Acme" in visible.first.text_content()


def test_search_box_case_insensitive(page, server_url):
    """Search is case-insensitive."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "sentinelone")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1


def test_search_box_no_match(page, server_url):
    """Search with no match hides all rows."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "nonexistent-company-xyz")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 0


def test_search_box_clear_restores(page, server_url):
    """Clearing search box restores all rows."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "SentinelOne")
    page.wait_for_timeout(100)
    page.fill("#searchBox", "")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 3


# --- Column sorting ---


def test_sort_by_score(page, server_url):
    """Clicking Score header sorts by score."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Already sorted desc by default; click to toggle to asc
    page.locator("#jobTable th >> nth=0").click()
    page.wait_for_timeout(200)

    rows = page.locator("#jobTable tbody tr")
    first_score = rows.first.locator("td.score").text_content()
    last_score = rows.last.locator("td.score").text_content()
    # After clicking once (was desc), should toggle direction
    assert int(first_score) != int(last_score)


def test_sort_by_company(page, server_url):
    """Clicking Company header sorts alphabetically."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Click Company header (index 3)
    page.locator("#jobTable th >> nth=3").click()
    page.wait_for_timeout(200)

    rows = page.locator("#jobTable tbody tr")
    companies = [rows.nth(i).locator(".company").text_content() for i in range(3)]
    assert companies == sorted(companies) or companies == sorted(companies, reverse=True)


# --- Profile panel ---


def test_profile_panel_toggle(page, server_url):
    """Profile toggle button shows/hides profile panel."""
    page.goto(f"{server_url}/2026-02-19.html")
    panel = page.locator("#profilePanel")

    # Profile starts visible
    assert panel.is_visible()

    # Click toggle to hide
    page.locator("#profileToggle").click()
    page.wait_for_timeout(200)
    assert not panel.is_visible()

    # Click again to show
    page.locator("#profileToggle").click()
    page.wait_for_timeout(200)
    assert panel.is_visible()


def test_profile_loads_default_values(page, server_url):
    """Profile fields are populated with DEFAULT_PROFILE values."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    # Resume summary should be populated
    summary = page.locator("#resumeSummary").input_value()
    assert len(summary) > 0

    # Role tags container should have tag pills
    role_tags = page.locator("#roleTags .tag-pill")
    assert role_tags.count() > 0


def test_add_tag_via_keyboard(page, server_url):
    """Typing in tag input and pressing Enter adds a tag pill."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    initial_count = page.locator("#roleTags .tag-pill").count()

    # Type a new tag and press Enter
    tag_input = page.locator("#roleTags .tag-add")
    tag_input.fill("new-test-tag")
    tag_input.press("Enter")
    page.wait_for_timeout(200)

    new_count = page.locator("#roleTags .tag-pill").count()
    assert new_count == initial_count + 1

    # Verify the tag text is there
    all_text = page.locator("#roleTags").text_content()
    assert "new-test-tag" in all_text


def test_remove_tag(page, server_url):
    """Clicking the X on a tag pill removes it."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    initial_count = page.locator("#roleTags .tag-pill").count()
    assert initial_count > 0

    # Click the remove button on the first tag
    page.locator("#roleTags .tag-pill .remove").first.click()
    page.wait_for_timeout(200)

    new_count = page.locator("#roleTags .tag-pill").count()
    assert new_count == initial_count - 1


def test_clear_all_tags(page, server_url):
    """'clear all' link removes all tags from a section."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    assert page.locator("#roleTags .tag-pill").count() > 0

    # Click "clear all" for role tags
    page.locator("text=Role Tags").locator("..").locator(".clear-tags").click()
    page.wait_for_timeout(200)

    assert page.locator("#roleTags .tag-pill").count() == 0


def test_save_profile_shows_toast(page, server_url):
    """Save Profile button shows a toast notification."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    page.locator("text=Save to Browser").click()
    page.wait_for_timeout(300)

    toast = page.locator("#toast")
    assert "Profile saved" in toast.text_content()


def test_reset_profile_restores_defaults(page, server_url):
    """Reset Profile restores DEFAULT_PROFILE values."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    # Clear storage to ensure clean state
    page.evaluate("localStorage.clear()")

    # Modify a field
    page.fill("#resumeSummary", "modified text")
    page.wait_for_timeout(100)

    # Click reset
    page.locator("text=Reset to Default").click()
    page.wait_for_timeout(300)

    # Should be restored to default (not "modified text")
    summary = page.locator("#resumeSummary").input_value()
    assert summary != "modified text"
    assert len(summary) > 0


def test_salary_inputs_populated(page, server_url):
    """Salary range inputs are populated from profile."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    # Clear localStorage so defaults load
    page.evaluate("localStorage.clear()")
    page.reload()
    page.wait_for_selector("#profilePanel")

    salary_min = page.locator("#salaryMin").input_value()
    # Should have a value from the default profile
    assert salary_min != ""


# --- Table data rendering ---


def test_job_title_links(page, server_url):
    """Job titles are clickable links with correct URLs."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    links = page.locator(".job-title")
    assert links.count() == 3

    first_href = links.first.get_attribute("href")
    assert first_href.startswith("https://example.com/")


def test_priority_styling(page, server_url):
    """Rows have correct priority CSS classes."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    high_cells = page.locator(".priority-high")
    assert high_cells.count() >= 1

    medium_cells = page.locator(".priority-medium")
    assert medium_cells.count() >= 1

    low_cells = page.locator(".priority-low")
    assert low_cells.count() >= 1


def test_salary_display(page, server_url):
    """Salary cells show formatted dollar ranges."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    salary_cells = page.locator("td.salary")
    all_text = " ".join(salary_cells.nth(i).text_content() for i in range(salary_cells.count()))
    assert "$140,000" in all_text
    assert "$160,000" in all_text


def test_source_badges(page, server_url):
    """Source badges render correctly."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    badges = page.locator(".source-badge")
    sources = [badges.nth(i).text_content() for i in range(badges.count())]
    assert "greenhouse" in sources
    assert "remoteok" in sources


def test_summary_text(page, server_url):
    """Summary column shows AI summary text."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    summaries = page.locator("td.summary")
    first_summary = summaries.first.text_content()
    assert "cybersecurity" in first_summary.lower() or "fit" in first_summary.lower()


# --- History dropdown ---


def test_history_dropdown_toggles(page, server_url):
    """Past Results button toggles the history dropdown."""
    page.goto(f"{server_url}/2026-02-19.html")

    dropdown = page.locator("#historyDropdown")
    assert not dropdown.is_visible()

    page.locator("#historyBtn").click()
    page.wait_for_timeout(200)
    assert dropdown.is_visible()

    page.locator("#historyBtn").click()
    page.wait_for_timeout(200)
    assert not dropdown.is_visible()


# --- Filter count display ---


def test_filter_count_updates(page, server_url):
    """Filter count text updates when rows are filtered."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    page.fill("#searchBox", "SentinelOne")
    page.wait_for_timeout(300)

    count_text = page.locator("#filterCount").text_content()
    assert "1" in count_text


# --- Combined filters ---


def test_combined_search_and_priority_filter(page, server_url):
    """Search box and priority filter work together."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#jobTable")

    # Set priority to high
    page.locator('.filter-btn[data-priority="high"]').click()
    page.wait_for_timeout(100)

    # Also search for "Customer"
    page.fill("#searchBox", "Customer")
    page.wait_for_timeout(200)

    visible = page.locator("#jobTable tbody tr:not(.hidden)")
    assert visible.count() == 1
    assert "SentinelOne" in visible.first.text_content()


# --- localStorage persistence ---


def test_profile_persists_across_reload(page, server_url):
    """Profile changes saved to localStorage persist across page reload."""
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("#profilePanel")

    # Clear any existing stored profile
    page.evaluate("localStorage.clear()")
    page.reload()
    page.wait_for_selector("#profilePanel")

    # Modify and save
    page.fill("#resumeSummary", "Persistent test summary")
    page.locator("text=Save to Browser").click()
    page.wait_for_timeout(300)

    # Reload and check
    page.reload()
    page.wait_for_selector("#profilePanel")

    summary = page.locator("#resumeSummary").input_value()
    assert summary == "Persistent test summary"

    # Cleanup
    page.evaluate("localStorage.clear()")


def test_rendered_page_has_company_links(page, server_url):
    """Confirms a real browser renders the server-generated company links with
    the expected href shape, and that sorting does not disturb them.

    This is NOT the regression guard for the client-side buildJobRow path --
    test_build_job_row_renders_company_link is, because sortTable() only
    reorders existing DOM nodes via appendChild and never rebuilds a cell, so
    the before/after count here can't actually detect a broken row builder.
    """
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("table tbody tr")

    before = page.locator("td.company a.company-link").count()
    assert before > 0, "no company links on initial load"

    page.click("th:has-text('Company')")
    page.wait_for_timeout(300)

    after = page.locator("td.company a.company-link").count()
    assert after == before, "company links disappeared after sorting"

    href = page.locator("td.company a.company-link").first.get_attribute("href")
    assert href.startswith("https://www.google.com/search?q=")


def test_build_job_row_renders_company_link(page, server_url):
    """buildJobRow() is the client-side row builder used after a Run Search
    (loadResults() rebuilds every row via buildJobRow, unlike sortTable()/
    filterTable() which only reorder or hide existing rows). This calls it
    directly to confirm the company cell it produces still links out.
    """
    page.goto(f"{server_url}/2026-02-19.html")
    page.wait_for_selector("table tbody tr")

    cell_html = page.evaluate(
        """() => buildJobRow({
            company: 'Acme Corp', title: 'Role', url: 'https://example.com/x',
            source: 'greenhouse', score: 50, priority: 'medium',
            salary_min: 0, salary_max: 0, location: 'Remote',
            posted_date: '', summary: ''
        }).querySelector('td.company').innerHTML"""
    )
    assert 'class="company-link"' in cell_html
    assert "https://www.google.com/search?q=Acme" in cell_html

    empty_html = page.evaluate(
        """() => buildJobRow({
            company: '  ', title: 'Role', url: 'https://example.com/x',
            source: 'greenhouse', score: 50, priority: 'medium',
            salary_min: 0, salary_max: 0, location: 'Remote',
            posted_date: '', summary: ''
        }).querySelector('td.company').innerHTML"""
    )
    assert "<a" not in empty_html
