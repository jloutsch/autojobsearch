import logging
from abc import ABC, abstractmethod

from models import JobListing

logger = logging.getLogger(__name__)


class BaseSource(ABC):
    """Abstract base class for all job sources."""

    name: str = "base"

    @abstractmethod
    def collect(self) -> list[JobListing]:
        """Fetch job listings from this source. Returns list of JobListing."""
        ...

    def safe_collect(self) -> list[JobListing]:
        """Collect with error handling so one source failure doesn't kill the pipeline."""
        try:
            jobs = self.collect()
            logger.info(f"[{self.name}] Collected {len(jobs)} listings")
            return jobs
        except Exception as e:
            logger.error(f"[{self.name}] Failed to collect: {e}")
            return []
