import logging
from datetime import datetime

import requests

import config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://jobicy.com/api/v2/remote-jobs"

QUERIES = [
    {"count": 50, "industry": "supporting", "tag": "customer success"},
    {"count": 50, "industry": "management", "tag": "account manager"},
]


class JobicySource(BaseSource):
    name = "jobicy"

    def collect(self) -> list[JobListing]:
        jobs = []
        seen_urls = set()

        for params in QUERIES:
            resp = requests.get(
                API_URL,
                params=params,
                headers={"User-Agent": "AutoJobSearch/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            listings = data.get("jobs", [])
            for item in listings:
                url = item.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = item.get("jobTitle", "")
                if not self._matches_role(title):
                    continue

                salary_min = self._parse_int(item.get("annualSalaryMin"))
                salary_max = self._parse_int(item.get("annualSalaryMax"))
                posted = self._parse_date(item.get("pubDate", ""))

                job = JobListing(
                    title=title,
                    company=item.get("companyName", ""),
                    url=url,
                    source=self.name,
                    description=item.get("jobExcerpt", ""),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    location=item.get("jobGeo", "Worldwide") or "Worldwide",
                    is_remote=True,
                    posted_date=posted,
                    raw_data=item,
                )
                jobs.append(job)

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_int(self, value) -> int:
        if not value:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
