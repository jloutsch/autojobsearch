"""Tests for sources/ashby.py — Ashby ATS per-company job board API source."""

import responses

from sources.ashby import AshbySource, API_BASE
from tests.conftest import load_fixture

RAMP_URL = API_BASE.format(slug="ramp")


@responses.activate
def test_collect_fetches_all_boards(monkeypatch):
    """One GET per board in ASHBY_BOARDS."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp", "Linear": "linear"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)
    responses.add(
        responses.GET,
        API_BASE.format(slug="linear"),
        json={"jobs": []},
        status=200,
    )

    source = AshbySource()
    jobs = source.collect()

    assert len(responses.calls) == 2
    assert any(j.title == "Customer Success Manager" for j in jobs)


@responses.activate
def test_role_filter_applied(monkeypatch):
    """Non-matching titles excluded."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Senior Software Engineer" not in titles
    assert "Customer Success Manager" in titles


@responses.activate
def test_is_remote_true(monkeypatch):
    """isRemote=true → is_remote=True."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.is_remote is True


@responses.activate
def test_is_remote_null_fallback(monkeypatch):
    """isRemote=null → falls back to location string check."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    tam = next(j for j in jobs if "Account Management" in j.title)
    # "San Francisco, CA" doesn't contain "remote"
    assert tam.is_remote is False


@responses.activate
def test_is_remote_false(monkeypatch):
    """isRemote=false → is_remote=False."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    # Modify fixture to have a matching role with isRemote=false
    fixture = {
        "jobs": [
            {
                "title": "Customer Success Manager",
                "location": "New York, NY",
                "isRemote": False,
                "employmentType": "FullTime",
                "publishedAt": "2026-02-18T10:00:00Z",
                "jobUrl": "https://jobs.ashbyhq.com/ramp/csm-ny",
                "descriptionPlain": "In-office CSM role.",
            }
        ]
    }
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()
    assert jobs[0].is_remote is False


@responses.activate
def test_date_parsing(monkeypatch):
    """ISO date parsed correctly."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026
    assert csm.posted_date.month == 2


@responses.activate
def test_company_from_config(monkeypatch):
    """Company name comes from config key, not API."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    assert all(j.company == "Ramp" for j in jobs)


@responses.activate
def test_source_name(monkeypatch):
    """All jobs have source='ashby'."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()
    assert all(j.source == "ashby" for j in jobs)


@responses.activate
def test_description_from_plain_text(monkeypatch):
    """descriptionPlain used for description field."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    fixture = load_fixture("ashby_response.json")
    responses.add(responses.GET, RAMP_URL, json=fixture, status=200)

    source = AshbySource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert "enterprise accounts" in csm.description


@responses.activate
def test_404_returns_empty(monkeypatch):
    """Unknown slug (404) → safe_collect returns []."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"BadCo": "nonexistent"})

    responses.add(
        responses.GET,
        API_BASE.format(slug="nonexistent"),
        status=404,
    )

    source = AshbySource()
    jobs = source.safe_collect()
    assert jobs == []


@responses.activate
def test_empty_board(monkeypatch):
    """Board with no jobs → empty list."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {"Ramp": "ramp"})

    responses.add(responses.GET, RAMP_URL, json={"jobs": []}, status=200)

    source = AshbySource()
    jobs = source.collect()
    assert jobs == []


def test_no_boards_configured(monkeypatch):
    """Empty ASHBY_BOARDS → no requests, empty list."""
    import config
    monkeypatch.setattr(config, "ASHBY_BOARDS", {})

    source = AshbySource()
    jobs = source.collect()
    assert jobs == []


def test_date_parsing_invalid():
    """Invalid date → fallback to now."""
    source = AshbySource()
    result = source._parse_date("not-a-date")
    assert result.year >= 2026


def test_date_parsing_empty():
    """Empty date → fallback to now."""
    source = AshbySource()
    result = source._parse_date("")
    assert result.year >= 2026
