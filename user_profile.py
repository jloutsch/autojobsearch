"""Load user profile from profile.json. Single source of truth for all preferences."""

import json
import os
import threading

_dir = os.path.dirname(__file__)
PROFILE_PATH = os.path.join(_dir, "profile.json")
_EXAMPLE_PATH = os.path.join(_dir, "profile.example.json")

_profile = None
_lock = threading.Lock()


def get_profile(path: str = PROFILE_PATH) -> dict:
    """Get the cached profile, loading from disk on first access."""
    global _profile
    with _lock:
        if _profile is None:
            if not os.path.exists(path) and os.path.exists(_EXAMPLE_PATH):
                import shutil
                shutil.copy2(_EXAMPLE_PATH, path)
            with open(path) as f:
                _profile = json.load(f)
        return _profile


def reload_profile():
    """Clear the cached profile so the next get_profile() re-reads from disk."""
    global _profile
    with _lock:
        _profile = None
