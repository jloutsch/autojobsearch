import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"

RELEVANT_CATEGORIES = {"Customer Success", "Sales", "Administration", "Management"}


class WorkingNomadsSource(BaseSource):
    name = "workingnomads"

    def collect(self) -> list[JobListing]:
        resp = requests.get(API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data:
            category = item.get("category_name", "")
            if category not in RELEVANT_CATEGORIES:
                continue

            title = item.get("title", "")
            if not self._matches_role(title):
                continue

            description_html = item.get("description", "")
            description = ""
            if description_html:
                soup = BeautifulSoup(description_html, "html.parser")
                description = soup.get_text(separator=" ", strip=True)

            posted = self._parse_date(item.get("pub_date", ""))

            job = JobListing(
                title=title,
                company=item.get("company_name", ""),
                url=item.get("url", ""),
                source=self.name,
                description=description,
                salary_min=0,
                salary_max=0,
                location=item.get("location", "Remote"),
                is_remote=True,
                posted_date=posted,
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
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            return datetime.now()
