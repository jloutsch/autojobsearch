import logging
import re
import html as html_mod
import defusedxml.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

FEED_BASE = "https://jobspresso.co/feed/?post_type=job_listing&s="

DC_NS = "http://purl.org/dc/elements/1.1/"


class JobspressoSource(BaseSource):
    name = "jobspresso"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for tag in config.SEARCH_QUERIES:
            feed_url = FEED_BASE + tag.replace(" ", "+")
            try:
                jobs = self._fetch_feed(feed_url)
            except Exception as e:
                logger.warning(f"[jobspresso] Failed to fetch tag '{tag}': {e}")
                continue
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

    def _parse_item(self, item) -> JobListing | None:
        title = item.findtext("title", "").strip()

        if not self._matches_role(title):
            return None

        link = item.findtext("link", "")

        # Company and location from dc:creator CDATA
        # Format: "Company Name<br>&#9906;&nbsp;Location"
        creator_raw = item.findtext(f"{{{DC_NS}}}creator", "")
        company, location = self._parse_creator(creator_raw)

        # Full description from content:encoded, fallback to description
        content_ns = "http://purl.org/rss/1.0/modules/content/"
        description_html = item.findtext(f"{{{content_ns}}}encoded", "")
        if not description_html:
            description_html = item.findtext("description", "")

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
            location=location,
            is_remote=True,
            posted_date=posted,
        )

    def _parse_creator(self, raw: str) -> tuple[str, str]:
        """Parse 'Company Name<br>&#9906;&nbsp;Location' into (company, location)."""
        if not raw:
            return "", ""

        # Unescape HTML entities first
        text = html_mod.unescape(raw)

        # Split on <br> tag (case insensitive)
        parts = re.split(r"<br\s*/?>", text, flags=re.IGNORECASE)
        company = parts[0].strip()

        location = ""
        if len(parts) > 1:
            # Strip the pin marker (⚲) and surrounding whitespace/nbsp
            loc = parts[1].strip()
            loc = loc.lstrip("\u2732\u26b2\u2316\u29b2")  # various pin-like chars
            loc = re.sub(r"^[\s\u00a0⚲]+", "", loc)  # ⚲ and nbsp
            location = loc.strip()

        return company, location

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _extract_salary(self, text: str) -> tuple[int, int]:
        if not text:
            return 0, 0

        range_match = re.search(
            r"\$\s*([\d,]+)\s*[kK]?\s*[-\u2013to]+\s*\$?\s*([\d,]+)\s*[kK]?",
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
