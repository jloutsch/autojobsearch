import hashlib
import sqlite3

from thefuzz import fuzz

from models import JobListing


def _stable_hash(text: str) -> str:
    """Deterministic hash that's consistent across process restarts."""
    return hashlib.sha256(text.lower().strip().encode()).hexdigest()[:16]


def is_duplicate(job: JobListing, seen_jobs: list[JobListing], threshold: int = 85) -> bool:
    """Fuzzy match on title + company to catch cross-posted roles."""
    for seen in seen_jobs:
        title_score = fuzz.token_sort_ratio(job.title, seen.title)
        company_score = fuzz.token_sort_ratio(job.company, seen.company)
        if title_score > threshold and company_score > threshold:
            return True
    return False


def init_db(db_path: str = "seen_jobs.db") -> None:
    """Initialize the SQLite database with schema."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            title_hash TEXT,
            company TEXT,
            source TEXT,
            first_seen DATE DEFAULT CURRENT_DATE,
            score REAL DEFAULT 0,
            status TEXT DEFAULT 'new'
        )
    """)
    conn.commit()
    conn.close()


def was_previously_sent(job: JobListing, db_path: str = "seen_jobs.db") -> bool:
    """Check SQLite database of previously delivered listings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE url = ? OR (company = ? AND title_hash = ?)",
        (job.url, job.company, _stable_hash(job.title)),
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_as_sent(job: JobListing, score: float = 0, db_path: str = "seen_jobs.db") -> None:
    """Record a job listing in the seen database."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO seen_jobs (url, title, title_hash, company, source, score) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                job.url,
                job.title,
                _stable_hash(job.title),
                job.company,
                job.source,
                score,
            ),
        )
        conn.commit()
    finally:
        conn.close()
