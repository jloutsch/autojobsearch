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
            # One failing role query must not discard the other's results.
            try:
                jobs = self._fetch_page(role)
            except Exception as e:
                logger.warning(f"[workatastartup] role '{role}' skipped: {e}")
                continue
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
                    "Chrome/120.0.0.0 Safari/537.36",
                    # Without an Accept header the site returns 406 Not Acceptable.
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[workatastartup] Fetch failed for role={role}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = self._parse_results(soup)
        if not results:
            # The /jobs page is now a client-rendered SPA (Algolia-backed): the
            # returned HTML has no a[data-jobid] anchors, so this scrape yields
            # nothing even on HTTP 200. Recovering this source requires querying
            # YC's Algolia API directly rather than scraping HTML. See TODO.
            logger.warning(
                "[workatastartup] 0 listings parsed (page is JS-rendered; "
                "needs Algolia API integration to return jobs)"
            )
        return results

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
