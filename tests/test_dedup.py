"""Tests for dedup.py — deduplication logic."""

import sqlite3
from datetime import datetime, timezone

from dedup import _stable_hash, init_db, is_duplicate, mark_as_sent, was_previously_sent


# --- is_duplicate (fuzzy matching) ---


def test_exact_duplicate_detected(make_job):
    """Same title+company in seen list returns True."""
    job = make_job(title="Customer Success Manager", company="TestCorp")
    seen = [make_job(title="Customer Success Manager", company="TestCorp")]
    assert is_duplicate(job, seen) is True


def test_fuzzy_duplicate_detected(make_job):
    """Similar titles/companies are detected as duplicates."""
    job = make_job(title="Customer Success Manager (Remote)", company="TestCorp")
    seen = [make_job(title="Customer Success Manager", company="TestCorp")]
    assert is_duplicate(job, seen) is True


def test_different_jobs_not_duplicate(make_job):
    """Unrelated titles return False."""
    job = make_job(title="Customer Success Manager", company="AlphaCorp")
    seen = [make_job(title="Senior Software Engineer", company="BetaCorp")]
    assert is_duplicate(job, seen) is False


def test_same_title_different_company_not_duplicate(make_job):
    """Same title at completely different company is not a duplicate."""
    job = make_job(title="Customer Success Manager", company="AlphaCorp")
    seen = [make_job(title="Customer Success Manager", company="ZetaIndustries")]
    assert is_duplicate(job, seen) is False


def test_empty_seen_list(make_job):
    """Empty seen_jobs list always returns False."""
    job = make_job()
    assert is_duplicate(job, []) is False


def test_threshold_boundary(make_job):
    """Scores right at the threshold boundary — uses > not >=."""
    job = make_job(title="Customer Success Manager", company="Corp")
    seen = [make_job(title="Customer Success Manager", company="Corp")]
    # Exact match (score=100) is above 85 threshold
    assert is_duplicate(job, seen, threshold=85) is True
    # threshold=100 means score must be > 100, which is impossible
    assert is_duplicate(job, seen, threshold=100) is False


# --- SQLite operations ---


def test_init_db_creates_table(tmp_db):
    """Table 'seen_jobs' exists after init_db."""
    conn = sqlite3.connect(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='seen_jobs'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_not_previously_sent(make_job, tmp_db):
    """Fresh DB returns False for any job."""
    job = make_job()
    assert was_previously_sent(job, tmp_db) is False


def test_mark_then_check(make_job, tmp_db):
    """mark_as_sent → was_previously_sent returns True."""
    job = make_job()
    mark_as_sent(job, score=42.0, db_path=tmp_db)
    assert was_previously_sent(job, tmp_db) is True


def test_duplicate_by_url(make_job, tmp_db):
    """Same URL with different title is still detected as sent."""
    job1 = make_job(url="https://example.com/job/1", title="Original Title")
    mark_as_sent(job1, db_path=tmp_db)

    job2 = make_job(url="https://example.com/job/1", title="Updated Title")
    assert was_previously_sent(job2, tmp_db) is True


def test_duplicate_by_title_hash(make_job, tmp_db):
    """Same company+title_hash with different URL is detected."""
    job1 = make_job(
        url="https://example.com/job/1",
        title="Customer Success Manager",
        company="TestCorp",
    )
    mark_as_sent(job1, db_path=tmp_db)

    job2 = make_job(
        url="https://other.com/job/999",
        title="Customer Success Manager",
        company="TestCorp",
    )
    assert was_previously_sent(job2, tmp_db) is True


# --- _stable_hash ---


def test_stable_hash_deterministic():
    """Same input always produces same hash."""
    assert _stable_hash("Hello World") == _stable_hash("Hello World")


def test_stable_hash_case_insensitive():
    """'Hello World' and 'hello world' produce same hash."""
    assert _stable_hash("Hello World") == _stable_hash("hello world")


def test_stable_hash_strips_whitespace():
    """Leading/trailing whitespace is ignored."""
    assert _stable_hash("  test  ") == _stable_hash("test")
