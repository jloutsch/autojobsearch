# Company Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the company name in the dashboard results table a link to a Google search for that company.

**Architecture:** One helper in `sanitize.py` builds the search URL from an untrusted company name by percent-encoding it into a fixed `https://www.google.com` origin. Both dashboard render paths — the server-rendered rows in `_render_row` and the client-rendered rows in the inline JS row builder — call it, mirroring the existing `safe_url()` / `safeUrl()` pair.

**Tech Stack:** Python 3.13, `urllib.parse.quote_plus`, `html.escape`, pytest, pytest-playwright for the browser rendering path.

**Spec:** `docs/superpowers/specs/2026-08-13-company-links-design.md`

## Global Constraints

- Company names are untrusted scraped text. Percent-encode before building the URL; HTML-escape after. Encoding is what prevents attribute escape, not escaping.
- The URL origin is always `https://www.google.com` — never derived from job data.
- An empty or whitespace-only company renders as plain text with no anchor.
- Test for the empty string *before* calling `safe_url()`; `safe_url("")` returns `"#"`, which would render a link to `#`.
- `archive.py` is out of scope and must not change.
- Run tests with the venv: `source .venv/bin/activate` first, or use `.venv/bin/python -m pytest`.
- Use `-p no:randomly` when running a single test by name, so ordering does not shuffle.

## File Structure

| File | Responsibility | Change |
| --- | --- | --- |
| `sanitize.py` | Shared safe-URL construction from untrusted text | Add `company_search_url()` |
| `tests/test_sanitize.py` | Unit tests for the helper | Create |
| `dashboard.py` | Both render paths + link styling | Modify 3 regions |
| `tests/test_dashboard.py` | Server-render assertions | Extend |

---

### Task 1: `company_search_url` helper

**Files:**
- Modify: `sanitize.py` (append after `safe_url`)
- Test: `tests/test_sanitize.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `company_search_url(name: str) -> str` — returns `"https://www.google.com/search?q=<percent-encoded name>"`, or `""` when the name is empty or whitespace-only. Task 2 and Task 3 both depend on the empty-string contract.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sanitize.py`:

```python
"""Tests for sanitize.py — shared cleaning of third-party text."""

import pytest

from sanitize import company_search_url, safe_url


@pytest.mark.parametrize("name,expected_query", [
    ("Datadog", "Datadog"),
    ("Samsara Inc.", "Samsara+Inc."),
    ("Ben & Jerry's", "Ben+%26+Jerry%27s"),
    ("  Stripe  ", "Stripe"),
    ("A+B Systems", "A%2BB+Systems"),
    ("Nestlé", "Nestl%C3%A9"),
    ("C#Corp", "C%23Corp"),
])
def test_builds_a_google_search_url(name, expected_query):
    assert company_search_url(name) == f"https://www.google.com/search?q={expected_query}"


@pytest.mark.parametrize("empty", ["", "   ", "\t\n", None])
def test_empty_company_yields_empty_string(empty):
    """Callers use '' as the signal to render plain text instead of a link."""
    assert company_search_url(empty) == ""


def test_html_metacharacters_are_encoded_not_passed_through():
    """A name cannot terminate the href attribute it is placed into."""
    url = company_search_url('Evil" onmouseover="alert(1)')
    assert '"' not in url
    assert "<" not in url
    assert url.startswith("https://www.google.com/search?q=")


def test_origin_is_fixed():
    """The scheme and host are never influenced by the company name."""
    assert company_search_url("https://evil.example/#").startswith(
        "https://www.google.com/search?q="
    )


def test_result_survives_safe_url_unchanged():
    """The helper's output is already an http(s) URL, so safe_url is a no-op on it."""
    url = company_search_url("Datadog")
    assert safe_url(url) == url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sanitize.py -q -p no:randomly`
Expected: FAIL — `ImportError: cannot import name 'company_search_url' from 'sanitize'`

- [ ] **Step 3: Implement the helper**

Append to `sanitize.py`:

```python
def company_search_url(name: str) -> str:
    """Build a web-search URL for a company name.

    No job source supplies an employer's website, so the company name is the only
    thing available to link on. The name is percent-encoded into a fixed origin:
    encoding is what stops a name containing a quote from terminating the href it
    is placed into, which HTML-escaping alone cannot do once the attribute
    boundary is already broken.

    Returns "" for an empty name so callers can render plain text — do not pass
    that through safe_url(), which turns "" into "#".
    """
    cleaned = str(name or "").strip()
    if not cleaned:
        return ""
    return "https://www.google.com/search?q=" + quote_plus(cleaned)
```

Add to the imports at the top of `sanitize.py`:

```python
from urllib.parse import quote_plus
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sanitize.py -q -p no:randomly`
Expected: PASS — 14 passed

- [ ] **Step 5: Commit**

```bash
git add sanitize.py tests/test_sanitize.py
git commit -m "Add company_search_url helper for untrusted company names"
```

---

### Task 2: Server-rendered company link

**Files:**
- Modify: `dashboard.py` — import, `.company-link` CSS near line 224, `_render_row` near line 1400
- Test: `tests/test_dashboard.py` (extend)

**Interfaces:**
- Consumes: `company_search_url(name) -> str` from Task 1
- Produces: server-rendered `<td class="company">` containing an `<a class="company-link">` when the company is non-empty

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard.py`:

```python
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
    row = _row(company='Evil" onmouseover="alert(1)')
    assert "onmouseover=" not in row
    assert 'class="company-link"' in row


