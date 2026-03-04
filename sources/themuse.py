import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://www.themuse.com/api/public/jobs"


class TheMuseSource(BaseSource):
    name = "themuse"

    def collect(self) -> list[JobListing]:
        jobs = []
        seen_urls = set()
        page = 0

        while True:
            resp = requests.get(
                API_URL,
                params={
                    "category": "Account Management",
                    "location": "Flexible / Remote",
                    "page": page,
                },
                headers={"User-Agent": "AutoJobSearch/1.0"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", []):
                title = item.get("name", "")
                if not self._matches_role(title):
                    continue

                url = item.get("refs", {}).get("landing_page", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                company = item.get("company", {}).get("name", "")
                contents = item.get("contents", "")
                description = self._strip_html(contents)
                salary_min, salary_max = self._extract_salary(contents)
                location = self._extract_location(item)
                is_remote = self._detect_remote(item)
                posted = self._parse_date(item.get("publication_date", ""))

                job = JobListing(
                    title=title,
                    company=company,
                    url=url,
                    source=self.name,
                    description=description,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    location=location,
                    is_remote=is_remote,
                    posted_date=posted,
                    raw_data=item,
                )
                jobs.append(job)

            page_count = data.get("page_count", 0)
            page += 1
            if page >= page_count:
                break

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _strip_html(self, html: str) -> str:
        if not html:
            return ""
        return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)

    def _extract_salary(self, html: str) -> tuple[int, int]:
        if not html:
            return 0, 0
        text = self._strip_html(html)
        match = re.search(
            r'\$\s*([\d,]+(?:\.\d+)?)\s*[k]?\s*[-–—to]+\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[k]?',
            text, re.IGNORECASE,
        )
        if not match:
            return 0, 0
        try:
            low = float(match.group(1).replace(",", ""))
            high = float(match.group(2).replace(",", ""))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            return int(low), int(high)
        except (ValueError, TypeError):
            return 0, 0

    def _extract_location(self, item: dict) -> str:
        locations = item.get("locations", [])
        if not locations:
            return ""
        return ", ".join(loc.get("name", "") for loc in locations)

    def _detect_remote(self, item: dict) -> bool:
        for loc in item.get("locations", []):
            name = loc.get("name", "").lower()
            if "remote" in name or "flexible" in name:
                return True
        return False

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now()
