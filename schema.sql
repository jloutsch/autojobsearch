CREATE TABLE IF NOT EXISTS seen_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    title TEXT,
    title_hash INTEGER,
    company TEXT,
    source TEXT,
    first_seen DATE DEFAULT CURRENT_DATE,
    score REAL DEFAULT 0,
    status TEXT DEFAULT 'new'  -- new, applied, skipped, interviewing
);
