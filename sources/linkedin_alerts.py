"""LinkedIn job discovery via Google Alerts RSS feeds.

Google Alerts RSS feeds must be created manually (one-time setup):
1. Go to https://www.google.com/alerts
2. Create alert for e.g. "customer success manager" site:linkedin.com/jobs
3. Set delivery to "RSS feed"
4. Copy the feed URL and add it to ALERT_FEED_URLS below

Once created, feeds can be consumed without authentication.
Only jobs posted in the last 24 hours are included.
"""

import logging
import defusedxml.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# Add your Google Alerts RSS feed URLs here after manual creation.
# Each URL looks like: https://www.google.com/alerts/feeds/{user_id}/{alert_id}
ALERT_FEED_URLS: list[str] = [
    # "https://www.google.com/alerts/feeds/00000000000000000000/00000000000000000000",
]

ATOM_NS = "{http://www.w3.org/2005/Atom}"
MAX_AGE = timedelta(hours=24)


class LinkedInAlertsSource(BaseSource):
    name = "linkedin"

    def collect(self) -> list[JobListing]:
        if not ALERT_FEED_URLS:
            logger.info("[linkedin] No Google Alerts feed URLs configured — skipping")
            return []

        all_jobs = []
        seen_urls = set()
        cutoff = datetime.now(timezone.utc) - MAX_AGE

        for feed_url in ALERT_FEED_URLS:
            jobs = self._fetch_feed(feed_url, cutoff)
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _fetch_feed(self, feed_url: str, cutoff: datetime) -> list[JobListing]:
        try:
            resp = requests.get(feed_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[linkedin] Failed to fetch feed: {e}")
            return []

        root = ET.fromstring(resp.content)
        jobs = []

        for entry in root.findall(f"{ATOM_NS}entry"):
            job = self._parse_entry(entry, cutoff)
            if job:
                jobs.append(job)

        return jobs

    def _parse_entry(self, entry: ET.Element, cutoff: datetime) -> JobListing | None:
        # Parse published date and enforce 24-hour recency
        updated_str = entry.findtext(f"{ATOM_NS}updated", "")
        published_str = entry.findtext(f"{ATOM_NS}published", updated_str)
        posted = self._parse_date(published_str)

        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if posted < cutoff:
            return None

        # Google Alerts titles are HTML — extract text
        raw_title = entry.findtext(f"{ATOM_NS}title", "")
        title = BeautifulSoup(raw_title, "html.parser").get_text(strip=True)

        # Extract URL from the link element
        link_el = entry.find(f"{ATOM_NS}link")
        url = link_el.get("href", "") if link_el is not None else ""

        # Google Alerts wraps URLs in a redirect — extract the actual URL
        if "google.com/url?" in url:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            url = params.get("url", params.get("q", [url]))[0]

        # Extract description/snippet
        content_el = entry.find(f"{ATOM_NS}content")
        description = ""
        if content_el is not None and content_el.text:
            description = BeautifulSoup(content_el.text, "html.parser").get_text(
                separator=" ", strip=True
            )

        # Try to extract company from title patterns like "Job Title at Company"
        company = ""
        if " at " in title:
            parts = title.rsplit(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()
        elif " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                title = parts[0].strip()
                company = parts[1].strip()

        if not self._matches_role(title):
            return None

        return JobListing(
            title=title,
            company=company,
            url=url,
            source=self.name,
            description=description,
            is_remote=True,  # Will be validated by hard filters
            posted_date=posted,
        )

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            # Google Alerts uses ISO 8601 format
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)
