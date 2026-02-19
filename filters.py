import logging
import re
from datetime import datetime, timedelta, timezone

import config as config
from models import JobListing

logger = logging.getLogger(__name__)

# Non-US countries and regions that should be rejected
NON_US_SIGNALS = [
    "india", "canada", "brazil", "mexico", "chile", "argentina", "colombia",
    "united kingdom", "uk", "ireland", "france", "germany", "spain", "italy",
    "netherlands", "sweden", "norway", "denmark", "finland", "poland", "portugal",
    "czech", "austria", "switzerland", "belgium", "romania", "hungary", "croatia",
    "israel", "dubai", "uae", "united arab emirates", "saudi", "qatar",
    "south africa", "nigeria", "kenya", "egypt",
    "japan", "korea", "china", "singapore", "indonesia", "australia",
    "new zealand", "philippines", "vietnam", "thailand", "malaysia", "taiwan",
    "emea", "apac", "latam", "latin america",
    "london", "paris", "berlin", "dublin", "amsterdam", "madrid", "barcelona",
    "munich", "tokyo", "sydney", "melbourne", "toronto", "vancouver", "montreal",
    "bangalore", "hyderabad", "mumbai", "delhi", "pune",
    "sao paulo", "tel aviv", "jakarta", "seoul",
]

# Boston area identifiers
BOSTON_SIGNALS = [
    "boston", "cambridge, ma", "somerville, ma", "brookline",
    "waltham", "newton, ma", "quincy, ma",
]

# Non-Boston US states/cities — if a "remote" role is pinned to one of these,
# it's location-restricted remote, not work-from-anywhere remote
NON_BOSTON_US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
    "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
    "district of columbia",
]

NON_BOSTON_US_CITIES = [
    "new york", "chicago", "denver", "austin", "seattle",
    "san francisco", "los angeles", "atlanta", "dallas", "houston",
    "miami", "philadelphia", "phoenix", "portland", "raleigh",
    "charlotte", "minneapolis", "detroit", "columbus", "indianapolis",
    "nashville", "salt lake", "tampa", "pittsburgh", "st. louis",
    "kansas city", "san diego", "san jose", "san antonio",
    "centennial", "mountain view", "palo alto", "sunnyvale",
]


def passes_hard_filters(job: JobListing) -> bool:
    """Reject listings that clearly don't match. Enforces:
    - US-wide remote (not state-restricted) or hybrid/on-site Boston
    - Role keyword match
    - Not junior
    - Salary floor
    """
    title_lower = job.title.lower()

    # Must match at least one target role family keyword
    if not any(kw in title_lower for kw in config.ROLE_KEYWORDS):
        return False

    # Reject junior roles
    junior_signals = ["junior", "associate", "entry level", "intern"]
    if any(signal in title_lower for signal in junior_signals):
        return False

    # Salary floor check (if salary data is available)
    if job.salary_max > 0 and job.salary_max < config.SALARY_FLOOR:
        return False

    # Staleness check — reject jobs older than MAX_JOB_AGE_DAYS
    if not _passes_age_filter(job):
        return False

    # --- Location filter ---
    if not _passes_location_filter(job):
        return False

    return True


def _passes_age_filter(job: JobListing) -> bool:
    """Reject jobs older than MAX_JOB_AGE_DAYS."""
    if config.MAX_JOB_AGE_DAYS <= 0:
        return True  # Disabled
    now = datetime.now(timezone.utc)
    posted = job.posted_date
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    age = now - posted
    if age.days > config.MAX_JOB_AGE_DAYS:
        logger.debug(f"Rejecting stale job ({age.days}d old): {job.title} @ {job.company}")
        return False
    return True


