"""Remote.co job source via Chrome browser.

Remote.co blocks plain HTTP requests. Uses Chrome to render the search page
and extracts job listings from links in the rendered DOM.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

import config
from models import JobListing
from sources.chrome_base import ChromeBrowserSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://remote.co/remote-jobs/search"
MAX_PAGES = 3


class RemoteCoSource(ChromeBrowserSource):
    name = "remoteco"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for query in config.SEARCH_QUERIES:
            try:
                jobs = self._search(query)
            except Exception as e:
                logger.warning(f"[remoteco] Failed query '{query}': {e}")
                continue
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _search(self, query: str) -> list[JobListing]:
        jobs = []

        for page in range(1, MAX_PAGES + 1):
            url = f"{SEARCH_URL}?search_keywords={query.replace(' ', '+')}"
            if page > 1:
                url += f"&page={page}"

            self._navigate(url, wait_range=(2.0, 4.0))

            # Wait for JS to render job listings
            try:
                self._wait_for_selector("a[href*='/job-details/']", timeout=15000)
            except Exception:
                break

            page_jobs = self._extract_jobs()
            if not page_jobs:
                break
            jobs.extend(page_jobs)

        return jobs

    def _extract_jobs(self) -> list[JobListing]:
        html = self._get_page_html()
        soup = BeautifulSoup(html, "html.parser")

        jobs = []
        # Find all job detail links
        job_links = soup.select("a[href*='/job-details/']")

        for link in job_links:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = f"https://remote.co{href}"

            # Extract title from link text
            raw_text = link.get_text(strip=True)

            # Remote.co prepends "New!Today" or similar badges
            title = re.sub(r"^(New!?)?\s*(Today|Yesterday|\d+ days? ago)?\s*", "", raw_text).strip()
            if not title:
                continue

            if not self._matches_role(title):
                continue

            # Company isn't available in the search results list
            job = JobListing(
                title=title,
                company="",
                url=href,
                source=self.name,
                is_remote=True,
                posted_date=datetime.now(),
            )
            jobs.append(job)

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)
