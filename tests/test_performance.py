"""Performance and load tests for the job search pipeline components.

Tests response time and throughput of key functions under various loads:
- Dashboard HTML generation with large job lists
- Rule-based scoring throughput
- Hard filter throughput
- Dedup performance with large datasets
- Markdown report generation
- HTTP handler response times under concurrent load
"""

import http.server
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import HTTPServer

import pytest
import requests
from freezegun import freeze_time

from archive import save_daily_report
from dashboard import _format_age, _render_row, generate_dashboard
from dedup import init_db, is_duplicate
from filters import passes_hard_filters
from models import JobListing
from scorer import rule_based_score

pytestmark = pytest.mark.performance


def _make_job_listing(**overrides):
    """Create a JobListing with defaults."""
    defaults = {
        "title": "Customer Success Manager",
        "company": "TestCorp",
        "url": "https://example.com/job/1",
        "source": "test",
        "description": "A cybersecurity saas role with jira and docker experience. "
                       "Cloud infrastructure and devops knowledge required. "
                       "Experience with AWS, python, and sql preferred.",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote - US",
        "is_remote": True,
        "posted_date": datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return JobListing(**defaults)


def _make_job_dict(**overrides):
    """Create a job dict for dashboard/archive functions."""
    defaults = {
        "title": "Customer Success Manager",
        "company": "TestCorp",
        "url": "https://example.com/job/1",
        "source": "greenhouse",
        "score": 72,
        "priority": "high",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote - US",
        "posted_date": "2026-02-18T10:00:00+00:00",
        "description": "A cybersecurity SaaS role.",
        "summary": "Good fit for technical background.",
        "key_matches": ["cybersecurity"],
        "gaps": [],
    }
    defaults.update(overrides)
    return defaults


# ============================================================
# Rule-based scoring performance
# ============================================================


class TestScoringPerformance:
    """Benchmark rule_based_score throughput."""

    def test_score_single_job(self, benchmark):
        """Single job scoring should be fast."""
        job = _make_job_listing()
        result = benchmark(rule_based_score, job)
        assert isinstance(result, (int, float))

    def test_score_100_jobs(self, benchmark):
        """Score 100 jobs in batch."""
        jobs = [
            _make_job_listing(
                title=f"CSM {i}",
                url=f"https://example.com/{i}",
                company=f"Corp{i}",
            )
            for i in range(100)
        ]

        def score_all():
            return [rule_based_score(j) for j in jobs]

        results = benchmark(score_all)
        assert len(results) == 100

    def test_score_500_jobs(self, benchmark):
        """Score 500 jobs — typical large pipeline run."""
        jobs = [
            _make_job_listing(
                title=f"CSM {i}",
                url=f"https://example.com/{i}",
                company=f"Corp{i}",
            )
            for i in range(500)
        ]

        def score_all():
            return [rule_based_score(j) for j in jobs]

        results = benchmark(score_all)
        assert len(results) == 500


# ============================================================
# Filter performance
# ============================================================


class TestFilterPerformance:
    """Benchmark passes_hard_filters throughput."""

    def test_filter_single_job(self, benchmark):
        job = _make_job_listing()
        result = benchmark(passes_hard_filters, job)
        assert isinstance(result, bool)

    def test_filter_500_jobs(self, benchmark):
        """Filter 500 jobs through hard filters."""
        jobs = [
            _make_job_listing(
                title=f"CSM {i}",
                url=f"https://example.com/{i}",
            )
            for i in range(500)
        ]

        def filter_all():
            return [passes_hard_filters(j) for j in jobs]

        results = benchmark(filter_all)
        assert len(results) == 500


# ============================================================
# Dedup performance
# ============================================================


class TestDedupPerformance:
    """Benchmark deduplication with varying dataset sizes."""

    def test_dedup_100_unique_jobs(self, benchmark, tmp_path):
        """Dedup 100 unique jobs — no duplicates found."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        # Use highly distinct titles and companies to avoid fuzzy matching
        titles = [
            "Customer Success Manager", "Technical Account Manager",
            "Solutions Engineer", "Account Executive", "Sales Engineer",
            "Implementation Specialist", "Support Operations Lead",
            "Client Relations Director", "Platform Engineer", "DevOps Manager",
        ]
        jobs = [
            _make_job_listing(
                title=f"{titles[i % len(titles)]} at Division {i}",
                url=f"https://example.com/{i}",
                company=f"{''.join(chr(65 + (i*7+j) % 26) for j in range(8))} Inc",
            )
            for i in range(100)
        ]

        def dedup_all():
            seen = []
            unique = []
            for job in jobs:
                if not is_duplicate(job, seen):
                    seen.append(job)
                    unique.append(job)
            return unique

        results = benchmark(dedup_all)
        assert len(results) == 100

    def test_dedup_100_with_50pct_duplicates(self, benchmark, tmp_path):
        """Dedup 100 jobs with 50% duplicates."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        titles = [
            "Customer Success Manager", "Technical Account Manager",
            "Solutions Engineer", "Account Executive", "Sales Engineer",
        ]
        # First 50 unique with highly distinct names
        jobs = []
        for i in range(50):
            jobs.append(_make_job_listing(
                title=f"{titles[i % len(titles)]} at Division {i}",
                url=f"https://example.com/{i}",
                company=f"{''.join(chr(65 + (i*7+j) % 26) for j in range(8))} Inc",
            ))
        # Next 50 are exact title/company dupes from different URLs
        for i in range(50):
            jobs.append(_make_job_listing(
                title=jobs[i].title,
                url=f"https://other.com/{i}",
                company=jobs[i].company,
            ))

        def dedup_all():
            seen = []
            unique = []
            for job in jobs:
                if not is_duplicate(job, seen):
                    seen.append(job)
                    unique.append(job)
            return unique

        results = benchmark(dedup_all)
        # Exact duplicates removed; fuzzy matching may catch more
        assert len(results) < 100


