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
         patch("main.WeWorkRemotelySource") as ws, \
         patch("main.LinkedInAlertsSource") as ls:
        for mock_src in [gs, cs, rs, bs, ws, ls]:
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
         patch("main.WeWorkRemotelySource") as ws, \
         patch("main.LinkedInAlertsSource") as ls:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws, ls]:
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
         patch("main.WeWorkRemotelySource") as ws, \
         patch("main.LinkedInAlertsSource") as ls:
        # Use real safe_collect so it catches the collect() exception
        mock_gs = MagicMock()
        mock_gs.name = "greenhouse"
        mock_gs.collect.side_effect = RuntimeError("API down")
        mock_gs.safe_collect = lambda: BaseSource.safe_collect(mock_gs)
        gs.return_value = mock_gs
        for mock_src in [cs, rs, bs, ws, ls]:
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
         patch("main.WeWorkRemotelySource") as ws, \
         patch("main.LinkedInAlertsSource") as ls:
        gs.return_value.safe_collect.return_value = [job1]
        rs.return_value.safe_collect.return_value = [job2]
        for mock_src in [cs, bs, ws, ls]:
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
         patch("main.WeWorkRemotelySource") as ws, \
         patch("main.LinkedInAlertsSource") as ls:
        gs.return_value.safe_collect.return_value = [job]
        for mock_src in [cs, rs, bs, ws, ls]:
            mock_src.return_value.safe_collect.return_value = []

        from main import run_pipeline
        result = run_pipeline()

    assert result == []
