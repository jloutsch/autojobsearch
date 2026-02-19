import json
import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://builtin.com/jobs/remote"


class BuiltInSource(BaseSource):
    name = "builtin"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for query in config.SEARCH_QUERIES:
            jobs = self._search(query)
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _search(self, query: str) -> list[JobListing]:
        try:
            resp = requests.get(
                SEARCH_URL,
                params={"search": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[builtin] Search failed for '{query}': {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        published_dates = self._extract_published_dates(soup)
        return self._parse_results(soup, published_dates)

    def _extract_published_dates(self, soup: BeautifulSoup) -> dict[int, datetime]:
        """Extract exact published_date timestamps from the tracking script in body onload."""
        dates = {}
        body = soup.find("body")
        if not body:
            return dates

        onload = body.get("onload", "")
        # Find the job_board_view tracking call with published_date fields
        # Pattern: {'id': 7611076, 'published_date': '2026-02-17T00:04:07', ...}
        for match in re.finditer(r"'id':\s*(\d+),\s*'published_date':\s*'([^']+)'", onload):
            job_id = int(match.group(1))
            try:
                dates[job_id] = datetime.fromisoformat(match.group(2)).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        if not dates:
            # Fallback: try parsing from any script tag
            for script in soup.find_all("script"):
                text = script.string or ""
                for match in re.finditer(r'"id":\s*(\d+),\s*"published_date":\s*"([^"]+)"', text):
                    job_id = int(match.group(1))
                    try:
                        dates[job_id] = datetime.fromisoformat(match.group(2)).replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

        return dates

    def _parse_results(self, soup: BeautifulSoup, published_dates: dict[int, datetime]) -> list[JobListing]:
        jobs = []
        cards = soup.select('div[data-id="job-card"]')

        for card in cards:
            try:
                job = self._parse_card(card, published_dates)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[builtin] Failed to parse card: {e}")
                continue

        return jobs

    def _parse_card(self, card, published_dates: dict[int, datetime]) -> JobListing | None:
        # Title + URL
        title_el = card.select_one('a[data-id="job-card-title"]')
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        url = href if href.startswith("http") else f"https://builtin.com{href}"

        # Extract job ID for date lookup
        job_id = None
        track_id = title_el.get("data-builtin-track-job-id", "")
        if track_id:
            try:
                job_id = int(track_id)
            except ValueError:
                pass

        # Company name
        company_el = card.select_one('a[data-id="company-title"] span')
        company = company_el.get_text(strip=True) if company_el else ""

        # Metadata spans: work type, location, salary, level
        spans = card.select("span.font-barlow.text-gray-04")
        work_type = spans[0].get_text(strip=True) if len(spans) > 0 else ""
        location = spans[1].get_text(strip=True) if len(spans) > 1 else ""
        salary_text = spans[2].get_text(strip=True) if len(spans) > 2 else ""

        salary_min, salary_max = self._parse_salary(salary_text)
        is_remote = "remote" in work_type.lower()

        # Get posted date from tracking data, fall back to relative text on card
        posted_date = published_dates.get(job_id) if job_id else None
        if not posted_date:
            posted_date = self._parse_relative_date(card)

        return JobListing(
            title=title,
            company=company,
            url=url,
            source=self.name,
            salary_min=salary_min,
            salary_max=salary_max,
            location=location,
            is_remote=is_remote,
            posted_date=posted_date,
        )

    def _parse_relative_date(self, card) -> datetime:
        """Parse 'Posted/Reposted X Days/Hours Ago' from the card's date span."""
        date_span = card.select_one("span.bg-gray-01.font-Montserrat.text-gray-03")
        if not date_span:
            return datetime.now(timezone.utc)

        text = date_span.get_text(strip=True).lower()
        from datetime import timedelta

        # "Reposted" means the job was republished — the date is the repost date.
        # Log this so users know it's not a fresh listing.
        if "repost" in text:
            logger.debug(f"[builtin] Detected reposted listing")

        match = re.search(r"(\d+)\s+(hour|day|week|month)", text)
        if not match:
            return datetime.now(timezone.utc)

        amount = int(match.group(1))
        unit = match.group(2)
        now = datetime.now(timezone.utc)

        if unit == "hour":
            return now - timedelta(hours=amount)
        elif unit == "day":
            return now - timedelta(days=amount)
        elif unit == "week":
            return now - timedelta(weeks=amount)
        elif unit == "month":
            return now - timedelta(days=amount * 30)

        return now

    def _parse_salary(self, text: str) -> tuple[int, int]:
        """Parse salary strings like '120K-140K Annually' or '$130,000 - $150,000'."""
        if not text:
            return 0, 0

        # Match patterns like "120K-140K" or "120k - 140k"
        k_match = re.findall(r"(\d+)K", text, re.IGNORECASE)
        if len(k_match) >= 2:
            return int(k_match[0]) * 1000, int(k_match[1]) * 1000
        elif len(k_match) == 1:
            return int(k_match[0]) * 1000, 0

        # Match patterns like "$130,000 - $150,000"
        full_match = re.findall(r"\$?([\d,]+)", text)
        if len(full_match) >= 2:
            return int(full_match[0].replace(",", "")), int(full_match[1].replace(",", ""))
        elif len(full_match) == 1:
            return int(full_match[0].replace(",", "")), 0

        return 0, 0
