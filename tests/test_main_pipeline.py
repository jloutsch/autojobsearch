"""Tests for main.py — run_pipeline integration tests."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from models import JobListing


def _make_job(**overrides):
    """Helper to create a JobListing without the fixture."""
    defaults = {
        "title": "Customer Success Manager",
        "company": "TestCorp",
        "url": "https://example.com/job/1",
        "source": "test",
        "description": "A cybersecurity saas role with jira experience.",
        "salary_min": 130000,
        "salary_max": 150000,
        "location": "Remote - US",
        "is_remote": True,
        # Relative, not a fixed date — see the note in conftest.make_job.
        "posted_date": datetime.now(timezone.utc) - timedelta(days=1),
    }
    defaults.update(overrides)
    return JobListing(**defaults)


@contextmanager
def stub_sources(*job_lists):
    """Replace the whole source list with stubs returning the given jobs.

    Patches main.build_sources rather than individual source classes. Patching
    classes one by one leaves any unlisted source live, so it makes real network
    calls and the suite hangs — which is exactly what this used to do.
    """
    stubs = []
    for jobs in job_lists:
        stub = MagicMock()
        stub.safe_collect.return_value = list(jobs)
        stubs.append(stub)
    with patch("main.build_sources", return_value=stubs):
        yield stubs


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.init_db")
def test_pipeline_no_results(mock_init_db, mock_ai, mock_report, mock_dash):
    """All sources return [] → empty report generated."""
    mock_ai.return_value = []
    mock_report.return_value = "reports/2026-02-19.md"

    with stub_sources([], [], []):
        from main import run_pipeline
        result = run_pipeline()

    assert result == []
    mock_report.assert_called_once()


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_end_to_end(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """Sources → filters → dedup → scoring → report generation."""
    job = _make_job()
    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["title"] == "Customer Success Manager"
    mock_report.assert_called_once()
    mock_dash.assert_called_once()


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.init_db")
def test_source_failure_isolated(mock_init_db, mock_ai, mock_report, mock_dash):
    """One source raising exception doesn't kill pipeline."""
    from sources.base import BaseSource

    mock_ai.return_value = []
    mock_report.return_value = "reports/2026-02-19.md"

    # Real safe_collect so it catches the collect() exception.
    failing = MagicMock()
    failing.name = "greenhouse"
    failing.collect.side_effect = RuntimeError("API down")
    failing.safe_collect = lambda: BaseSource.safe_collect(failing)

    healthy = MagicMock()
    healthy.safe_collect.return_value = []

    with patch("main.build_sources", return_value=[failing, healthy]):
        from main import run_pipeline
        # Should not raise despite the source failure
        result = run_pipeline()

    assert result == []


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_dedup_removes_cross_source_duplicates(
    mock_init_db, mock_filters, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """Same job from 2 sources counted once."""
    job1 = _make_job(url="https://example.com/job/1", source="greenhouse")
    job2 = _make_job(url="https://example.com/job/2", source="remoteok")
    # Both have same title and company, so dedup should catch it

    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job1], [job2]):
        from main import run_pipeline
        result = run_pipeline()

    # Dedup should keep only one
    assert len(result) == 1


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent")
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_previously_sent_excluded(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """Jobs in seen_jobs.db are excluded from results."""
    job = _make_job()
    mock_sent.return_value = True  # All jobs have been sent before
    mock_ai.return_value = []
    mock_report.return_value = "reports/2026-02-19.md"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    # Jobs in seen_jobs.db are excluded
    assert result == []


# --- Additional edge cases ---


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters")
@patch("main.init_db")
def test_pipeline_all_filtered_out(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """All jobs filtered → empty report."""
    mock_filters.return_value = False  # All jobs fail filter
    mock_report.return_value = "reports/2026-02-19.md"

    with stub_sources([_make_job()], []):
        from main import run_pipeline
        result = run_pipeline()

    assert result == []


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=True)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_all_seen_before(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """All jobs previously sent → empty report."""
    mock_report.return_value = "reports/2026-02-19.md"

    with stub_sources([_make_job()], []):
        from main import run_pipeline
        result = run_pipeline()

    assert result == []


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_ai_score_combined(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """A successful AI result is blended in and its analysis propagates."""
    job = _make_job()
    mock_ai.return_value = [{
        "fit_score": 35,
        "summary": "Good match.",
        "key_matches": ["cybersecurity"],
        "gaps": [],
        "status": "ok",
    }]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["scored_by"] == "ai"
    assert 0 < result[0]["score"] <= 100
    assert result[0]["summary"] == "Good match."
    assert result[0]["key_matches"] == ["cybersecurity"]


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_ai_failure_falls_back_to_rules(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """A failed AI call must not be treated as a genuine zero score."""
    job = _make_job()
    # fit_score 0 with an error status — the job should be ranked on rules
    # alone rather than being buried by the failure.
    mock_ai.return_value = [{
        "fit_score": 0, "summary": "", "key_matches": [], "gaps": [],
        "status": "error",
    }]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["scored_by"] == "rules"
    assert result[0]["score"] > 0


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_sorts_by_score(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """Output sorted descending by score."""
    job1 = _make_job(title="Low Score CSM", salary_min=0, salary_max=0,
                     description="basic role")
    job2 = _make_job(title="Customer Success Manager", url="https://example.com/job/2",
                     description="A cybersecurity saas role with jira experience.")

    mock_ai.return_value = [None, None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job1, job2], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 2
    assert result[0]["score"] >= result[1]["score"]


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_priority_assignment(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """Priority is derived from the 0-100 composite, not from the model."""
    job = _make_job()
    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["priority"] in ("high", "medium", "low")


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_pipeline_high_priority_rule_only(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """A strong rule score alone reaches 'high' on the normalised scale."""
    # primary title match (15) + priority company (10) + salary (10) = 35/50,
    # which normalises to 70/100 — the 'high' threshold.
    job = _make_job(
        title="Application Support Manager",  # primary role tag
        company="SentinelOne",  # priority company
        salary_min=130000,
        salary_max=150000,
        description="A cybersecurity saas role with jira and docker experience.",
    )
    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["scored_by"] == "rules"
    assert result[0]["priority"] == "high"
    assert result[0]["score"] >= 70


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.mark_as_sent")
@patch("main.was_previously_sent", return_value=False)
@patch("main.is_duplicate", return_value=False)
@patch("main.passes_hard_filters", return_value=True)
@patch("main.init_db")
def test_priority_band_matches_displayed_score(
    mock_init_db, mock_filters, mock_dedup, mock_sent, mock_mark,
    mock_ai, mock_report, mock_dash
):
    """A job's band must agree with the whole number every renderer shows.

    Banding a fractional score puts two jobs both displaying "50/100" into
    different sections, which reads as a bug in the report.
    """
    job = _make_job()
    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with stub_sources([job], []):
        from main import run_pipeline
        result = run_pipeline()

    score = result[0]["score"]
    assert score == round(score), "score must already be whole when it reaches the renderers"
    expected = "high" if score >= 70 else ("medium" if score >= 50 else "low")
    assert result[0]["priority"] == expected
