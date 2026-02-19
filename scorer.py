import config as config
from models import JobListing
from user_profile import get_profile


def rule_based_score(job: JobListing) -> float:
    """Score 0-50 based on hard criteria. Fast, no API cost."""
    score = 0.0
    p = get_profile()

    title_lower = job.title.lower()
    desc_lower = job.description.lower()

    # Title match (0-15 points)
    primary_titles = [t.lower() for t in p.get("scoring", {}).get("primary_role_tags", [])]
    secondary_titles = [t.lower() for t in p.get("scoring", {}).get("secondary_role_tags", [])]
    if any(t in title_lower for t in primary_titles):
        score += 15
    elif any(t in title_lower for t in secondary_titles):
        score += 10
    else:
        score += 5

    # Priority company (0-10 points)
    if any(c.lower() in job.company.lower() for c in config.PRIORITY_COMPANIES):
        score += 10

    # Industry match (0-10 points)
    industry_keywords = [t.lower() for t in p["industry_tags"]]
    matches = sum(1 for kw in industry_keywords if kw in desc_lower)
    score += min(matches * 2.5, 10)

    # Salary range (0-10 points)
    salary_target = p["salary_range"]["min"]
    salary_acceptable = int(salary_target * 0.85)
    if job.salary_min >= salary_target:
        score += 10
    elif job.salary_min >= salary_acceptable:
        score += 5

    # Experience alignment signals (0-5 points)
    alignment_keywords = [s.lower() for s in p.get("skills", [])]
    alignment = sum(1 for kw in alignment_keywords if kw in desc_lower)
    score += min(alignment, 5)

    return score
