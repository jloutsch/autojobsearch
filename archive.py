import os
import re
from datetime import date, datetime, timezone

from sanitize import safe_url

_MD_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _md_text(value: str) -> str:
    """Make scraped text safe to inline in markdown.

    Collapses newlines so a title can't forge headings or list items, and escapes
    the bracket characters that would otherwise let it break out of a link label
    and write its own markup.
    """
    cleaned = _MD_CONTROL.sub(" ", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _md_url(raw: str) -> str:
    """Scheme-check a URL and neutralise the parens that delimit a markdown link."""
    return safe_url(raw).replace("(", "%28").replace(")", "%29")


def save_daily_report(ranked_jobs: list[dict], output_dir: str = "reports/") -> str:
    """Write daily report as markdown for GitHub archive. Returns the filename."""
    os.makedirs(output_dir, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    filename = os.path.join(output_dir, f"{today}.md")

    lines = [f"# Job Search Report — {today}\n"]

    if not ranked_jobs:
        lines.append("No new matching jobs found today.\n")
    else:
        high = [j for j in ranked_jobs if j.get("priority") == "high"]
        medium = [j for j in ranked_jobs if j.get("priority") == "medium"]
        low = [j for j in ranked_jobs if j.get("priority") == "low"]

        lines.append(f"**{len(ranked_jobs)} new matches** — "
                      f"{len(high)} high, {len(medium)} medium, {len(low)} low priority\n")

        if high:
            lines.append("## High Priority\n")
            for job in high:
                lines.extend(_render_job(job))

        if medium:
            lines.append("## Worth a Look\n")
            for job in medium:
                lines.extend(_render_job(job))

        if low:
            lines.append("## Other Matches\n")
            for job in low:
                lines.extend(_render_job(job))

    with open(filename, "w") as f:
        f.write("\n".join(lines))

    return filename


def _render_job(job: dict) -> list[str]:
    """Render a single job entry as markdown lines."""
    lines = []
    title = _md_text(job.get("title", "")) or "Unknown"
    company = _md_text(job.get("company", "")) or "Unknown"
    url = _md_url(job.get("url", ""))
    score = job.get("score", 0)
    source = _md_text(job.get("source", ""))

    lines.append(f"### [{title}]({url}) — {company}")
    lines.append(f"**Score:** {score:.0f}/100 | **Source:** {source}")

    if job.get("salary_min") or job.get("salary_max"):
        sal_min = job.get("salary_min", 0)
        sal_max = job.get("salary_max", 0)
        if sal_min and sal_max:
            lines.append(f"**Salary:** ${sal_min:,}–${sal_max:,}")
        elif sal_min:
            lines.append(f"**Salary:** ${sal_min:,}+")

    if job.get("posted_date"):
        lines.append(f"**Posted:** {_format_posted(job['posted_date'])}")

    if job.get("location"):
        lines.append(f"**Location:** {_md_text(job['location'])}")

    if job.get("summary"):
        lines.append(f"\n{_md_text(job['summary'])}")

    lines.append("")  # blank line between entries
    return lines


def _format_posted(posted_iso: str) -> str:
    """Format posted_date ISO string as human-readable age."""
    try:
        posted = datetime.fromisoformat(posted_iso)
        now = datetime.now(timezone.utc)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        days = (now - posted).days
        if days == 0:
            return "Today"
        elif days == 1:
            return "Yesterday"
        elif days < 7:
            return f"{days} days ago"
        else:
            return posted.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return posted_iso
