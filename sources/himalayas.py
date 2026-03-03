import logging
from datetime import datetime

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
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            resp = requests.get(
                API_URL,
                params={"limit": PAGE_SIZE, "offset": offset},
                headers={"User-Agent": "AutoJobSearch/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
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

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
