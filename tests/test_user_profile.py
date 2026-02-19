"""Tests for user_profile.py — profile caching."""

import json
import os
import threading

import pytest

import user_profile


def test_loads_from_file(tmp_path, monkeypatch):
    """Reads and returns JSON from path."""
    profile_data = {"role_tags": ["test"], "salary_range": {"min": 0, "max": 0, "floor": 0}}
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data))

    # Reset the cache
    monkeypatch.setattr(user_profile, "_profile", None)
    result = user_profile.get_profile(str(profile_file))
    assert result["role_tags"] == ["test"]


def test_caches_on_second_call(tmp_path, monkeypatch):
    """Second call returns same object without re-reading disk."""
    profile_data = {"role_tags": ["cached"]}
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data))

    monkeypatch.setattr(user_profile, "_profile", None)
    result1 = user_profile.get_profile(str(profile_file))

    # Modify file on disk — should not affect cached result
    profile_file.write_text(json.dumps({"role_tags": ["changed"]}))
    result2 = user_profile.get_profile(str(profile_file))

    assert result1 is result2  # Same object (cached)
    assert result2["role_tags"] == ["cached"]


def test_reload_clears_cache(tmp_path, monkeypatch):
    """reload_profile() → next get_profile() re-reads from disk."""
    profile_data = {"role_tags": ["original"]}
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data))

    monkeypatch.setattr(user_profile, "_profile", None)
    user_profile.get_profile(str(profile_file))

    # Update disk
    profile_file.write_text(json.dumps({"role_tags": ["updated"]}))

    # Reload
    user_profile.reload_profile()
    result = user_profile.get_profile(str(profile_file))
    assert result["role_tags"] == ["updated"]


def test_copies_example_if_missing(tmp_path, monkeypatch):
    """Missing profile.json → copies from profile.example.json."""
    example_data = {"role_tags": ["from_example"]}
    example_file = tmp_path / "profile.example.json"
    example_file.write_text(json.dumps(example_data))

    profile_file = tmp_path / "profile.json"
    assert not profile_file.exists()

    monkeypatch.setattr(user_profile, "_profile", None)
    monkeypatch.setattr(user_profile, "_EXAMPLE_PATH", str(example_file))

    result = user_profile.get_profile(str(profile_file))
    assert result["role_tags"] == ["from_example"]
    assert profile_file.exists()


def test_thread_safety(tmp_path, monkeypatch):
    """Concurrent get_profile() calls don't corrupt state."""
    profile_data = {"role_tags": ["thread_safe"]}
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data))

    monkeypatch.setattr(user_profile, "_profile", None)

    results = []
    errors = []

    def reader():
        try:
            r = user_profile.get_profile(str(profile_file))
            results.append(r["role_tags"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert all(tags == ["thread_safe"] for tags in results)


def test_invalid_json_raises(tmp_path, monkeypatch):
    """Malformed JSON file raises json.JSONDecodeError."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json at all {{{")

    monkeypatch.setattr(user_profile, "_profile", None)
    with pytest.raises(json.JSONDecodeError):
        user_profile.get_profile(str(bad_file))
