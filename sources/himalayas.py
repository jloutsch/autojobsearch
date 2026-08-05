import logging
from datetime import datetime, timezone

import requests

import config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://himalayas.app/jobs/api"
MAX_PAGES = 5
PAGE_SIZE = 20


class HimalayasSource(BaseSource):
    name = "himalayas"

    def collect(self) -> list[JobListing]:
        jobs = []
        seen_urls = set()

        for query in config.SEARCH_QUERIES:
            self._fetch_query(query, jobs, seen_urls)

        return jobs

    def _fetch_query(self, query: str, jobs: list, seen_urls: set) -> None:
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            try:
                resp = requests.get(
                    API_URL,
                    params={"limit": PAGE_SIZE, "offset": offset, "q": query},
                    headers={"User-Agent": "AutoJobSearch/1.0"},
                    timeout=30,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning(f"[himalayas] Failed to fetch query '{query}': {e}")
                break
            data = resp.json()

            listings = data.get("jobs", [])
            if not listings:
                break

            for item in listings:
                title = item.get("title", "")
                if not self._matches_role(title):
                    continue

                salary_min = int(item.get("salaryMin") or 0)
                salary_max = int(item.get("salaryMax") or 0)
                posted = self._parse_date(item.get("pubDate", ""))

                url = item.get("url", "")
                if not url:
                    slug = item.get("slug", "")
                    company_slug = item.get("companySlug", "")
                    if slug and company_slug:
                        url = f"https://himalayas.app/companies/{company_slug}/jobs/{slug}"

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                job = JobListing(
                    title=title,
                    company=item.get("companyName", ""),
                    url=url,
                    source=self.name,
                    description=item.get("description", ""),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    location=str(item.get("locationRestrictions", "") or "") or "Worldwide",
                    is_remote=True,
                    posted_date=posted,
                    raw_data=item,
                )
                jobs.append(job)

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_date(self, date_str) -> datetime:
        if not date_str:
            return datetime.now(timezone.utc)
        # himalayas returns pubDate as a Unix timestamp (int seconds)
        if isinstance(date_str, (int, float)):
            try:
                return datetime.fromtimestamp(date_str, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            return datetime.now(timezone.utc)
