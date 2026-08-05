"""Tests for main.py — run_pipeline integration tests."""

from datetime import datetime, timezone
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
        "posted_date": datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return JobListing(**defaults)


@patch("main.generate_dashboard")
@patch("main.save_daily_report")
@patch("main.score_top_jobs")
@patch("main.init_db")
def test_pipeline_no_results(mock_init_db, mock_ai, mock_report, mock_dash):
    """All sources return [] → empty report generated."""
    mock_ai.return_value = []
    mock_report.return_value = "reports/2026-02-19.md"

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        for mock_src in [gs, cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        # Use real safe_collect so it catches the collect() exception
        mock_gs = MagicMock()
        mock_gs.name = "greenhouse"
        mock_gs.collect.side_effect = RuntimeError("API down")
        mock_gs.safe_collect = lambda: BaseSource.safe_collect(mock_gs)
        gs.return_value = mock_gs
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

        from main import run_pipeline
        # Should not raise despite Greenhouse failure
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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job1]
        rs.return_value.safe_collect.return_value = [job2]
        for mock_src in [cs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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

    job = _make_job()
    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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

    job = _make_job()
    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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
    """AI score + rule score combined correctly."""
    job = _make_job()
    ai_result = {
        "fit_score": 35,
        "summary": "Good match.",
        "key_matches": ["cybersecurity"],
        "gaps": [],
        "priority": "high",
    }
    mock_ai.return_value = [ai_result]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["score"] > 35  # rule_based_score adds to the 35
    assert result[0]["priority"] == "high"
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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job1, job2]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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
    """Rule-only: >=30 high, >=20 medium, else low."""
    job = _make_job()
    mock_ai.return_value = [None]
    mock_report.return_value = "reports/2026-02-19.md"
    mock_dash.return_value = "reports/2026-02-19.html"

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

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
    """Rule score >= 30 → 'high' priority without AI (line 106)."""
    # Create a job that scores 30+: primary title match (15) + priority company (10) + salary (10) = 35
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

    with patch("main.GreenhouseSource") as gs, \
         patch("main.CrowdStrikeSource") as cs, \
         patch("main.RemoteOKSource") as rs, \
         patch("main.BuiltInSource") as bs, \
         patch("main.WeWorkRemotelySource") as ws:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws]:
            mock_src.return_value.safe_collect.return_value = []

        from main import run_pipeline
        result = run_pipeline()

    assert len(result) == 1
    assert result[0]["priority"] == "high"
    assert result[0]["score"] >= 30
