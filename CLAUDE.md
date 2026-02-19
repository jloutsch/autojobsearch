# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated daily job search pipeline that discovers, scores, and delivers relevant Customer Success Manager / Technical Account Manager roles. Runs on GitHub Actions (free tier), uses Python for scraping/filtering, a local Ollama model for intelligent scoring, and outputs a static HTML dashboard.

The full technical blueprint is in `automated-job-search-plan.md`.

## Build Commands

```bash
python3 -m venv .venv && source .venv/bin/activate   # Create/activate virtualenv
pip install -r requirements.txt                        # Install dependencies
python main.py                                         # Run full pipeline locally
```

Requires Ollama running locally for AI scoring (`ollama serve`). Pipeline still works without it — just skips AI scoring.

## Architecture

Four-phase pipeline orchestrated by `main.py`:

1. **COLLECT** — Source modules in `sources/` each return standardized `JobListing` dataclasses (defined in `models.py`). Each source extends `BaseSource` from `sources/base.py` with a `collect()` method. The `safe_collect()` wrapper catches exceptions so one source failure doesn't kill the pipeline.
2. **FILTER & DEDUPLICATE** — Hard filters (remote, salary floor, role keyword match, reject junior) in `filters.py`. Fuzzy dedup via `thefuzz` in `dedup.py`. SQLite `seen_jobs.db` tracks previously delivered listings.
3. **SCORE & RANK** — Two-tier: rule-based scoring (0-50 points) in `scorer.py`, then top 15 sent to Ollama for AI fit scoring (0-50 points) in `ai_scorer.py`. Composite score is 0-100.
4. **DELIVER** — Static HTML dashboard (`dashboard.py`) + markdown archive (`archive.py`) committed to `reports/`.

## Active Sources

| Source | Module | Method | Notes |
|--------|--------|--------|-------|
| Greenhouse ATS | `sources/greenhouse.py` | JSON API | SentinelOne (`sentinellabs`), Huntress, Datadog — no auth |
| CrowdStrike | `sources/crowdstrike.py` | Workday POST API | `crowdstrike.wd5.myworkdayjobs.com` — no auth, 20 results/page max |
| RemoteOK | `sources/remoteok.py` | JSON API | All listings are remote; first element in response is metadata (skip it) |
| BuiltIn | `sources/builtin.py` | HTML scraping | Selectors: `div[data-id="job-card"]`, `a[data-id="job-card-title"]`, `a[data-id="company-title"]` |
| WeWorkRemotely | `sources/weworkremotely.py` | RSS/Atom XML | Title format is `Company: Job Title` — split on first colon |
| LinkedIn | `sources/linkedin_alerts.py` | Google Alerts RSS | Requires manual one-time feed setup; only includes jobs from last 24 hours |

**Not viable:** Indeed RSS (Cloudflare 403), Wellfound (Cloudflare + DataDome)

## AI Scoring (Ollama)

Uses a local Ollama model (default: `llama3.2:latest`) via the `/api/chat` endpoint with `format: "json"`. Configurable via environment variables:
- `OLLAMA_URL` — default `http://localhost:11434`
- `OLLAMA_MODEL` — default `llama3.2:latest`

Scores the top 15 rule-based results with fit analysis against the resume summary in `ai_scorer.py`. Gracefully skips if Ollama is unavailable.

## Key Configuration

- `config.py` — Search queries, priority companies, industries, salary range, Greenhouse board tokens, role keywords (all loaded from `profile.json`)
- `models.py` — `JobListing` dataclass shared across all modules
- `sources/linkedin_alerts.py:ALERT_FEED_URLS` — Google Alerts RSS feed URLs (must be added after manual creation)

## GitHub Actions

Workflow at `.github/workflows/daily-job-search.yml`. Cron runs weekdays at 13:00 UTC (8 AM EST). The `seen_jobs.db` SQLite database persists as a GitHub Actions artifact (90-day retention, overwritten each run). AI scoring is skipped in CI (no Ollama available) — uses rule-based scoring only.

## Graceful Degradation

AI scoring and the LinkedIn source skip gracefully when their dependencies aren't available. The pipeline always produces the markdown report and HTML dashboard.
