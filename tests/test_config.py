"""Tests for config.py — configuration loading from profile."""

import config


def test_reload_updates_globals(monkeypatch):
    """After changing profile + reload(), config globals reflect new values."""
    import user_profile

    new_profile = {
        "role_tags": ["new tag"],
        "priority_companies": ["NewCo"],
        "industry_tags": ["fintech"],
        "salary_range": {"min": 200000, "max": 250000, "floor": 180000},
        "greenhouse_boards": {"NewCo": "newco-board"},
        "max_job_age_days": 14,
    }
    monkeypatch.setattr(user_profile, "_profile", new_profile)
    config.reload()

    assert config.SEARCH_QUERIES == ["new tag"]
    assert config.PRIORITY_COMPANIES == ["NewCo"]
    assert config.SALARY_MIN == 200000
    assert config.SALARY_FLOOR == 180000
    assert config.MAX_JOB_AGE_DAYS == 14


def test_role_keywords_lowercased():
    """ROLE_KEYWORDS are lowercase versions of role_tags."""
    for kw in config.ROLE_KEYWORDS:
        assert kw == kw.lower()


def test_salary_floor_default(monkeypatch):
    """Missing 'floor' key defaults to 100000."""
    import user_profile

    profile_no_floor = {
        "role_tags": ["test"],
        "priority_companies": [],
        "industry_tags": [],
        "salary_range": {"min": 100000, "max": 0},
        "greenhouse_boards": {},
    }
    monkeypatch.setattr(user_profile, "_profile", profile_no_floor)
    config.reload()
    assert config.SALARY_FLOOR == 100000


def test_greenhouse_boards_loaded():
    """GREENHOUSE_BOARDS matches profile dict."""
    assert config.GREENHOUSE_BOARDS == {"SentinelOne": "sentinellabs", "Datadog": "datadog"}


def test_max_job_age_days_default(monkeypatch):
    """Missing key defaults to 30."""
    import user_profile

    profile_no_age = {
        "role_tags": ["test"],
        "priority_companies": [],
        "industry_tags": [],
        "salary_range": {"min": 100000, "max": 0, "floor": 100000},
        "greenhouse_boards": {},
    }
    monkeypatch.setattr(user_profile, "_profile", profile_no_age)
    config.reload()
    assert config.MAX_JOB_AGE_DAYS == 30
