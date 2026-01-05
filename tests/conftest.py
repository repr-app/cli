"""
Pytest configuration and shared fixtures for repr CLI tests.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Generator
import uuid

import pytest
from git import Repo


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_repr_home(temp_dir: Path, monkeypatch) -> Path:
    """Mock ~/.repr directory using REPR_HOME env var."""
    repr_home = temp_dir / ".repr"
    repr_home.mkdir()
    monkeypatch.setenv("REPR_HOME", str(repr_home))

    # Reload modules to pick up new env var
    import repr.config
    import repr.keychain
    import importlib
    importlib.reload(repr.keychain)
    importlib.reload(repr.config)

    return repr_home


@pytest.fixture
def mock_git_repo(temp_dir: Path) -> Repo:
    """Create a mock git repository for testing."""
    repo_path = temp_dir / "test-repo"
    repo_path.mkdir()

    # Initialize git repo
    repo = Repo.init(repo_path)

    # Configure git user
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repository")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return repo


@pytest.fixture
def mock_config(mock_repr_home: Path) -> dict:
    """Create a mock config.json file."""
    from repr.config import DEFAULT_CONFIG, CONFIG_FILE, save_config

    config = DEFAULT_CONFIG.copy()
    save_config(config)

    return config


@pytest.fixture
def authenticated_config(mock_config: dict, mock_repr_home: Path) -> dict:
    """Create a mock authenticated config."""
    from repr.config import save_config
    from repr.keychain import store_secret

    # Store fake token in keychain
    store_secret("auth_token", "fake_token_12345")

    # Update config with auth info
    mock_config["auth"] = {
        "email": "test@example.com",
        "token_keychain_ref": "auth_token",
    }
    save_config(mock_config)

    return mock_config


@pytest.fixture
def mock_stories(mock_repr_home: Path) -> list[dict]:
    """Create mock story files."""
    import repr.storage
    import importlib

    # Reload storage module to pick up new REPR_HOME
    importlib.reload(repr.storage)

    from repr.storage import STORIES_DIR, save_story

    STORIES_DIR.mkdir(parents=True, exist_ok=True)

    stories = []
    for i in range(3):
        story_id = str(uuid.uuid4())
        content = f"# Story {i+1}\n\nThis is test story {i+1}."
        metadata = {
            "id": story_id,
            "summary": f"Test Story {i+1}",
            "repo_name": "test-repo",
            "created_at": "2026-01-05T10:00:00Z",
            "commit_shas": [f"abc{i}123"],
            "needs_review": i == 0,  # First story needs review
            "confidence": "high" if i > 0 else "medium",
        }
        save_story(content, metadata, story_id)
        stories.append(metadata)

    return stories


@pytest.fixture
def ci_mode(monkeypatch):
    """Enable CI mode via environment variable."""
    monkeypatch.setenv("REPR_CI", "true")

    # Reload config to pick up env var
    import repr.config
    import importlib
    importlib.reload(repr.config)


@pytest.fixture
def local_mode(monkeypatch):
    """Force local mode via environment variable."""
    monkeypatch.setenv("REPR_MODE", "local")

    # Reload config
    import repr.config
    import importlib
    importlib.reload(repr.config)


@pytest.fixture
def cloud_mode(monkeypatch):
    """Force cloud mode via environment variable."""
    monkeypatch.setenv("REPR_MODE", "cloud")

    # Reload config
    import repr.config
    import importlib
    importlib.reload(repr.config)
