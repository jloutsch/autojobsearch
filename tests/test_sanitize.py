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
