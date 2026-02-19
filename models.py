from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobListing:
    title: str
    company: str
    url: str
    source: str  # "greenhouse", "remoteok", "builtin", etc.
    description: str = ""
    salary_min: int = 0
    salary_max: int = 0
    location: str = ""
    is_remote: bool = False
    posted_date: datetime = field(default_factory=datetime.now)
    raw_data: dict = field(default_factory=dict)