def _passes_location_filter(job: JobListing) -> bool:
    """Accept only:
    1. US-wide remote roles (no specific state/city restriction)
    2. Hybrid or on-site roles in the Boston area
    """
    loc_lower = job.location.lower().strip()
    loc_original = job.location.strip()  # Preserve case for abbreviation matching
    title_lower = job.title.lower()
    desc_lower = job.description.lower()

    # Reject if location clearly indicates non-US
    if _is_non_us(loc_lower) or _is_non_us(title_lower):
        return False

    # --- Boston area (hybrid or on-site) — always accept ---
    if _is_boston(loc_lower) or _is_boston(title_lower):
        return True

    # --- Check if it's a remote role ---
    is_remote = job.is_remote or "remote" in loc_lower or "remote" in title_lower

    if is_remote:
        # Accept if location says US-wide with no specific state/city
        if _is_us_wide_remote(loc_lower, loc_original, title_lower, desc_lower):
            return True
        # Reject state/city-restricted remote (e.g. "Florida, USA, Remote")
        return False

    # --- Not remote, not Boston — reject ---
    # (on-site roles in non-Boston US cities)
    return False


def _is_us_wide_remote(loc_lower: str, loc_original: str, title: str, desc: str) -> bool:
    """Check if a remote role is truly US-wide, not restricted to specific states/cities."""

    # Location is just "remote" with no qualifier — accept
    if loc_lower in ("remote", "remote - us east", "remote - us west", ""):
        return True

    # "N Locations" without specifics — accept (common on BuiltIn)
    if re.match(r"^\d+ locations?$", loc_lower):
        return True

    # Just "US" as the whole location
    if loc_lower in ("us", "u.s.", "u.s.a."):
        return True

    # IMPORTANT: Check pinning BEFORE US-wide patterns, because locations
    # like "TX, USA" or "Florida, USA, Remote" contain "usa" as a substring
    # but are actually state-restricted.
    if _is_pinned_to_non_boston_location(loc_lower, loc_original):
        return False

    # Broad US-wide signals in location field (checked AFTER pinning)
    us_wide_patterns = [
        "united states",
        "united states - remote",
        "united states of america",
        "usa",
        "us remote",
        "remote - us",
        "remote us",
        "remote, us",
        "nationwide",
        "anywhere in the us",
        "anywhere in the world",
        "worldwide",
    ]

    for pattern in us_wide_patterns:
        if pattern in loc_lower:
            return True

    # Check the description for location restrictions
    restriction_signals = [
        "must be located in",
        "must reside in",
        "candidates must be based in",
        "hiring remotely in",
        "remote from",
        "this role is open to candidates in",
        "open to remote candidates in",
        "based out of",
    ]
    for sig in restriction_signals:
        if sig in desc:
            # Check if the restriction is to Boston/MA — that's fine
            idx = desc.index(sig)
            context = desc[idx:idx+100]
            if _is_boston(context):
                return True
            # Restricted to somewhere else
            return False

    # Default deny — only accept locations explicitly matched above.
    # Sources like RemoteOK/WWR set is_remote=True with an empty or
    # "Worldwide" location, which is already matched above.
    return False


def _is_pinned_to_non_boston_location(loc_lower: str, loc_original: str) -> bool:
    """Check if a location string pins the role to a specific non-Boston US place."""
    # Check for specific non-Boston state names (lowercase comparison)
    for state in NON_BOSTON_US_STATES:
        if state in loc_lower:
            return True

    # Check for non-Boston city names (lowercase comparison)
    for city in NON_BOSTON_US_CITIES:
        if city in loc_lower:
            return True

    # Check for state abbreviations (2-letter) in ORIGINAL case location
    # e.g. "FL, USA" or "TX, USA" or "OH, USA" — but not "MA"
    non_boston_abbrevs = [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
        "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MI", "MN", "MS",
        "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
        "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
        "WI", "WY", "DC",
    ]
    for abbr in non_boston_abbrevs:
        if re.search(rf'\b{abbr}\b', loc_original):
            return True

    return False


def _is_boston(text: str) -> bool:
    """Check if text references the Boston area."""
    return any(sig in text for sig in BOSTON_SIGNALS)


def _is_non_us(text: str) -> bool:
    """Check if text clearly indicates a non-US country/region."""
    for sig in NON_US_SIGNALS:
        if len(sig) <= 3:
            # Short signals (e.g. "uk", "uae") need word boundaries
            # to avoid matching "unlock", "bulk", etc.
            if re.search(rf'\b{re.escape(sig)}\b', text):
                return True
        elif sig in text:
            return True
    return False