# ============================================================
# Dashboard HTML generation performance
# ============================================================


class TestDashboardPerformance:
    """Benchmark dashboard HTML generation."""

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_render_row(self, benchmark):
        """Single row rendering."""
        job = _make_job_dict()
        result = benchmark(_render_row, job)
        assert "<tr" in result

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_generate_dashboard_10_jobs(self, benchmark, tmp_path):
        """Generate dashboard with 10 jobs."""
        jobs = [
            _make_job_dict(url=f"https://example.com/{i}", title=f"CSM {i}")
            for i in range(10)
        ]

        def gen():
            return generate_dashboard(jobs, output_dir=str(tmp_path))

        result = benchmark(gen)
        assert os.path.exists(result)

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_generate_dashboard_100_jobs(self, benchmark, tmp_path):
        """Generate dashboard with 100 jobs — stress test."""
        priorities = ["high", "medium", "low"]
        jobs = [
            _make_job_dict(
                url=f"https://example.com/{i}",
                title=f"CSM {i}",
                company=f"Corp{i}",
                priority=priorities[i % 3],
                score=90 - i,
            )
            for i in range(100)
        ]

        def gen():
            return generate_dashboard(jobs, output_dir=str(tmp_path))

        result = benchmark(gen)
        assert os.path.exists(result)
        size = os.path.getsize(result)
        # 100 jobs should produce a reasonably sized file (<2MB)
        assert size < 2 * 1024 * 1024

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_generate_dashboard_empty(self, benchmark, tmp_path):
        """Generate empty dashboard."""
        def gen():
            return generate_dashboard([], output_dir=str(tmp_path))

        result = benchmark(gen)
        assert os.path.exists(result)

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_format_age_throughput(self, benchmark):
        """Format 1000 age strings."""
        dates = [
            f"2026-02-{18 - (i % 18):02d}T{10 + (i % 12):02d}:00:00+00:00"
            for i in range(1000)
        ]

        def format_all():
            return [_format_age(d) for d in dates]

        results = benchmark(format_all)
        assert len(results) == 1000


