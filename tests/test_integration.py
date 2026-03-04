"""Integration tests — end-to-end pipeline flows without network calls."""

import json
from datetime import datetime, timezone

import pytest

import config
import user_profile
from filters import passes_hard_filters
from models import JobListing
from scorer import rule_based_score


@pytest.fixture
def make_job():
    """Factory fixture for creating JobListing instances with defaults."""

    def _make(**overrides):
        defaults = {
            "title": "Customer Success Manager",
            "company": "TestCorp",
            "url": "https://example.com/job/1",
            "source": "test",
            "description": "A customer success role in a cybersecurity saas company.",
            "salary_min": 130000,
            "salary_max": 150000,
            "location": "Remote",
            "is_remote": True,
            "posted_date": datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        return JobListing(**defaults)

    return _make


def _update_profile(monkeypatch, **overrides):
    """Merge overrides into the current profile and reload config."""
    current = user_profile.get_profile().copy()
    current.update(overrides)
    monkeypatch.setattr(user_profile, "_profile", current)
    config.reload()
    return current


class TestParsedTagsImproveScoring:
    """Verify that parsed resume tags actually improve job matching scores."""

    def test_matching_industry_tags_boost_score(self, make_job, monkeypatch):
        """Jobs with descriptions matching industry_tags score higher."""
        _update_profile(
            monkeypatch,
            industry_tags=["cybersecurity", "threat detection", "endpoint security"],
        )

        matching_job = make_job(
            description="Leading cybersecurity company with threat detection "
            "and endpoint security platform.",
        )
        generic_job = make_job(
            description="A company that makes widgets and does retail operations.",
        )

        score_match = rule_based_score(matching_job)
        score_generic = rule_based_score(generic_job)
        assert score_match > score_generic, (
            f"Matching job ({score_match}) should score higher than generic ({score_generic})"
        )

    def test_matching_skills_boost_score(self, make_job, monkeypatch):
        """Jobs mentioning profile skills score higher."""
        _update_profile(
            monkeypatch,
            skills=["python", "docker", "aws", "sql", "jira"],
        )

        matching_job = make_job(
            description="Must know python, docker, aws, sql, and use jira daily.",
        )
        no_match_job = make_job(
            description="Must know ruby, kubernetes, gcp, and use monday.com.",
        )

        score_match = rule_based_score(matching_job)
        score_no_match = rule_based_score(no_match_job)
        assert score_match > score_no_match


class TestProfileSaveReloadsConfig:
    """Verify that updating the profile refreshes config module globals."""

    def test_role_keywords_update(self, monkeypatch):
        """Config.ROLE_KEYWORDS reflects updated role_tags."""
        _update_profile(monkeypatch, role_tags=["devops engineer", "sre"])
        assert "devops engineer" in config.ROLE_KEYWORDS
        assert "sre" in config.ROLE_KEYWORDS

    def test_priority_companies_update(self, monkeypatch):
        """Config.PRIORITY_COMPANIES reflects updated priority_companies."""
        _update_profile(monkeypatch, priority_companies=["Acme", "Globex"])
        assert config.PRIORITY_COMPANIES == ["Acme", "Globex"]

    def test_salary_floor_update(self, monkeypatch):
        """Config.SALARY_FLOOR reflects updated salary_range."""
        _update_profile(
            monkeypatch,
            salary_range={"min": 150000, "max": 200000, "floor": 120000},
        )
        assert config.SALARY_FLOOR == 120000


class TestFilterUsesUpdatedRoleTags:
    """Verify passes_hard_filters() uses current config.ROLE_KEYWORDS."""

    def test_new_role_tags_allow_matching_jobs(self, make_job, monkeypatch):
        """After updating role_tags, jobs with new keywords pass filters."""
        _update_profile(monkeypatch, role_tags=["devops engineer"])

        devops_job = make_job(title="Senior DevOps Engineer")
        assert passes_hard_filters(devops_job) is True

    def test_removed_role_tags_reject_jobs(self, make_job, monkeypatch):
        """After removing role_tags, previously matching jobs get rejected."""
        # Set role_tags to something that won't match "Customer Success Manager"
        _update_profile(monkeypatch, role_tags=["data scientist"])

        csm_job = make_job(title="Customer Success Manager")
        assert passes_hard_filters(csm_job) is False


class TestScoringPrimaryVsSecondaryTags:
    """Verify primary_role_tags get higher scores than secondary_role_tags."""

    def test_primary_scores_higher_than_secondary(self, make_job, monkeypatch):
        """Job matching primary_role_tags scores higher than one matching secondary."""
        _update_profile(
            monkeypatch,
            scoring={
                "primary_role_tags": ["Customer Success Manager"],
                "secondary_role_tags": ["Solutions Engineer"],
            },
        )

        primary_job = make_job(title="Customer Success Manager")
        secondary_job = make_job(title="Solutions Engineer")

        score_primary = rule_based_score(primary_job)
        score_secondary = rule_based_score(secondary_job)
        assert score_primary > score_secondary, (
            f"Primary ({score_primary}) should score higher than secondary ({score_secondary})"
        )

    def test_unmatched_title_scores_lowest(self, make_job, monkeypatch):
        """Job title matching neither primary nor secondary gets base score."""
        _update_profile(
            monkeypatch,
            scoring={
                "primary_role_tags": ["Customer Success Manager"],
                "secondary_role_tags": ["Solutions Engineer"],
            },
        )

        unmatched_job = make_job(title="Janitor")
        secondary_job = make_job(title="Solutions Engineer")

        score_unmatched = rule_based_score(unmatched_job)
        score_secondary = rule_based_score(secondary_job)
        assert score_secondary > score_unmatched


class TestFullPipelineCollectFilterScore:
    """Test the collect→filter→score pipeline with mocked sources."""

    def test_pipeline_filters_and_ranks_correctly(self, make_job, monkeypatch):
        """Mock sources return known jobs; verify filter + score ordering."""
        _update_profile(
            monkeypatch,
            role_tags=["customer success", "account management"],
            industry_tags=["cybersecurity", "saas"],
            skills=["python", "jira", "aws"],
            priority_companies=["SentinelOne"],
            scoring={
                "primary_role_tags": ["Customer Success Manager"],
                "secondary_role_tags": ["Account Manager"],
            },
        )

        # Job that should score highest: primary title + priority company + industry match
        top_job = make_job(
            title="Customer Success Manager",
            company="SentinelOne",
            url="https://example.com/1",
            description="Cybersecurity saas platform. Must know python, jira, and aws.",
        )

        # Job that should score medium: secondary title + industry match
        mid_job = make_job(
            title="Account Management Lead",
            company="OtherCorp",
            url="https://example.com/2",
            description="A saas cybersecurity company looking for account management.",
        )

        # Job that should be filtered out: wrong title
        filtered_job = make_job(
            title="Software Engineer",
            company="TestCorp",
            url="https://example.com/3",
        )

        # Job that should be filtered out: junior role
        junior_job = make_job(
            title="Junior Customer Success Associate",
            company="TestCorp",
            url="https://example.com/4",
        )

        all_jobs = [top_job, mid_job, filtered_job, junior_job]

        # Filter
        passed = [j for j in all_jobs if passes_hard_filters(j)]
        assert len(passed) == 2
        assert top_job in passed
        assert mid_job in passed
        assert filtered_job not in passed
        assert junior_job not in passed

        # Score and rank
        scored = [(j, rule_based_score(j)) for j in passed]
        scored.sort(key=lambda x: x[1], reverse=True)

        assert scored[0][0] is top_job, "SentinelOne CSM should rank first"
        assert scored[0][1] > scored[1][1], "Top job should have higher score"

    def test_salary_floor_filter(self, make_job, monkeypatch):
        """Jobs below salary floor are filtered out."""
        _update_profile(
            monkeypatch,
            salary_range={"min": 130000, "max": 160000, "floor": 100000},
        )

        above_floor = make_job(salary_min=110000, salary_max=130000)
        below_floor = make_job(
            salary_min=70000, salary_max=90000,
            url="https://example.com/low-pay",
        )
        no_salary = make_job(
            salary_min=0, salary_max=0,
            url="https://example.com/no-salary",
        )

        assert passes_hard_filters(above_floor) is True
        assert passes_hard_filters(below_floor) is False
        assert passes_hard_filters(no_salary) is True  # No salary data = don't reject
