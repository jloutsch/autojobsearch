"""Indeed job source via Chrome browser.

Indeed uses Cloudflare bot protection, requiring a real Chrome browser.
Job data is embedded as JSON in a JavaScript variable within the page source.
"""

import json
import logging
import re
from datetime import datetime

import config
from models import JobListing
from sources.chrome_base import ChromeBrowserSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.indeed.com/jobs"
MAX_PAGES = 3
RESULTS_PER_PAGE = 10


class IndeedSource(ChromeBrowserSource):
    name = "indeed"

    def collect(self) -> list[JobListing]:
        all_jobs = []
        seen_urls = set()

        for query in config.SEARCH_QUERIES:
            try:
                jobs = self._search(query)
            except Exception as e:
                logger.warning(f"[indeed] Failed query '{query}': {e}")
                continue
            for job in jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        return all_jobs

    def _search(self, query: str) -> list[JobListing]:
        jobs = []

        for page in range(MAX_PAGES):
            start = page * RESULTS_PER_PAGE
            url = f"{SEARCH_URL}?q={query.replace(' ', '+')}&l=Remote&start={start}&filter=0"

            # Extra delay for Indeed — aggressive bot detection
            self._navigate(url, wait_range=(3.0, 5.0))

            page_jobs = self._extract_jobs()
            if not page_jobs:
                break

            jobs.extend(page_jobs)

        return jobs

    def _extract_jobs(self) -> list[JobListing]:
        html = self._get_page_html()

        # Indeed embeds job data in a JS variable
        match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.+?\});',
            html,
            re.DOTALL,
        )
        if not match:
            # Check if we hit a CAPTCHA or block page
            if "captcha" in html.lower() or "unusual traffic" in html.lower():
                logger.warning("[indeed] Hit CAPTCHA/block page — stopping")
            else:
                logger.warning("[indeed] Could not find job card data in page")
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("[indeed] Failed to parse embedded JSON")
            return []

        results = (
            data.get("metaData", {})
            .get("mosaicProviderJobCardsModel", {})
            .get("results", [])
        )

        jobs = []
        for item in results:
            title = item.get("title", "")
            if not self._matches_role(title):
                continue

            company = item.get("company", "")
            job_key = item.get("jobkey", "")
            job_url = f"https://www.indeed.com/viewjob?jk={job_key}" if job_key else ""

            location = item.get("formattedLocation", "")
            is_remote = "remote" in location.lower() if location else False

            # Salary extraction
            salary_snippet = item.get("salarySnippet", {}) or {}
            salary_text = salary_snippet.get("text", "") or ""
            salary_min, salary_max = self._parse_salary(salary_text)

            # Description snippet
            description = ""
            snippets = item.get("snippets", []) or item.get("jobSnippet", {})
            if isinstance(snippets, list):
                description = " ".join(snippets)
            elif isinstance(snippets, dict):
                description = snippets.get("text", "")

            # Date
            posted = self._parse_relative_date(item.get("formattedRelativeTime", ""))

            job = JobListing(
                title=title,
                company=company,
                url=job_url,
                source=self.name,
                description=description,
                salary_min=salary_min,
                salary_max=salary_max,
                location=location,
                is_remote=is_remote,
                posted_date=posted,
            )
            jobs.append(job)

        return jobs

    def _matches_role(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in config.ROLE_KEYWORDS)

    def _parse_salary(self, text: str) -> tuple[int, int]:
        if not text:
            return 0, 0
        range_match = re.search(
            r"\$\s*([\d,]+)\s*[kK]?\s*[-\u2013to]+\s*\$?\s*([\d,]+)\s*[kK]?",
            text,
        )
        if range_match:
            low = int(range_match.group(1).replace(",", ""))
            high = int(range_match.group(2).replace(",", ""))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            return low, high
        return 0, 0

    def _parse_relative_date(self, text: str) -> datetime:
        """Parse Indeed's relative dates like '3 days ago', 'Just posted'."""
        if not text:
            return datetime.now()
        text_lower = text.lower()
        if "just" in text_lower or "today" in text_lower:
            return datetime.now()
        days_match = re.search(r"(\d+)\s*day", text_lower)
        if days_match:
            from datetime import timedelta
            days = int(days_match.group(1))
            return datetime.now() - timedelta(days=days)
        return datetime.now()
