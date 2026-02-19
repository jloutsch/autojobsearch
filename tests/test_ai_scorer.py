"""Tests for ai_scorer.py — AI scoring via Ollama."""

import json
from unittest.mock import patch

import requests
import responses

import ai_scorer
from ai_scorer import _ollama_available, ai_score, score_top_jobs


OLLAMA_URL = ai_scorer.OLLAMA_URL
OLLAMA_MODEL = ai_scorer.OLLAMA_MODEL


# --- _ollama_available ---


@responses.activate
def test_ollama_available_true():
    """/api/tags returns model list containing configured model → True."""
    responses.add(
        responses.GET,
        f"{OLLAMA_URL}/api/tags",
        json={"models": [{"name": OLLAMA_MODEL}]},
        status=200,
    )
    assert _ollama_available() is True


@responses.activate
def test_ollama_available_false_no_model():
    """Model not in list → False."""
    responses.add(
        responses.GET,
        f"{OLLAMA_URL}/api/tags",
        json={"models": [{"name": "other-model:latest"}]},
        status=200,
    )
    assert _ollama_available() is False


def test_ollama_available_connection_error():
    """Connection refused → False."""
    with patch("ai_scorer.requests.get",
               side_effect=requests.exceptions.ConnectionError("Connection refused")):
        assert _ollama_available() is False


# --- ai_score ---


@responses.activate
def test_ai_score_valid_response(make_job):
    """Valid JSON response parsed correctly."""
    result_json = {
        "fit_score": 35,
        "summary": "Great fit for this role.",
        "key_matches": ["customer success", "saas"],
        "gaps": ["no sales experience"],
        "priority": "high",
    }
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={
            "message": {"content": json.dumps(result_json)},
            "done": True,
        },
        status=200,
    )

    job = make_job()
    result = ai_score(job)

    assert result["fit_score"] == 35
    assert result["priority"] == "high"
    assert "Great fit" in result["summary"]


@responses.activate
def test_ai_score_score_clamped(make_job):
    """fit_score: 75 clamped to 50."""
    result_json = {"fit_score": 75, "summary": "", "key_matches": [], "gaps": [], "priority": "high"}
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={"message": {"content": json.dumps(result_json)}, "done": True},
        status=200,
    )

    result = ai_score(make_job())
    assert result["fit_score"] == 50


@responses.activate
def test_ai_score_negative_clamped(make_job):
    """Negative fit_score clamped to 0."""
    result_json = {"fit_score": -10, "summary": "", "key_matches": [], "gaps": [], "priority": "low"}
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={"message": {"content": json.dumps(result_json)}, "done": True},
        status=200,
    )

    result = ai_score(make_job())
    assert result["fit_score"] == 0


@responses.activate
def test_ai_score_malformed_json(make_job):
    """Non-JSON response returns fallback dict."""
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={"message": {"content": "This is not JSON at all"}, "done": True},
        status=200,
    )

    result = ai_score(make_job())
    assert result["fit_score"] == 0
    assert result["priority"] == "low"


@responses.activate
def test_ai_score_markdown_fences_stripped(make_job):
    """Response wrapped in ```json ``` fences still parsed."""
    result_json = {"fit_score": 30, "summary": "Ok", "key_matches": [], "gaps": [], "priority": "medium"}
    content = "```json\n" + json.dumps(result_json) + "\n```"
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={"message": {"content": content}, "done": True},
        status=200,
    )

    result = ai_score(make_job())
    assert result["fit_score"] == 30


# --- score_top_jobs ---


def test_score_top_jobs_ollama_unavailable(make_job):
    """Returns [None]*len(jobs) when Ollama is down."""
    with patch("ai_scorer.requests.get",
               side_effect=requests.exceptions.ConnectionError("offline")):
        jobs = [make_job(), make_job()]
        rule_scores = [30.0, 20.0]
        results = score_top_jobs(jobs, rule_scores, top_n=15)

    assert len(results) == 2
    assert all(r is None for r in results)


@responses.activate
def test_score_top_jobs_ranks_by_rule_score(make_job):
    """Only top N by rule score get AI-scored."""
    # Make Ollama available
    responses.add(
        responses.GET,
        f"{OLLAMA_URL}/api/tags",
        json={"models": [{"name": OLLAMA_MODEL}]},
        status=200,
    )

    # AI response for each scored job
    result_json = {"fit_score": 25, "summary": "Good", "key_matches": [], "gaps": [], "priority": "medium"}
    for _ in range(2):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            json={"message": {"content": json.dumps(result_json)}, "done": True},
            status=200,
        )

    jobs = [make_job(title=f"Job {i}") for i in range(5)]
    rule_scores = [10.0, 40.0, 20.0, 30.0, 5.0]

    results = score_top_jobs(jobs, rule_scores, top_n=2)

    # Only top 2 by rule score (indices 1 and 3) should be scored
    assert results[1] is not None  # score 40
    assert results[3] is not None  # score 30
    assert results[0] is None  # score 10
    assert results[4] is None  # score 5


@responses.activate
def test_custom_prompt_template(make_job, monkeypatch):
    """Profile ai_prompt_template field is used instead of default."""
    import user_profile

    profile = user_profile.get_profile()
    profile["ai_prompt_template"] = "Custom: $title at $company"

    result_json = {"fit_score": 20, "summary": "", "key_matches": [], "gaps": [], "priority": "low"}
    responses.add(
        responses.POST,
        f"{OLLAMA_URL}/api/chat",
        json={"message": {"content": json.dumps(result_json)}, "done": True},
        status=200,
    )

    result = ai_score(make_job())
    # Verify the request body used the custom template
    request_body = json.loads(responses.calls[0].request.body)
    prompt = request_body["messages"][0]["content"]
    assert prompt.startswith("Custom:")
