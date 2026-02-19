# Automated Daily Job Search System — Technical Blueprint

**Author:** Claude
**Date:** February 17, 2026
**Status:** Ready to Build

---

## Executive Summary

This document is a step-by-step construction plan for a fully automated system that discovers, scores, and delivers relevant Customer Success Manager, Technical Account Manager, and adjacent roles to your inbox every weekday at 8:00 AM EST. The system runs on GitHub Actions (free tier), uses Python for scraping and filtering, the Anthropic API for intelligent scoring, and delivers results via email.

**Estimated build time:** 3–4 Claude sessions
**Monthly cost:** $0–5 (GitHub Actions free tier + minimal Anthropic API usage)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   GitHub Actions (Cron)                   │
│              Runs M–F at 8:00 AM EST (13:00 UTC)         │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              Phase 1: COLLECT                             │
│                                                          │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │LinkedIn │ │ Indeed  │ │Glassdoor │ │BuiltIn/Lever/│  │
│  │  (RSS)  │ │  (RSS)  │ │  (API)   │ │Greenhouse API│  │
│  └────┬────┘ └────┬────┘ └────┬─────┘ └──────┬───────┘  │
│       └───────────┴───────────┴──────────────┘           │
│                        │                                 │
│                        ▼                                 │
│              Raw Job Listings (JSON)                      │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              Phase 2: FILTER & DEDUPLICATE                │
│                                                          │
│  • Remove duplicates (fuzzy title + company match)       │
│  • Apply hard filters (remote, salary, full-time)        │
│  • Check against "already seen" database (SQLite)        │
│  • Normalize titles to role categories                   │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              Phase 3: SCORE & RANK                        │
│                                                          │
│  ┌──────────────────┐  ┌───────────────────────────────┐ │
│  │ Rule-Based Score  │  │  Anthropic API (Claude Haiku) │ │
│  │ (fast, cheap)     │  │  (detailed fit analysis)      │ │
│  │                   │  │                               │ │
│  │ • Title match     │  │ • Compare JD to resume        │ │
│  │ • Company match   │  │ • Score 1–10 fit              │ │
│  │ • Industry match  │  │ • Generate 2-line summary     │ │
│  │ • Salary range    │  │ • Flag key requirements       │ │
│  │ • Remote flag     │  │ • Note skill gaps             │ │
│  └────────┬─────────┘  └──────────────┬────────────────┘ │
│           └──────────┬────────────────┘                   │
│                      ▼                                    │
│            Composite Score (0–100)                        │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              Phase 4: DELIVER                             │
│                                                          │
│  ┌───────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │  HTML Email    │  │  Markdown  │  │  Google Sheet  │  │
│  │  (SendGrid /  │  │  (GitHub   │  │  (append row   │  │
│  │   Gmail SMTP) │  │   commit)  │  │   via API)     │  │
│  └───────────────┘  └────────────┘  └────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## Phase 1: Data Collection

### 1A. Source: Job Board RSS & API Feeds

Each source gets its own Python module in `sources/`. All modules return a standardized `JobListing` dataclass.

```python
# models.py — Shared data model
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class JobListing:
    title: str
    company: str
    url: str
    source: str  # "linkedin", "indeed", "builtin", etc.
    description: str = ""
    salary_min: int = 0
    salary_max: int = 0
    location: str = ""
    is_remote: bool = False
    posted_date: datetime = field(default_factory=datetime.now)
    raw_data: dict = field(default_factory=dict)
```

### Source Modules to Build

| Source | Method | Module | Notes |
|--------|--------|--------|-------|
| **LinkedIn** | RSS feed via Google Alerts + LinkedIn Jobs URL scraping | `sources/linkedin.py` | Set up Google Alerts for each role title; parse RSS XML |
| **Indeed** | RSS feed (indeed.com/rss) | `sources/indeed.py` | Indeed provides RSS endpoints with query params |
| **Glassdoor** | Web scraping (requests + BeautifulSoup) | `sources/glassdoor.py` | Scrape search results pages |
| **BuiltIn** | API / scraping | `sources/builtin.py` | BuiltIn has a fairly scrapable structure |
| **Wellfound** | GraphQL API | `sources/wellfound.py` | AngelList/Wellfound exposes a public GraphQL endpoint |
| **Lever/Greenhouse** | Direct ATS APIs | `sources/ats_direct.py` | Hit career pages for priority companies directly |
| **RemoteOK** | JSON API | `sources/remoteok.py` | remoteok.com/api — free, returns JSON |
| **We Work Remotely** | RSS | `sources/weworkremotely.py` | Standard RSS feeds by category |
| **Company Career Pages** | Targeted scraping | `sources/priority_companies.py` | SentinelOne, Huntress, CrowdStrike, Datadog |

