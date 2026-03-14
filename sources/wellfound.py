"""Wellfound (formerly AngelList) job source via Chrome browser.

Wellfound uses DataDome bot protection, requiring a real Chrome browser.
Job data is embedded in a __NEXT_DATA__ script tag as Apollo GraphQL state.

Wellfound only supports predefined role categories (not free-text search).
We map role_tags to known Wellfound role slugs where possible.
"""

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

import config
from models import JobListing
from sources.chrome_base import ChromeBrowserSource

logger = logging.getLogger(__name__)

ROLE_URL = "https://wellfound.com/role/r/{slug}"
MAX_PAGES = 3

# Map config role_tags to Wellfound's predefined role category slugs.
# Only roles that exist on Wellfound are included.
WELLFOUND_ROLE_SLUGS = [
    "account-manager",
    "customer-support",
    "operations-manager",
    "sales-manager",
    "technical-support",
]


class WellfoundSource(ChromeBrowserSource):
    name = "wellfound"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for slug in WELLFOUND_ROLE_SLUGS:
            try:
                jobs = self._fetch_role(slug)
            except Exception as e:
                logger.warning(f"[wellfound] Failed role '{slug}': {e}")
                continue
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _fetch_role(self, slug: str) -> list[JobListing]:
        jobs = []

        for page_num in range(1, MAX_PAGES + 1):
            url = ROLE_URL.format(slug=slug)
            if page_num > 1:
                url += f"?page={page_num}"

            self._navigate(url, wait_range=(2.0, 4.0))

            # Check if we got redirected to /remote (role doesn't exist)
            if self._page.url.rstrip("/").endswith("/remote"):
                break

            page_jobs, has_more = self._extract_jobs()
            jobs.extend(page_jobs)

            if not has_more or not page_jobs:
                break

        return jobs

    def _extract_jobs(self) -> tuple[list[JobListing], bool]:
        html = self._get_page_html()
        soup = BeautifulSoup(html, "html.parser")

        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return [], False

        try:
            next_data = json.loads(script.string)
        except json.JSONDecodeError:
            logger.warning("[wellfound] Failed to parse __NEXT_DATA__ JSON")
            return [], False

        apollo_state = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("apolloState", {})
            .get("data", {})
        )
        if not apollo_state:
            return [], False

        # Build company lookup from StartupResult refs
        company_lookup = {}
        for key, val in apollo_state.items():
            if key.startswith("StartupResult:") and isinstance(val, dict):
                for ref in val.get("highlightedJobListings", []):
                    if isinstance(ref, dict) and "__ref" in ref:
                        company_lookup[ref["__ref"]] = {
                            "name": val.get("name", ""),
                            "slug": val.get("slug", ""),
                        }

        # Extract pagination info
        has_more = False
        root_query = apollo_state.get("ROOT_QUERY", {})
        for key, val in root_query.items():
            if isinstance(val, dict) and "pageCount" in val:
                page_count = val.get("pageCount", 1)
                current_page = val.get("page", 1)
                has_more = current_page < page_count
                break

        jobs = []
        for key, val in apollo_state.items():
            if not key.startswith("JobListingSearchResult:"):
                continue
            if not isinstance(val, dict) or "title" not in val:
                continue

            title = val.get("title", "")
            if not self._matches_role(title):
                continue

            # Company from lookup
            company_info = company_lookup.get(key, {})
            company_name = company_info.get("name", "")

            # Job URL
            job_slug = val.get("slug", "")
            job_id = val.get("id", key.split(":")[-1])
            job_url = f"https://wellfound.com/jobs/{job_id}-{job_slug}" if job_slug else ""

            # Location
            location_names = val.get("locationNames", [])
            if isinstance(location_names, list):
                location = ", ".join(location_names) if location_names else ""
            else:
                location = str(location_names or "")

            # Remote
            is_remote = bool(val.get("remote", False))

            # Salary
            compensation = val.get("compensation", "")
            salary_min, salary_max = self._parse_compensation(compensation)

            # Date — liveStartAt is a Unix timestamp
            live_start = val.get("liveStartAt", "")
            posted = self._parse_date(live_start)

            # Description
            description = val.get("description", "") or ""

            job = JobListing(
                title=title,
                company=company_name,
                url=job_url,
                source=self.name,
                description=description[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                location=location,
                is_remote=is_remote,
                posted_date=posted,
            )
            jobs.append(job)

        return jobs, has_more

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_compensation(self, comp) -> tuple[int, int]:
        if not comp:
            return 0, 0
        text = str(comp)
        range_match = re.search(
            r"\$\s*([\d,]+)\s*[kK]?\s*[-\u2013]+\s*\$?\s*([\d,]+)\s*[kK]?",
            text,
        )
        if range_match:
            low = int(range_match.group(1).replace(",", ""))
            high = int(range_match.group(2).replace(",", ""))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            return low, high
        return 0, 0

    def _parse_date(self, value) -> datetime:
        if not value:
            return datetime.now()
        try:
            # Unix timestamp (integer or string)
            ts = int(value)
            return datetime.fromtimestamp(ts)
        except (ValueError, TypeError, OSError):
            pass
        try:
            # ISO format fallback
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
