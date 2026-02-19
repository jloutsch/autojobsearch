"""Configuration derived from profile.json. Backward-compatible exports."""

from user_profile import get_profile


def _load():
    """Load all config values from the current profile."""
    global SEARCH_QUERIES, PRIORITY_COMPANIES, INDUSTRIES
    global SALARY_MIN, SALARY_MAX, SALARY_FLOOR
    global GREENHOUSE_BOARDS, ROLE_KEYWORDS
    global MAX_JOB_AGE_DAYS

    _p = get_profile()
    SEARCH_QUERIES = _p["role_tags"]
    PRIORITY_COMPANIES = _p["priority_companies"]
    INDUSTRIES = _p["industry_tags"]
    SALARY_MIN = _p["salary_range"]["min"]
    SALARY_MAX = _p["salary_range"]["max"]
    SALARY_FLOOR = _p["salary_range"].get("floor", 100000)
    GREENHOUSE_BOARDS = _p.get("greenhouse_boards", {})
    ROLE_KEYWORDS = [tag.lower() for tag in _p["role_tags"]]
    MAX_JOB_AGE_DAYS = _p.get("max_job_age_days", 30)


EMPLOYMENT_TYPE = "full-time"
TIMEZONE = "US/Eastern"

ACCEPTED_LOCATIONS = {
    "remote_us": True,
    "hybrid_preferred_city": True,
}

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
]

# Initial load
_load()


def reload():
    """Re-read profile.json and refresh all module-level constants."""
    _load()