### 1B. Search Queries per Source

Each source should run **multiple queries** to cover the full role family:

```python
# config.py
SEARCH_QUERIES = [
    "Customer Success Manager",
    "Technical Account Manager",
    "Solutions Engineer",
    "Client Success Manager",
    "Customer Experience Manager",
    "Implementation Manager",
    "Enterprise Support Manager",
    "Customer Operations Manager",
    "Strategic Account Manager",
    "Partner Success Manager",
    "Technical Customer Success Manager",
]

PRIORITY_COMPANIES = [
    "SentinelOne",
    "Huntress",
    "CrowdStrike",
    "Datadog",
]

INDUSTRIES = [
    "cybersecurity",
    "saas",
    "healthcare IT",
    "medical imaging",
    "devops",
    "infrastructure",
]

SALARY_MIN = 130000
SALARY_MAX = 150000  # soft cap — include roles above this too
WORK_TYPE = "remote"
EMPLOYMENT_TYPE = "full-time"
TIMEZONE = "US/Eastern"
```

### 1C. Priority Company Direct Scraping

For the four priority companies, hit their ATS career pages directly:

```python
# sources/priority_companies.py
COMPANY_CAREER_URLS = {
    "SentinelOne": {
        "type": "greenhouse",
        "url": "https://boards-api.greenhouse.io/v1/boards/sentinelone/jobs"
    },
    "Huntress": {
        "type": "greenhouse",
        "url": "https://boards-api.greenhouse.io/v1/boards/huntress/jobs"
    },
    "CrowdStrike": {
        "type": "workday",  # requires different scraping approach
        "url": "https://crowdstrike.wd5.myworkdaysite.com/en-US/crowdstrikecareers"
    },
    "Datadog": {
        "type": "greenhouse",
        "url": "https://boards-api.greenhouse.io/v1/boards/datadog/jobs"
    },
}
```

**Greenhouse API** is publicly accessible and returns JSON — no auth required. This is the easiest source to start with and covers 3 of 4 priority companies.

---

## Phase 2: Filter & Deduplicate

### 2A. Hard Filters

```python
# filters.py
import re
from models import JobListing

def passes_hard_filters(job: JobListing) -> bool:
    """Reject listings that clearly don't match."""

    title_lower = job.title.lower()
    desc_lower = job.description.lower()

    # Must be remote (or at least not explicitly on-site only)
    if not job.is_remote:
        on_site_signals = ["on-site only", "in-office", "no remote", "must be located in"]
        if any(signal in desc_lower for signal in on_site_signals):
            return False

    # Must match at least one target role family keyword
    role_keywords = [
        "customer success", "technical account", "solutions engineer",
        "client success", "customer experience", "implementation",
        "enterprise support", "customer operations", "strategic account",
        "partner success", "customer engineer",
    ]
    if not any(kw in title_lower for kw in role_keywords):
        return False

    # Reject junior roles
    junior_signals = ["junior", "associate", "entry level", "intern"]
    if any(signal in title_lower for signal in junior_signals):
        return False

    # Salary floor check (if salary data is available)
    if job.salary_max > 0 and job.salary_max < 100000:
        return False

    return True
```

### 2B. Deduplication

Use fuzzy matching to catch the same role posted across multiple boards:

```python
# dedup.py
from thefuzz import fuzz
import sqlite3

def is_duplicate(job: JobListing, seen_jobs: list[JobListing], threshold=85) -> bool:
    """Fuzzy match on title + company to catch cross-posted roles."""
    for seen in seen_jobs:
        title_score = fuzz.token_sort_ratio(job.title, seen.title)
        company_score = fuzz.token_sort_ratio(job.company, seen.company)
        if title_score > threshold and company_score > threshold:
            return True
    return False

def was_previously_sent(job: JobListing, db_path="seen_jobs.db") -> bool:
    """Check SQLite database of previously delivered listings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE url = ? OR "
        "(company = ? AND title_hash = ?)",
        (job.url, job.company, hash(job.title.lower().strip()))
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None
```

