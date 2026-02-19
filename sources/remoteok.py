import logging
from datetime import datetime

import requests

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://remoteok.com/api"


class RemoteOKSource(BaseSource):
    name = "remoteok"

    def collect(self) -> list[JobListing]:
        resp = requests.get(
            API_URL,
            headers={"User-Agent": "AutoJobSearch/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # First element is metadata/legal notice, skip it
        listings = data[1:] if len(data) > 1 else []

        jobs = []
        for item in listings:
            title = item.get("position", "")
            if not self._matches_role(title):
                continue

            salary_min, salary_max = self._parse_salary(item)
            posted = self._parse_date(item.get("date", ""))

            job = JobListing(
                title=title,
                company=item.get("company", ""),
                url=item.get("url", ""),
                source=self.name,
                description=item.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                location=item.get("location", "Worldwide"),
                is_remote=True,  # All RemoteOK listings are remote
                posted_date=posted,
                raw_data=item,
            )
            jobs.append(job)

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_salary(self, item: dict) -> tuple[int, int]:
        try:
            sal_min = int(item.get("salary_min", 0) or 0)
            sal_max = int(item.get("salary_max", 0) or 0)
            return sal_min, sal_max
        except (ValueError, TypeError):
            return 0, 0

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
