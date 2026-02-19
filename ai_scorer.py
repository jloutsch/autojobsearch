import json
import logging
import os
import string
from urllib.parse import urlparse

import requests

from models import JobListing
from user_profile import get_profile

logger = logging.getLogger(__name__)

_raw_ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_parsed = urlparse(_raw_ollama_url)
_allowed_hosts = {"localhost", "127.0.0.1", "host.docker.internal"}
if _parsed.scheme not in ("http", "https") or _parsed.hostname not in _allowed_hosts:
    logger.warning(
        f"OLLAMA_URL '{_raw_ollama_url}' is not a trusted local address — "
        f"falling back to http://localhost:11434"
    )
    OLLAMA_URL = "http://localhost:11434"
else:
    OLLAMA_URL = _raw_ollama_url.rstrip("/")

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")

DEFAULT_PROMPT_TEMPLATE = (
    "Score this job listing's fit for the candidate below.\n"
    "Return ONLY valid JSON with these fields:\n"
    "- fit_score: integer 0-50\n"
    "- summary: string, 2 sentences max, what makes this role interesting\n"
    "- key_matches: list of 2-3 strongest qualification matches\n"
    "- gaps: list of any notable skill gaps\n"
    '- priority: "high", "medium", or "low"\n'
    "\n"
    "CANDIDATE:\n"
    "$resume_summary\n"
    "\n"
    "JOB LISTING:\n"
    "Title: $title\n"
    "Company: $company\n"
    "Description: $description\n"
    "Salary: $salary_min\u2013$salary_max\n"
    "Location: $location"
)


def _ollama_available() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL not in models:
            logger.warning(
                f"Ollama model '{OLLAMA_MODEL}' not found. "
                f"Available: {', '.join(models)}"
            )
            return False
        return True
    except requests.RequestException:
        return False


def ai_score(job: JobListing) -> dict:
    """Use Ollama to score job fit and generate a summary."""
    p = get_profile()
    raw_template = p.get("ai_prompt_template") or DEFAULT_PROMPT_TEMPLATE
    try:
        tmpl = string.Template(raw_template)
        prompt = tmpl.safe_substitute(
            resume_summary=p["resume_summary"],
            title=job.title,
            company=job.company,
            description=job.description[:3000],
            salary_min=f"${job.salary_min:,}",
            salary_max=f"${job.salary_max:,}",
            location=job.location,
        )
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid prompt template, using default: {e}")
        tmpl = string.Template(DEFAULT_PROMPT_TEMPLATE)
        prompt = tmpl.safe_substitute(
            resume_summary=p["resume_summary"],
            title=job.title,
            company=job.company,
            description=job.description[:3000],
            salary_min=f"${job.salary_min:,}",
            salary_max=f"${job.salary_max:,}",
            location=job.location,
        )

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json()["message"]["content"].strip()

    try:
        # Handle possible markdown code block wrapping
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        # Validate expected fields
        result.setdefault("fit_score", 0)
        result.setdefault("summary", "")
        result.setdefault("key_matches", [])
        result.setdefault("gaps", [])
        result.setdefault("priority", "low")
        # Clamp fit_score to 0-50
        result["fit_score"] = max(0, min(50, int(result["fit_score"])))
        return result
    except (json.JSONDecodeError, IndexError, ValueError) as e:
        logger.warning(f"Failed to parse Ollama response for {job.title}: {e}")
        return {"fit_score": 0, "summary": "", "key_matches": [], "gaps": [], "priority": "low"}


def score_top_jobs(
    jobs: list[JobListing],
    rule_scores: list[float],
    top_n: int = 15,
) -> list[dict]:
    """AI-score the top N jobs by rule-based score. Returns list of AI result dicts."""
    if not _ollama_available():
        logger.warning(f"Ollama not available at {OLLAMA_URL} — skipping AI scoring")
        return [None] * len(jobs)

    logger.info(f"AI scoring with Ollama model: {OLLAMA_MODEL}")

    # Pair jobs with their original index and rule scores, then sort by score
    indexed = sorted(
        enumerate(zip(jobs, rule_scores)),
        key=lambda x: x[1][1],
        reverse=True,
    )

    results = {}
    for rank, (orig_idx, (job, _score)) in enumerate(indexed[:top_n]):
        try:
            result = ai_score(job)
            results[orig_idx] = result
            logger.info(
                f"  AI scored [{rank+1}/{min(top_n, len(indexed))}]: "
                f"{job.title} @ {job.company} -> {result.get('fit_score', 0)}/50 "
                f"({result.get('priority', 'low')})"
            )
        except Exception as e:
            logger.warning(f"  AI scoring failed for {job.title}: {e}")
            results[orig_idx] = None

    # Return results in original order, None for jobs not scored
    return [results.get(i) for i in range(len(jobs))]
