import logging
from datetime import datetime

import requests

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


class GreenhouseSource(BaseSource):
    name = "greenhouse"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        for company, board_token in config.GREENHOUSE_BOARDS.items():
            jobs = self._fetch_board(company, board_token)
            all_jobs.extend(jobs)
        return all_jobs

    def _fetch_board(self, company: str, board_token: str) -> list[JobListing]:
        url = API_BASE.format(board=board_token)
        resp = requests.get(url, params={"content": "true"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not self._matches_role(title):
                continue

            location = self._extract_location(item)
            posted = self._parse_date(
                item.get("first_published", "") or item.get("updated_at", "")
            )

            job = JobListing(
                title=title,
                company=company,
                url=item.get("absolute_url", ""),
                source=self.name,
                description=item.get("content", ""),
                location=location,
                is_remote="remote" in location.lower(),
                posted_date=posted,
                raw_data=item,
            )
            jobs.append(job)

        logger.info(f"[greenhouse/{board_token}] Found {len(jobs)} matching roles out of {len(data.get('jobs', []))} total")
        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _extract_location(self, item: dict) -> str:
        locations = item.get("location", {})
        return locations.get("name", "") if isinstance(locations, dict) else ""

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
