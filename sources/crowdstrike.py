"""CrowdStrike job listings via Workday public API."""

import logging
import re
from datetime import datetime, timedelta, timezone

import requests

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://crowdstrike.wd5.myworkdayjobs.com/wday/cxs/crowdstrike/crowdstrikecareers"
SEARCH_URL = f"{BASE_URL}/jobs"
PAGE_SIZE = 20  # Workday max per request


class CrowdStrikeSource(BaseSource):
    name = "crowdstrike"

    def collect(self) -> list[JobListing]:
        all_postings = self._search_all()
        logger.info(f"[crowdstrike] Found {len(all_postings)} matching roles")

        jobs = []
        for posting in all_postings:
            job = self._posting_to_job(posting)
            if job:
                jobs.append(job)

        return jobs

    def _search_all(self) -> list[dict]:
        """Search for matching roles across all pages."""
        all_postings = []

        for query in self._search_queries():
            offset = 0
            while True:
                data = self._search_page(query, offset)
                if not data:
                    break

                postings = data.get("jobPostings", [])
                all_postings.extend(postings)

                total = data.get("total", 0)
                offset += PAGE_SIZE
                if offset >= total or not postings:
                    break

        # Deduplicate by externalPath
        seen = set()
        unique = []
        for p in all_postings:
            path = p.get("externalPath", "")
            if path not in seen:
                seen.add(path)
                unique.append(p)

        return unique

    def _search_queries(self) -> list[str]:
        """Generate search queries from configured role tags."""
        return config.SEARCH_QUERIES[:4]

    def _search_page(self, query: str, offset: int) -> dict | None:
        try:
            resp = requests.post(
                SEARCH_URL,
                json={
                    "appliedFacets": {},
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "searchText": query,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"[crowdstrike] Search failed for '{query}' offset={offset}: {e}")
            return None

    def _posting_to_job(self, posting: dict) -> JobListing | None:
        title = posting.get("title", "")
        if not self._matches_role(title):
            return None

        external_path = posting.get("externalPath", "")
        url = f"https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers{external_path}"
        location = posting.get("locationsText", "")

        posted_date = self._parse_posted_on(posting.get("postedOn", ""))

        return JobListing(
            title=title,
            company="CrowdStrike",
            url=url,
            source=self.name,
            location=location,
            is_remote="remote" in title.lower() or "remote" in location.lower(),
            posted_date=posted_date,
            raw_data=posting,
        )

    def _parse_posted_on(self, text: str) -> datetime:
        """Parse Workday's 'Posted X Days Ago' format."""
        if not text:
            return datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        text_lower = text.lower()

        if "today" in text_lower:
            return now

        match = re.search(r"(\d+)\s+(day|hour|week|month)", text_lower)
        if not match:
            return now

        amount = int(match.group(1))
        unit = match.group(2)

        if unit == "hour":
            return now - timedelta(hours=amount)
        elif unit == "day":
            return now - timedelta(days=amount)
        elif unit == "week":
            return now - timedelta(weeks=amount)
        elif unit == "month":
            return now - timedelta(days=amount * 30)

        return now

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)