### 2C. SQLite "Already Seen" Database

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS seen_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    title TEXT,
    title_hash INTEGER,
    company TEXT,
    source TEXT,
    first_seen DATE DEFAULT CURRENT_DATE,
    score REAL DEFAULT 0,
    status TEXT DEFAULT 'new'  -- new, applied, skipped, interviewing
);
```

This database persists as a GitHub Actions artifact or in a private gist/repo branch.

---

## Phase 3: Score & Rank

### 3A. Rule-Based Scoring (Fast, Free)

```python
# scorer.py

def rule_based_score(job: JobListing) -> float:
    """Score 0-50 based on hard criteria. Fast, no API cost."""
    score = 0.0

    title_lower = job.title.lower()
    desc_lower = job.description.lower()

    # Title match (0–15 points)
    primary_titles = ["customer success manager", "technical account manager"]
    secondary_titles = ["solutions engineer", "implementation manager",
                        "enterprise support manager", "strategic account manager"]
    if any(t in title_lower for t in primary_titles):
        score += 15
    elif any(t in title_lower for t in secondary_titles):
        score += 10
    else:
        score += 5

    # Priority company (0–10 points)
    priority = ["sentinelone", "huntress", "crowdstrike", "datadog"]
    if any(c in job.company.lower() for c in priority):
        score += 10

    # Industry match (0–10 points)
    industry_keywords = [
        "cybersecurity", "security", "healthcare", "health tech",
        "medical", "imaging", "saas", "devops", "infrastructure",
        "observability", "monitoring"
    ]
    matches = sum(1 for kw in industry_keywords if kw in desc_lower)
    score += min(matches * 2.5, 10)

    # Salary range (0–10 points)
    if job.salary_min >= 130000:
        score += 10
    elif job.salary_min >= 110000:
        score += 5

    # Experience alignment signals (0–5 points)
    alignment_keywords = [
        "enterprise", "technical", "cross-functional",
        "onboarding", "retention", "expansion",
        "saas", "b2b", "healthcare"
    ]
    alignment = sum(1 for kw in alignment_keywords if kw in desc_lower)
    score += min(alignment, 5)

    return score
```

### 3B. AI Scoring with Anthropic API (Detailed Fit Analysis)

Only send the **top 15 listings** from rule-based scoring to the API to keep costs minimal.

```python
# ai_scorer.py
import anthropic

RESUME_SUMMARY = """
# Loaded from profile.json at runtime — see profile.json for configuration.
"""

