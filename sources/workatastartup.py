import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

import config as config
from models import JobListing
from sources.base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.workatastartup.com/jobs"

ROLE_PARAMS = ["support", "sales"]


class WorkAtAStartupSource(BaseSource):
    name = "workatastartup"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for role in ROLE_PARAMS:
            jobs = self._fetch_page(role)
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _fetch_page(self, role: str) -> list[JobListing]:
        try:
            resp = requests.get(
                BASE_URL,
                params={"role": role},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[workatastartup] Fetch failed for role={role}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_results(soup)

    def _parse_results(self, soup: BeautifulSoup) -> list[JobListing]:
        jobs = []

        for link in soup.select("a[data-jobid]"):
            try:
                job = self._parse_job(link, soup)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[workatastartup] Failed to parse job: {e}")
                continue

        return jobs

    def _parse_job(self, link, soup: BeautifulSoup) -> JobListing | None:
        title = link.get_text(strip=True)
        if not self._matches_role(title):
            return None

        href = link.get("href", "")
        if href and not href.startswith("http"):
            url = f"https://www.workatastartup.com{href}"
        else:
            url = href

        # Find the parent container for this job to get company info
        parent = link.find_parent("div", class_="company-details")
        if not parent:
            # Try broader parent search
            parent = link.find_parent("div")

        company = ""
        location = ""

        if parent:
            # Company name: span.font-bold inside div.company-details
            company_el = parent.select_one("span.font-bold")
            if company_el:
                company = self._clean_company(company_el.get_text(strip=True))

            # Location from job details paragraph
            details_p = parent.select_one("p.job-details")
            if details_p:
                spans = details_p.find_all("span")
                if len(spans) >= 2:
                    location = spans[1].get_text(strip=True)

        is_remote = "remote" in location.lower() if location else False

        return JobListing(
            title=title,
            company=company,
            url=url,
            source=self.name,
            location=location,
            is_remote=is_remote,
            posted_date=datetime.now(),
        )

    def _clean_company(self, name: str) -> str:
        """Strip YC batch suffix like '(W25)' or '(S24)'."""
        return re.sub(r"\s*\([WS]\d{2}\)\s*$", "", name).strip()

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)
