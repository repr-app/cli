"""
Test commit deduplication in story generation.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from repr.storage import (
    get_processed_commit_shas,
    save_story,
    STORIES_DIR,
)


@pytest.fixture
def temp_stories_dir(monkeypatch):
    """Use a temporary directory for stories during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        stories_dir = Path(tmpdir) / "stories"
        stories_dir.mkdir()
        monkeypatch.setattr("repr.storage.STORIES_DIR", stories_dir)
        yield stories_dir


def test_get_processed_commit_shas_empty(temp_stories_dir):
    """Test getting processed commits when no stories exist."""
    processed = get_processed_commit_shas()
    assert processed == set()


def test_get_processed_commit_shas_single_story(temp_stories_dir):
    """Test getting processed commits from a single story."""
    # Save a story with some commits
    metadata = {
        "repo_name": "test-repo",
        "commit_shas": ["abc123", "def456", "ghi789"],
    }
    save_story("Test story content", metadata)
    
    # Get processed commits
    processed = get_processed_commit_shas()
    assert processed == {"abc123", "def456", "ghi789"}


def test_get_processed_commit_shas_multiple_stories(temp_stories_dir):
    """Test getting processed commits from multiple stories."""
    # Save multiple stories
    save_story("Story 1", {
        "repo_name": "test-repo",
        "commit_shas": ["abc123", "def456"],
    })
    save_story("Story 2", {
        "repo_name": "test-repo",
        "commit_shas": ["ghi789", "jkl012"],
    })
    save_story("Story 3", {
        "repo_name": "test-repo",
        "commit_shas": ["def456", "mno345"],  # def456 is duplicate
    })
    
    # Get all processed commits
    processed = get_processed_commit_shas()
    assert processed == {"abc123", "def456", "ghi789", "jkl012", "mno345"}


def test_get_processed_commit_shas_filter_by_repo(temp_stories_dir):
    """Test filtering processed commits by repository."""
    # Save stories for different repos
    save_story("Story 1", {
        "repo_name": "repo-a",
        "commit_shas": ["abc123", "def456"],
    })
    save_story("Story 2", {
        "repo_name": "repo-b",
        "commit_shas": ["ghi789", "jkl012"],
    })
    save_story("Story 3", {
        "repo_name": "repo-a",
        "commit_shas": ["mno345"],
    })
    
    # Get processed commits for repo-a only
    processed_a = get_processed_commit_shas(repo_name="repo-a")
    assert processed_a == {"abc123", "def456", "mno345"}
    
    # Get processed commits for repo-b only
    processed_b = get_processed_commit_shas(repo_name="repo-b")
    assert processed_b == {"ghi789", "jkl012"}


def test_get_processed_commit_shas_handles_missing_field(temp_stories_dir):
    """Test handling stories without commit_shas field."""
    # Save a story without commit_shas
    save_story("Story without commits", {
        "repo_name": "test-repo",
        "summary": "Test story",
    })
    
    # Should not crash, just return empty set
    processed = get_processed_commit_shas()
    assert processed == set()


def test_get_processed_commit_shas_handles_corrupt_json(temp_stories_dir):
    """Test handling corrupt JSON files."""
    # Create a corrupt JSON file
    corrupt_file = temp_stories_dir / "corrupt.json"
    corrupt_file.write_text("{ invalid json }")
    
    # Should not crash, just skip the corrupt file
    processed = get_processed_commit_shas()
    assert processed == set()


def test_commit_filtering_in_generate(temp_stories_dir):
    """Test that generate command filters out processed commits."""
    # Save a story with some commits
    save_story("Existing story", {
        "repo_name": "test-repo",
        "commit_shas": ["abc123", "def456"],
    })
    
    # Simulate commit list from git
    all_commits = [
        {"full_sha": "abc123", "message": "Already processed 1"},
        {"full_sha": "def456", "message": "Already processed 2"},
        {"full_sha": "ghi789", "message": "New commit 1"},
        {"full_sha": "jkl012", "message": "New commit 2"},
    ]
    
    # Filter out processed commits
    processed_shas = get_processed_commit_shas(repo_name="test-repo")
    filtered_commits = [c for c in all_commits if c["full_sha"] not in processed_shas]
    
    # Should only have the new commits
    assert len(filtered_commits) == 2
    assert filtered_commits[0]["full_sha"] == "ghi789"
    assert filtered_commits[1]["full_sha"] == "jkl012"