def ai_score(job: JobListing, client: anthropic.Anthropic) -> dict:
    """Use Claude Haiku to score fit and generate a summary."""

    prompt = f"""Score this job listing's fit for the candidate below.
Return ONLY valid JSON with these fields:
- fit_score: integer 0-50
- summary: string, 2 sentences max, what makes this role interesting
- key_matches: list of 2-3 strongest qualification matches
- gaps: list of any notable skill gaps
- priority: "high", "medium", or "low"

CANDIDATE:
{RESUME_SUMMARY}

JOB LISTING:
Title: {job.title}
Company: {job.company}
Description: {job.description[:3000]}
Salary: ${job.salary_min:,}–${job.salary_max:,}
"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    return json.loads(response.content[0].text)
```

### 3C. Composite Scoring

```python
def composite_score(rule_score: float, ai_result: dict) -> float:
    """Combine rule-based (0–50) and AI (0–50) scores into 0–100."""
    return rule_score + ai_result.get("fit_score", 0)
```

---

## Phase 4: Delivery

### 4A. HTML Email via Gmail SMTP (Free)

```python
# deliver.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date

def send_daily_digest(ranked_jobs: list[dict], recipient="user@example.com"):
    """Send HTML email digest of top job matches."""

    today = date.today().strftime("%A, %B %d, %Y")
    high_priority = [j for j in ranked_jobs if j["priority"] == "high"]
    medium_priority = [j for j in ranked_jobs if j["priority"] == "medium"]

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
        <h2 style="color: #2563eb;">🔍 Daily Job Digest — {today}</h2>
        <p style="color: #666;">Found {len(ranked_jobs)} new matches
        ({len(high_priority)} high priority)</p>

        <h3 style="color: #dc2626;">🔴 High Priority ({len(high_priority)})</h3>
        {"".join(_render_job_card(j) for j in high_priority)}

        <h3 style="color: #f59e0b;">🟡 Worth a Look ({len(medium_priority)})</h3>
        {"".join(_render_job_card(j) for j in medium_priority)}

        <hr>
        <p style="color: #999; font-size: 12px;">
            Automated by your Job Search Pipeline •
            <a href="#">Edit filters</a>
        </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 {len(high_priority)} High-Priority Roles — {today}"
    msg["From"] = "job-search-bot@gmail.com"
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("your-bot-email@gmail.com", "app-password-here")
        server.send_message(msg)
```

### 4B. Markdown Commit to Repo (Searchable Archive)

```python
# archive.py
def save_daily_report(ranked_jobs: list[dict], output_dir="reports/"):
    """Write daily report as markdown for GitHub archive."""
    today = date.today().strftime("%Y-%m-%d")
    filename = f"{output_dir}/{today}.md"

    lines = [f"# Job Search Report — {today}\n"]
    for job in ranked_jobs:
        lines.append(f"## [{job['title']}]({job['url']}) — {job['company']}")
        lines.append(f"**Score:** {job['score']}/100 | **Priority:** {job['priority']}")
        lines.append(f"{job['summary']}\n")

    with open(filename, "w") as f:
        f.write("\n".join(lines))
```

---

## GitHub Actions Workflow

```yaml
# .github/workflows/daily-job-search.yml
name: Daily Job Search

on:
  schedule:
    # 8:00 AM EST = 13:00 UTC (standard time)
    # 8:00 AM EDT = 12:00 UTC (daylight saving)
    # Use 13:00 UTC and accept ~1hr shift during DST
    - cron: '0 13 * * 1-5'  # Weekdays only
  workflow_dispatch: # Allow manual trigger for testing

permissions:
  contents: write  # For committing daily reports

jobs:
  search:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Download previous seen_jobs database
        uses: actions/download-artifact@v4
        with:
          name: seen-jobs-db
          path: .
        continue-on-error: true  # First run won't have this

      - name: Run job search pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GMAIL_SENDER: ${{ secrets.GMAIL_SENDER }}
        run: python main.py

      - name: Upload updated seen_jobs database
        uses: actions/upload-artifact@v4
        with:
          name: seen-jobs-db
          path: seen_jobs.db
          retention-days: 90

      - name: Commit daily report
        run: |
          git config user.name "Job Search Bot"
          git config user.email "bot@noreply.github.com"
          git add reports/
          git diff --staged --quiet || git commit -m "📋 Daily job report $(date +%Y-%m-%d)"
          git push
```

---

## Repository Structure

```
job-search-bot/
├── .github/
│   └── workflows/
│       └── daily-job-search.yml
├── sources/
│   ├── __init__.py
│   ├── base.py              # Abstract source class
│   ├── greenhouse.py        # Greenhouse ATS API (covers 3 priority companies)
│   ├── indeed_rss.py        # Indeed RSS feeds
│   ├── linkedin_alerts.py   # Google Alerts RSS for LinkedIn
│   ├── builtin.py           # BuiltIn scraper
│   ├── remoteok.py          # RemoteOK JSON API
│   ├── weworkremotely.py    # WWR RSS
│   └── wellfound.py         # Wellfound GraphQL
├── reports/                  # Daily markdown reports (git committed)
│   └── 2026-02-18.md
├── config.py                 # All search criteria, queries, company lists
├── models.py                 # JobListing dataclass
├── filters.py                # Hard filters + remote detection
├── dedup.py                  # Fuzzy matching + SQLite seen-jobs
├── scorer.py                 # Rule-based scoring
├── ai_scorer.py              # Anthropic API fit scoring
├── deliver.py                # Email delivery (Gmail SMTP)
├── archive.py                # Markdown report generation
├── main.py                   # Pipeline orchestrator
├── requirements.txt
├── schema.sql
└── README.md
```

---

## Build Order (Session-by-Session)

### Session 1 — Foundation + Easiest Sources

1. Set up repo structure, `config.py`, `models.py`, `schema.sql`
2. Build `sources/greenhouse.py` (covers SentinelOne, Huntress, Datadog — free JSON API)
3. Build `sources/remoteok.py` (free JSON API, simplest source)
4. Build `sources/builtin.py` (good remote/salary filters, scrapable structure)
5. Build `filters.py` and `dedup.py`
6. Build `scorer.py` (rule-based only)
7. Build `archive.py` (markdown output)
8. Test end-to-end locally with 3 sources

### Session 2 — More Sources + AI Scoring

1. Build `sources/indeed_rss.py`
2. Build `sources/weworkremotely.py`
3. Build `ai_scorer.py` (Anthropic API integration)
4. Test composite scoring pipeline
5. Build `deliver.py` (email delivery)

### Session 3 — Full Pipeline + Deployment

1. Build `sources/wellfound.py`
2. Build `sources/linkedin_alerts.py`
3. Handle CrowdStrike (Workday scraping — trickiest source)
4. Create GitHub Actions workflow
5. Set up secrets (API keys, Gmail app password)
6. Deploy and test with manual trigger
7. Verify cron schedule fires correctly

### Session 4 — Polish + Enhancements

1. Add Google Sheets integration for tracking (optional)
2. Build simple web dashboard with daily results (optional)
3. Add "Apply" status tracking (link back from email)
4. Tune scoring weights based on first week of results
5. Add Slack notification as secondary delivery channel (optional)

---

## Configuration & Secrets

### GitHub Secrets Required

| Secret | Purpose | How to Get |
|--------|---------|------------|
| `ANTHROPIC_API_KEY` | AI scoring via Claude Haiku | console.anthropic.com → API Keys |
| `GMAIL_APP_PASSWORD` | Email delivery | Google Account → Security → App Passwords |
| `GMAIL_SENDER` | Sender email address | Your Gmail or a dedicated bot account |

### Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| GitHub Actions | Free (2,000 mins/month on free tier; ~15 min/day × 22 days = 330 mins) |
| Anthropic API (Haiku) | ~$1–3 (15 listings × 22 days × ~500 tokens = ~165K tokens) |
| Gmail SMTP | Free |
| **Total** | **~$1–3/month** |

---

## Sample Email Output

```
Subject: 🔍 3 High-Priority Roles — Tuesday, February 18, 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 HIGH PRIORITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Technical Account Manager — SentinelOne
Score: 92/100 | $135K–$155K | Remote
"SentinelOne's TAM role maps directly to your healthcare
enterprise support background. Strong match on infrastructure
troubleshooting and cross-functional collaboration."
Matches: enterprise support, technical depth, healthcare customers
Gaps: EDR/XDR product knowledge (learnable)
→ Apply: [link]

Customer Success Manager — Huntress
Score: 87/100 | $130K–$145K | Remote
"Huntress focuses on SMB cybersecurity — your experience
supporting resource-constrained teams is a direct parallel."
Matches: small team empathy, automation expertise, B2B SaaS
Gaps: cybersecurity domain (adjacent to your healthcare security work)
→ Apply: [link]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟡 WORTH A LOOK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Implementation Manager — Datadog
Score: 74/100 | $140K–$160K | Remote
...
```

---

## Extensibility Roadmap

Once the core pipeline is stable, these enhancements can be layered on:

**Near-term (weeks 2–4):**
- Auto-generate a draft cover letter for each high-priority role using Claude + your cover letter instructions
- Attach cover letter PDFs to the daily email
- Add a "one-click apply" workflow via saved resume + cover letter

**Medium-term (months 2–3):**
- Build a Streamlit dashboard for browsing/filtering historical results
- Add company culture scoring using Glassdoor/Blind data
- Track application funnel (applied → phone screen → interview → offer)

**Long-term:**
- Train a lightweight classifier on your "applied" vs "skipped" history to improve scoring
- Add salary benchmarking data from levels.fyi API
- Expand to international remote roles (Ireland, Canada — aligned with relocation research)

---

## Key Technical Decisions & Rationale

**Why GitHub Actions over AWS Lambda?**
Free tier is more than enough, no infrastructure to manage, built-in secrets management, and the daily report archive lives in the same repo. Zero ops burden.

**Why Claude Haiku for scoring?**
Cheapest model in the Anthropic lineup while still excellent at structured JSON output and resume-to-JD comparison. At ~$0.001 per scoring call, you could score 1,000 listings for $1.

**Why SQLite for the "seen" database?**
Persists as a GitHub Actions artifact, zero infrastructure, and the dataset never grows beyond a few thousand rows. A full database service would be overkill.

**Why Gmail SMTP over SendGrid?**
You're the only recipient. Gmail's free SMTP with app passwords handles single-recipient delivery perfectly. No vendor signup required.

**Why start with Greenhouse API?**
Three of your four priority companies (SentinelOne, Huntress, Datadog) use Greenhouse. The API is public, unauthenticated, returns clean JSON, and is the most reliable source to build first. Immediate value on day one.
