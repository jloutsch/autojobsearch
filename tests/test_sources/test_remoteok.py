"""Tests for sources/remoteok.py — RemoteOK JSON API source."""

import responses

from sources.remoteok import RemoteOKSource, API_URL
from tests.conftest import load_fixture


@responses.activate
def test_collect_skips_metadata():
    """First element (metadata) is skipped."""
    fixture = load_fixture("remoteok_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemoteOKSource()
    jobs = source.collect()

    # Only 1 of 2 actual jobs matches role keywords
    assert all(j.source == "remoteok" for j in jobs)
    # Metadata element should not appear as a job
    assert not any(hasattr(j, "legal") for j in jobs)


@responses.activate
def test_role_filter_applied():
    """Non-matching titles excluded."""
    fixture = load_fixture("remoteok_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemoteOKSource()
    jobs = source.collect()

    titles = [j.title for j in jobs]
    assert "Senior Software Developer" not in titles


@responses.activate
def test_salary_parsing():
    """salary_min/salary_max extracted correctly."""
    fixture = load_fixture("remoteok_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemoteOKSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.salary_min == 120000
    assert csm.salary_max == 150000


def test_salary_none_values():
    """None salary fields → (0, 0)."""
    source = RemoteOKSource()
    assert source._parse_salary({"salary_min": None, "salary_max": None}) == (0, 0)


@responses.activate
def test_date_parsing():
    """ISO date parsed correctly."""
    fixture = load_fixture("remoteok_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemoteOKSource()
    jobs = source.collect()

    csm = next(j for j in jobs if j.title == "Customer Success Manager")
    assert csm.posted_date.year == 2026


@responses.activate
def test_all_remote():
    """Every returned job has is_remote=True."""
    fixture = load_fixture("remoteok_response.json")
    responses.add(responses.GET, API_URL, json=fixture, status=200)

    source = RemoteOKSource()
    jobs = source.collect()

    assert all(j.is_remote is True for j in jobs)
