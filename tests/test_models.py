"""Tests for models.py — JobListing dataclass."""

from datetime import datetime

import pytest

from models import JobListing


def test_joblisting_defaults():
    """Default values for optional fields."""
    job = JobListing(
        title="CSM", company="Corp", url="https://example.com", source="test"
    )
    assert job.description == ""
    assert job.salary_min == 0
    assert job.salary_max == 0
    assert job.location == ""
    assert job.is_remote is False
    assert isinstance(job.posted_date, datetime)
    assert job.raw_data == {}


def test_joblisting_required_fields():
    """Missing required field raises TypeError."""
    with pytest.raises(TypeError):
        JobListing(title="CSM", company="Corp")  # missing url and source


def test_joblisting_custom_values():
    """All fields populated correctly."""
    posted = datetime(2026, 2, 18, 10, 0, 0)
    job = JobListing(
        title="TAM",
        company="SecureCo",
        url="https://secureco.com/jobs/1",
        source="greenhouse",
        description="A great role",
        salary_min=130000,
        salary_max=150000,
        location="Remote - US",
        is_remote=True,
        posted_date=posted,
        raw_data={"id": 42},
    )
    assert job.title == "TAM"
    assert job.company == "SecureCo"
    assert job.salary_min == 130000
    assert job.salary_max == 150000
    assert job.is_remote is True
    assert job.raw_data == {"id": 42}
    assert job.posted_date == posted


def test_joblisting_posted_date_default():
    """Default posted_date is approximately now."""
    job = JobListing(
        title="CSM", company="Corp", url="https://example.com", source="test"
    )
    now = datetime.now()
    # Should be within a few seconds of now
    delta = abs((now - job.posted_date).total_seconds())
    assert delta < 5
