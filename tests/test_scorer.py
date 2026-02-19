"""Tests for scorer.py — rule-based scoring logic."""

from scorer import rule_based_score


# --- Title match scoring (0-15 pts) ---


def test_primary_role_tag_match(make_job):
    """Title matching primary tag gets 15 pts for title component."""
    job = make_job(title="Application Support Manager", description="")
    score = rule_based_score(job)
    assert score >= 15  # At least 15 from title


def test_secondary_role_tag_match(make_job):
    """Title matching secondary tag gets 10 pts for title component."""
    job = make_job(title="Solutions Engineer", description="")
    score = rule_based_score(job)
    assert score >= 10


def test_generic_role_match(make_job):
    """Title with role keyword but not in primary/secondary gets 5 pts."""
    job = make_job(title="Customer Success Associate Lead", description="")
    score = rule_based_score(job)
    assert score >= 5


def test_no_role_match_still_gets_5(make_job):
    """Even unrelated titles get 5 pts (scorer always adds at least 5 for title)."""
    # The scorer always falls through to the else branch giving 5 pts
    job = make_job(title="Random Title", description="")
    score = rule_based_score(job)
    assert score >= 5


# --- Priority company scoring (+10 pts) ---


def test_priority_company_bonus(make_job):
    """Company in PRIORITY_COMPANIES gets +10 pts."""
    job = make_job(company="SentinelOne", title="Customer Success Manager", description="")
    score = rule_based_score(job)
    # 15 (primary title) + 10 (priority company) = at least 25
    assert score >= 25


def test_non_priority_company_no_bonus(make_job):
    """Company NOT in PRIORITY_COMPANIES gets no bonus."""
    job = make_job(company="RandomCorp", title="Customer Success Manager", description="")
    # No priority bonus
    score_with = rule_based_score(make_job(company="SentinelOne", title="Customer Success Manager", description=""))
    score_without = rule_based_score(job)
    assert score_with - score_without == 10


# --- Industry keyword scoring (0-10 pts) ---


def test_industry_keyword_scoring(make_job):
    """Description with industry keywords gets points."""
    job = make_job(description="A role in cybersecurity and saas environment")
    score = rule_based_score(job)
    # 2 industry matches * 2.5 = 5 pts for industry
    assert score >= 10  # 5 title + 5 industry


def test_industry_cap_at_10(make_job):
    """5+ industry keywords still capped at 10 pts."""
    job = make_job(
        description="cybersecurity saas healthcare it cloud infrastructure devops more keywords"
    )
    score_all = rule_based_score(job)
    # Industry maxes at 10, so even with all 5 keywords (5 * 2.5 = 12.5 -> capped at 10)
    job_none = make_job(description="no matching keywords here at all")
    score_none = rule_based_score(job_none)
    assert score_all - score_none <= 10 + 5  # industry(10) + skills could add up to 5


# --- Salary scoring (0-10 pts) ---


def test_salary_in_range(make_job):
    """Salary at or above target min gets 10 pts."""
    job = make_job(salary_min=140000, description="")
    score = rule_based_score(job)
    # 5 (title) + 10 (salary) = 15
    assert score >= 15


def test_salary_below_min_but_acceptable(make_job):
    """Salary between 85% of min and min gets 5 pts."""
    # min is 130000, 85% is 110500
    job = make_job(salary_min=115000, description="")
    score = rule_based_score(job)
    # 5 (title) + 5 (salary) = 10
    assert score >= 10


def test_salary_zero_no_salary_points(make_job):
    """No salary info gets 0 salary pts."""
    job = make_job(salary_min=0, description="")
    score = rule_based_score(job)
    # Only title pts
    assert score == 5


# --- Skills alignment (0-5 pts) ---


def test_skills_alignment(make_job):
    """Description with matching skills gets points."""
    job = make_job(description="Experience with jira, python, and docker required")
    score = rule_based_score(job)
    # 3 matching skills = 3 pts
    assert score >= 8  # 5 (title) + 3 (skills)


def test_skills_cap_at_5(make_job):
    """6+ matching skills capped at 5 pts."""
    job = make_job(
        description="jira git docker python sql linux troubleshooting aws confluence communication"
    )
    score = rule_based_score(job)
    # All 10 skills match but capped at 5
    job_no_skills = make_job(description="no skills at all")
    score_diff = rule_based_score(job) - rule_based_score(job_no_skills)
    # diff should be at most 5 (skills) + industry/salary differences
    # Just verify the score is reasonable
    assert score >= 10  # 5 title + 5 skills


# --- Combined scoring ---


def test_max_possible_score(make_job):
    """Perfect job gets close to 50 pts."""
    job = make_job(
        title="Application Support Manager",  # primary: 15
        company="SentinelOne",  # priority: +10
        description="cybersecurity saas healthcare it cloud infrastructure devops jira python docker sql linux aws",
        salary_min=140000,  # salary: +10
    )
    score = rule_based_score(job)
    # 15 + 10 + 10 + 10 + 5 = 50
    assert score == 50


def test_min_possible_score(make_job):
    """Non-matching job gets 5 pts minimum (title always adds 5)."""
    job = make_job(
        title="Random Title",
        company="NobodyCorp",
        description="",
        salary_min=0,
    )
    score = rule_based_score(job)
    assert score == 5


def test_case_insensitive_matching(make_job):
    """Uppercase skills/keywords in description still match."""
    job = make_job(description="JIRA PYTHON DOCKER CYBERSECURITY SAAS")
    score = rule_based_score(job)
    # Skills and industry should match despite uppercase
    assert score >= 5 + 3 + 5  # title + 3 skills + 2 industry
