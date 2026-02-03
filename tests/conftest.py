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


def _force_cleanup_git_repo(path: Path) -> None:
    """Force cleanup of git repo files on Windows.
    
    On Windows, git processes may hold file handles that prevent deletion.
    This function forcibly closes any git handles and retries deletion.
    """
    import gc
    import shutil
    import sys
    import time
    
    # Force garbage collection to release any git objects
    gc.collect()
    
    if sys.platform == "win32":
        # On Windows, give git processes time to release handles
        time.sleep(0.1)
        
        # Retry deletion with exponential backoff
        for i in range(5):
            try:
                shutil.rmtree(path, ignore_errors=False)
                return
            except PermissionError:
                gc.collect()
                time.sleep(0.1 * (2 ** i))
        
        # Final attempt with ignore_errors
        shutil.rmtree(path, ignore_errors=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    tmpdir = tempfile.mkdtemp()
    try:
        yield Path(tmpdir)
    finally:
        _force_cleanup_git_repo(Path(tmpdir))


@pytest.fixture
def mock_repr_home(temp_dir: Path, monkeypatch) -> Path:
    """Mock ~/.repr directory using REPR_HOME env var."""
    repr_home = temp_dir / ".repr"
    repr_home.mkdir()
    monkeypatch.setenv("REPR_HOME", str(repr_home))

    # Reload modules to pick up new env var
    import repr.config
    import repr.keychain
    import repr.storage
    import repr.db
    import importlib
    importlib.reload(repr.keychain)
    importlib.reload(repr.config)
    importlib.reload(repr.storage)
    importlib.reload(repr.db)

    # Reset the database singleton so it picks up the new path
    repr.db.reset_db_instance()

    return repr_home


@pytest.fixture
def mock_git_repo(temp_dir: Path) -> Generator[Repo, None, None]:
    """Create a mock git repository for testing."""
    import gc
    
    repo_path = temp_dir / "test-repo"
    repo_path.mkdir()

    # Initialize git repo
    repo = Repo.init(repo_path)

    # Configure git user
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repository")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    yield repo
    
    # Cleanup: close git repo to release file handles (important on Windows)
    repo.close()
    gc.collect()


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
    """Create mock story files and database entries."""
    import repr.storage
    import repr.db
    import importlib
    from datetime import datetime, timezone

    # Reload storage module to pick up new REPR_HOME
    importlib.reload(repr.storage)
    importlib.reload(repr.db)
    repr.db.reset_db_instance()

    from repr.storage import STORIES_DIR, save_story
    from repr.db import get_db
    from repr.models import Story

    STORIES_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database and register a test project
    db = get_db()
    project_id = db.register_project(mock_repr_home.parent / "test-repo", "test-repo")

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
        # Save to files (for file-based storage operations)
        save_story(content, metadata, story_id)
        stories.append(metadata)

        # Also save to database (for database-backed list_stories in cli.py)
        story_obj = Story(
            id=story_id,
            created_at=datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime.now(timezone.utc),
            project_id=project_id,
            title=f"Test Story {i+1}",
            problem="Test problem",
            approach="Test approach",
            commit_shas=[f"abc{i}123"],
            category="feature",
        )
        db.save_story(story_obj, project_id)

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
