# Company links in the dashboard results table

**Date:** 2026-08-13
**Status:** Approved, ready for implementation

## Problem

In the dashboard results table the company column is plain text. Following up on
an employer means selecting the name, copying it, and searching manually.

## Decision

The company name becomes a link to a Google search for that name.

### Why not link to the company's own site

The obvious design — derive the employer's domain from the job URL's host, and
fall back to a search — was measured against the existing report archive before
being rejected:

| Source of job URL | Links | Share |
| --- | ---: | ---: |
| Aggregators (BuiltIn, Jobicy, WeWorkRemotely, RemoteOK, TheMuse) | 7,247 | 98.1% |
| Company-owned hosts | 143 | 1.9% |

Sample: 7,390 job links across 125 archived reports.

The 143 company-owned hosts are effectively two employers — `careers.datadoghq.com`
(113) and `sentinelone.com` (28). A derivation branch would therefore be dead code
for 98% of rows while adding an aggregator host blocklist that must be updated
whenever a source is added or an applicant tracking system changes domain. A stale
entry in that list fails quietly, sending the user to `boards.greenhouse.io`
instead of the employer.

No source supplies a company website URL directly: every `url`-shaped field in the
upstream APIs is either the job posting itself or a logo hosted on the aggregator's
own domain. There is no field to read, only a value to derive or search for.

## Behaviour

- The company cell renders as an anchor to `https://www.google.com/search?q=<company>`.
- The link opens in a new tab, matching the existing job-title link.
- A row whose company name is empty or whitespace renders as plain text, with no
  anchor. An empty link is worse than no link.
- Nothing else about the row changes.

## Components

### `sanitize.company_search_url(name) -> str`

Builds the search URL from an untrusted company name. Lives beside `safe_url()`
because it is the same concern — producing a safe URL from scraped text — and both
renderers need it.

- Percent-encodes the name into the query string.
- Returns `""` for an empty or whitespace-only name, which callers treat as the
  signal to render plain text.

### Two render paths

Both must change, or links disappear as soon as the user interacts with the table:

| Path | Location | Notes |
| --- | --- | --- |
| Server-rendered rows | `dashboard.py::_render_row` | Initial page load |
| Client-rendered rows | inline JS row builder in `dashboard.py` | Re-renders on sort and filter |

The JS side gets a small mirror of the helper, following the existing precedent
where `safeUrl()` mirrors `safe_url()`.

### Out of scope

`archive.py` is unchanged. The markdown report renders `### [title](url) — Company`,
which has no column and already carries a link to the posting.

## Safety

Company names come from scraped listings and are untrusted.

- **Encoding, not just escaping.** The name is percent-encoded into the query
  string. Encoding is what prevents a name containing `"`, `<`, or `&` from
  terminating the `href` attribute; HTML-escaping the finished URL alone would not
  be sufficient, because escaping happens after the attribute boundary is already
  broken.
- **Fixed origin.** The URL is always constructed against `https://www.google.com`,
  so the scheme can never be attacker-influenced.
- **One path for every href.** A non-empty result is still routed through the
  existing `safe_url()` before rendering, so every anchor in `dashboard.py` passes
  through a single control rather than two.

  Order matters here. `safe_url("")` returns `"#"`, so the caller must test for the
  empty string *before* calling it — otherwise a row with no company name renders a
  link to `#` instead of the plain text required above.

## Testing

- **Helper unit tests:** spaces, `&`, `"`, `<`, `#`, `+`, unicode, leading and
  trailing whitespace, empty string, whitespace-only string, `None`.
- **Server render:** `_render_row` emits an anchor wrapping the company name; a
  hostile name (`Evil" onmouseover="alert(1)`) cannot escape the attribute; an
  empty company yields no anchor.
- **Regression:** the existing job-title link and its `safe_url()` treatment are
  unaffected.

## Success criteria

1. Clicking any company name in the dashboard opens a Google search for it in a new
   tab.
2. A company name containing HTML metacharacters produces a working link and no
   injected markup.
3. Rows with no company name show plain text and no anchor.
4. Links survive sorting and filtering the table.
5. The full test suite passes.
