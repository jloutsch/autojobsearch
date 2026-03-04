import logging
from datetime import datetime

import requests

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbySource(BaseSource):
    name = "ashby"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        for company, slug in config.ASHBY_BOARDS.items():
            jobs = self._fetch_board(company, slug)
            all_jobs.extend(jobs)
        return all_jobs

    def _fetch_board(self, company: str, slug: str) -> list[JobListing]:
        url = API_BASE.format(slug=slug)
        resp = requests.get(
            url,
            headers={"User-Agent": "AutoJobSearch/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not self._matches_role(title):
                continue

            location = item.get("location", "")
            is_remote = self._detect_remote(item, location)
            posted = self._parse_date(item.get("publishedAt", ""))

            job = JobListing(
                title=title,
                company=company,
                url=item.get("jobUrl", ""),
                source=self.name,
                description=item.get("descriptionPlain", "") or "",
                location=location,
                is_remote=is_remote,
                posted_date=posted,
                raw_data=item,
            )
            jobs.append(job)

        logger.info(f"[ashby/{slug}] Found {len(jobs)} matching roles out of {len(data.get('jobs', []))} total")
        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _detect_remote(self, item: dict, location: str) -> bool:
        is_remote = item.get("isRemote")
        if is_remote is not None:
            return bool(is_remote)
        return "remote" in location.lower()

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
