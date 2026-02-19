import logging
import re
import defusedxml.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

FEED_URLS = [
    "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
    "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
]


class WeWorkRemotelySource(BaseSource):
    name = "weworkremotely"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for feed_url in FEED_URLS:
            jobs = self._fetch_feed(feed_url)
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _fetch_feed(self, feed_url: str) -> list[JobListing]:
        resp = requests.get(feed_url, timeout=30)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return []

        jobs = []
        for item in channel.findall("item"):
            job = self._parse_item(item)
            if job:
                jobs.append(job)

        return jobs

    def _parse_item(self, item: ET.Element) -> JobListing | None:
        raw_title = item.findtext("title", "")

        # Title format is "Company: Job Title"
        if ":" in raw_title:
            company, title = raw_title.split(":", 1)
            company = company.strip()
            title = title.strip()
        else:
            company = ""
            title = raw_title.strip()

        if not self._matches_role(title):
            return None

        link = item.findtext("link", "")
        region = item.findtext("region", "")
        job_type = item.findtext("type", "")
        description_html = item.findtext("description", "")

        # Parse description HTML to plain text for scoring
        description = ""
        if description_html:
            soup = BeautifulSoup(description_html, "html.parser")
            description = soup.get_text(separator=" ", strip=True)

        salary_min, salary_max = self._extract_salary(description)
        posted = self._parse_date(item.findtext("pubDate", ""))

        return JobListing(
            title=title,
            company=company,
            url=link,
            source=self.name,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            location=region,
            is_remote=True,  # All WWR listings are remote
            posted_date=posted,
        )

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _extract_salary(self, text: str) -> tuple[int, int]:
        """Extract salary from description text."""
        if not text:
            return 0, 0

        # Match patterns like "$130,000 - $150,000" or "$130k-$150k"
        range_match = re.search(
            r"\$\s*([\d,]+)\s*[kK]?\s*[-–to]+\s*\$?\s*([\d,]+)\s*[kK]?",
            text,
        )
        if range_match:
            low = range_match.group(1).replace(",", "")
            high = range_match.group(2).replace(",", "")
            low_val = int(low) * (1000 if int(low) < 1000 else 1)
            high_val = int(high) * (1000 if int(high) < 1000 else 1)
            return low_val, high_val

        return 0, 0

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now()
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            return datetime.now()
