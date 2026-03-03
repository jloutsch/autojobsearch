import logging
import re
from datetime import datetime

import requests

import config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(BaseSource):
    name = "remotive"

    def collect(self) -> list[JobListing]:
        resp = requests.get(
            API_URL,
            params={"category": "customer-support", "limit": 100},
            headers={"User-Agent": "AutoJobSearch/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        listings = data.get("jobs", [])
        jobs = []
        for item in listings:
            title = item.get("title", "")
            if not self._matches_role(title):
                continue

            salary_min, salary_max = self._parse_salary(item.get("salary", ""))
            posted = self._parse_date(item.get("publication_date", ""))

            job = JobListing(
                title=title,
                company=item.get("company_name", ""),
                url=item.get("url", ""),
                source=self.name,
                description=item.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                location=item.get("candidate_required_location", "Worldwide") or "Worldwide",
                is_remote=True,
                posted_date=posted,
                raw_data=item,
            )
            jobs.append(job)

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_salary(self, salary_str: str) -> tuple[int, int]:
        if not salary_str:
            return 0, 0
        # Match number optionally followed by 'k'
        matches = re.findall(r"([\d,]+)\s*k?", salary_str, re.IGNORECASE)
        if not matches:
            return 0, 0
        nums = []
        for m in matches:
            val = int(m.replace(",", ""))
            if val == 0:
                continue
            # Normalize k-notation: values under 1000 with 'k' nearby
            if val < 1000:
                val *= 1000
            nums.append(val)
        if len(nums) >= 2:
            return nums[0], nums[1]
        if len(nums) == 1:
            return nums[0], nums[0]
        return 0, 0

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