def test_job_title_link_is_unaffected():
    """Regression: the title anchor keeps its own safe_url treatment."""
    row = _row(url="https://example.com/1")
    assert '<a href="https://example.com/1"' in row
    assert 'class="job-title"' in row

    blocked = _row(url="javascript:alert(1)")
    assert "javascript:" not in blocked
    assert 'href="#"' in blocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -q -p no:randomly -k company`
Expected: FAIL — `assert 'class="company-link"' in row` fails; the cell is still plain text

- [ ] **Step 3: Add the import**

In `dashboard.py`, change:

```python
from sanitize import safe_url
```

to:

```python
from sanitize import company_search_url, safe_url
```

- [ ] **Step 4: Add the CSS**

In `dashboard.py`, immediately after the `.company` rule near line 224:

```
  .company {{ color: #e2e8f0; font-weight: 500; }}
  .company-link {{ color: inherit; text-decoration: none; }}
  .company-link:hover {{ text-decoration: underline; }}
```

`color: inherit` keeps the existing company colour, so the only visual change is the hover underline. The doubled braces are required — this block is inside an f-string.

- [ ] **Step 5: Build the cell in `_render_row`**

In `dashboard.py::_render_row`, after the existing `company = html.escape(...)` line, add:

```python
    company_url = company_search_url(job.get("company", ""))
    if company_url:
        company_cell = (
            f'<a href="{html.escape(safe_url(company_url))}" target="_blank" '
            f'rel="noopener noreferrer" class="company-link">{company}</a>'
        )
    else:
        company_cell = company
```

Then change the company cell in the returned f-string from:

```
    <td class="company">{company}</td>
```

to:

```
    <td class="company">{company_cell}</td>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -q -p no:randomly`
Expected: PASS — all dashboard tests including the 4 new ones

- [ ] **Step 7: Commit**

```bash
git add dashboard.py tests/test_dashboard.py
git commit -m "Link company names to a search in server-rendered rows"
```

---

### Task 3: Client-rendered company link

**Files:**
- Modify: `dashboard.py` — JS helper after `safeUrl` near line 420, row builder near line 880
- Test: `tests/test_browser_ui.py` (extend)

**Interfaces:**
- Consumes: the `.company-link` CSS from Task 2
- Produces: client-rendered rows whose company cell matches the server-rendered markup

The table re-renders client-side on sort and filter. Without this task the links appear on load and vanish on first interaction.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_browser_ui.py`:

```python
def test_company_links_survive_sorting(page, server_url):
    """The table re-renders client-side, so the link must exist after interaction."""
    page.goto(server_url)
    page.wait_for_selector("table tbody tr")

    before = page.locator("td.company a.company-link").count()
    assert before > 0, "no company links on initial load"

    page.click("th:has-text('Company')")
    page.wait_for_timeout(300)

    after = page.locator("td.company a.company-link").count()
    assert after == before, "company links disappeared after sorting"

    href = page.locator("td.company a.company-link").first.get_attribute("href")
    assert href.startswith("https://www.google.com/search?q=")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_browser_ui.py -q -p no:randomly -k company_links`
Expected: FAIL — `assert after == before`, because the JS row builder still emits plain text

- [ ] **Step 3: Add the JS mirror**

In `dashboard.py`, immediately after the `safeUrl` function near line 420:

```javascript
// Mirrors sanitize.company_search_url. No source supplies an employer website,
// so the name is encoded into a fixed origin; '' means render plain text.
function companySearchUrl(name) {{
  const trimmed = String(name || '').trim();
  return trimmed ? 'https://www.google.com/search?q=' + encodeURIComponent(trimmed) : '';
}}
```

`encodeURIComponent` encodes a space as `%20` where Python's `quote_plus` uses `+`. Both are valid in a query string and Google treats them identically, so the two paths need not produce byte-identical URLs — do not write a test asserting they match.

- [ ] **Step 4: Use it in the row builder**

In `dashboard.py`, immediately before `tr.innerHTML = ` near line 876:

```javascript
  const companyUrl = companySearchUrl(job.company);
  const companyCell = companyUrl
    ? `<a href="${{escapeHtml(safeUrl(companyUrl))}}" target="_blank" rel="noopener noreferrer" class="company-link">${{escapeHtml(job.company)}}</a>`
    : escapeHtml(job.company);
```

Then change the company cell in the `tr.innerHTML` template from:

```
    <td class="company">${{escapeHtml(job.company)}}</td>
```

to:

```
    <td class="company">${{companyCell}}</td>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_browser_ui.py -q -p no:randomly -k company_links`
Expected: PASS

- [ ] **Step 6: Run the full suite for regressions**

Run: `.venv/bin/python -m pytest tests/ -q -p no:randomly`
Expected: PASS — 561 existing tests plus the new ones.

Pay attention to `test_sort_by_company` and `test_search_box_filters_by_company`. Both read the company cell; `textContent` still returns the name through the anchor, but if either asserts on inner HTML it needs updating to match the new markup.

- [ ] **Step 7: Verify by eye**

```bash
.venv/bin/python main.py serve 8080
```

Open `http://localhost:8080/`, confirm company names underline on hover and open a Google search in a new tab, then sort by Company and confirm the links still work.

- [ ] **Step 8: Commit**

```bash
git add dashboard.py tests/test_browser_ui.py
git commit -m "Link company names to a search in client-rendered rows"
```

---

## Out of scope

- `archive.py` — the markdown report has no company column and already links the posting.
- The server-rendered job-title anchor lacks the `rel="noopener noreferrer"` that its client-rendered counterpart has. Pre-existing and unrelated; leave it.