# ============================================================
# Markdown report generation performance
# ============================================================


class TestReportPerformance:
    """Benchmark markdown report generation."""

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_report_100_jobs(self, benchmark, tmp_path):
        """Generate markdown report with 100 jobs."""
        priorities = ["high", "medium", "low"]
        jobs = [
            _make_job_dict(
                url=f"https://example.com/{i}",
                title=f"CSM {i}",
                priority=priorities[i % 3],
            )
            for i in range(100)
        ]

        def gen():
            return save_daily_report(jobs, output_dir=str(tmp_path))

        result = benchmark(gen)
        assert os.path.exists(result)


# ============================================================
# HTTP handler load tests
# ============================================================


class TestHttpLoadPerformance:
    """Test HTTP handler performance under concurrent load."""

    @pytest.fixture
    def load_server(self, tmp_path):
        """Start a test server for load testing."""
        from dashboard import generate_landing_page

        reports_dir = str(tmp_path / "reports")
        generate_landing_page(output_dir=reports_dir)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=reports_dir, **kwargs)

            def do_GET(self):
                if self.path == "/api/profile":
                    from user_profile import get_profile
                    data = json.dumps(get_profile()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                super().do_GET()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("localhost", 0), QuietHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        yield f"http://localhost:{port}"
        server.shutdown()

    def test_concurrent_get_index(self, load_server):
        """20 concurrent GET / requests all return 200."""
        errors = []

        def fetch_index():
            try:
                resp = requests.get(f"{load_server}/", timeout=5)
                if resp.status_code != 200:
                    errors.append(f"Status {resp.status_code}")
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(fetch_index) for _ in range(20)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"

    def test_concurrent_get_profile(self, load_server):
        """20 concurrent GET /api/profile requests all return valid JSON."""
        errors = []

        def fetch_profile():
            try:
                resp = requests.get(f"{load_server}/api/profile", timeout=5)
                if resp.status_code != 200:
                    errors.append(f"Status {resp.status_code}")
                    return
                data = resp.json()
                if "role_tags" not in data:
                    errors.append("Missing role_tags")
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(fetch_profile) for _ in range(20)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"

    def test_response_time_index(self, load_server):
        """GET / responds within 500ms."""
        start = time.monotonic()
        resp = requests.get(f"{load_server}/", timeout=5)
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Response took {elapsed:.3f}s"

    def test_response_time_profile(self, load_server):
        """GET /api/profile responds within 200ms."""
        start = time.monotonic()
        resp = requests.get(f"{load_server}/api/profile", timeout=5)
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.2, f"Response took {elapsed:.3f}s"


# ============================================================
# End-to-end pipeline timing (filter + score + dashboard)
# ============================================================


class TestPipelinePerformance:
    """Benchmark the full filter→score→dashboard pipeline (no network)."""

    @freeze_time("2026-02-19 12:00:00", tz_offset=0)
    def test_full_pipeline_50_jobs(self, benchmark, tmp_path):
        """Filter, score, and generate dashboard for 50 jobs."""
        jobs = [
            _make_job_listing(
                title=f"Customer Success Manager {i}",
                url=f"https://example.com/{i}",
                company=f"Corp{i}",
            )
            for i in range(50)
        ]

        def pipeline():
            # Filter
            passed = [j for j in jobs if passes_hard_filters(j)]
            # Score
            scored = [(j, rule_based_score(j)) for j in passed]
            scored.sort(key=lambda x: x[1], reverse=True)
            # Build dashboard dicts
            ranked = []
            for job, score in scored:
                priority = "high" if score >= 30 else ("medium" if score >= 20 else "low")
                ranked.append({
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                    "source": job.source,
                    "score": score,
                    "priority": priority,
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "location": job.location,
                    "posted_date": job.posted_date.isoformat() if job.posted_date else "",
                    "description": job.description,
                    "summary": "",
                })
            # Generate
            return generate_dashboard(ranked, output_dir=str(tmp_path))

        result = benchmark(pipeline)
        assert os.path.exists(result)
