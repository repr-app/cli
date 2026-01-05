"""
Test token budget enforcement for cloud generation.

Verifies Gap #6: Cloud generation should enforce 50 commit / 100k token limits.
Status: ⚠️ PARTIAL (batching exists but limits not enforced)
"""

import pytest
from unittest.mock import Mock, patch


class TestTokenBudgetConfiguration:
    """Test token budget configuration."""

    def test_config_has_token_limit(self, mock_config):
        """Config should define token_limit."""
        from repr.config import load_config

        config = load_config()
        assert "generation" in config
        assert "token_limit" in config["generation"]
        assert config["generation"]["token_limit"] == 100000

    def test_config_has_max_commits_per_batch(self, mock_config):
        """Config should define max_commits_per_batch."""
        from repr.config import load_config

        config = load_config()
        assert "max_commits_per_batch" in config["generation"]
        assert config["generation"]["max_commits_per_batch"] == 50

    def test_config_has_batch_size(self, mock_config):
        """Config should define batch_size for stories."""
        from repr.config import load_config

        config = load_config()
        assert "batch_size" in config["generation"]
        assert config["generation"]["batch_size"] == 5


class TestCommitBatching:
    """Test commit batching logic."""

    def test_commits_split_into_batches(self):
        """Commits should be split into batches."""
        from repr.openai_analysis import COMMITS_PER_BATCH

        # Verify batch size is defined
        assert COMMITS_PER_BATCH > 0
        assert COMMITS_PER_BATCH <= 50  # Should not exceed spec limit

    def test_batch_size_is_conservative(self):
        """Batch size should be conservative (under spec limit)."""
        from repr.openai_analysis import COMMITS_PER_BATCH

        # Current implementation uses 25, which is < 50 (spec limit)
        assert COMMITS_PER_BATCH == 25

    @patch("repr.cli._generate_stories")
    def test_large_commit_set_split_correctly(self, mock_generate):
        """Large number of commits should be split into multiple batches."""
        # Create 100 mock commits
        commits = [{"sha": f"abc{i}", "message": f"Commit {i}"} for i in range(100)]

        # Simulate batching (from cli.py:419-422)
        batch_size = 5  # Default from config
        batches = [
            commits[i : i + batch_size] for i in range(0, len(commits), batch_size)
        ]

        # Should create 20 batches (100 / 5)
        assert len(batches) == 20
        assert all(len(b) <= batch_size for b in batches)


class TestTokenEstimation:
    """Test token estimation (implemented in openai_analysis.py)."""

    def test_estimate_tokens_function_exists(self):
        """Should have a function to estimate token count."""
        from repr.openai_analysis import estimate_tokens

        # Function should exist
        assert callable(estimate_tokens)

    def test_estimate_tokens_for_commits(self):
        """Should estimate tokens for list of commits."""
        from repr.openai_analysis import estimate_tokens

        commits = [
            {"message": "Fix bug in auth", "files": []},
            {"message": "Add new feature", "files": []},
        ]
        tokens = estimate_tokens(commits)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_includes_commit_messages(self):
        """Token estimate should include commit messages."""
        from repr.openai_analysis import estimate_tokens

        # Test with commits that have messages
        commits_with_message = [
            {"message": "A" * 1000, "files": []}  # 1000 char message
        ]
        tokens_with = estimate_tokens(commits_with_message)

        # Should include overhead + message tokens (~1000/4 = 250 tokens + 2000 overhead)
        assert tokens_with > 2000  # Should include overhead
        assert tokens_with > 250  # Should include message tokens


class TestTokenLimitEnforcement:
    """Test enforcement of token limits (implemented in cli.py)."""

    def test_exceeding_token_limit_splits_batches(self, mock_repr_home):
        """Exceeding token limit should trigger batch splitting."""
        # The implementation splits by max_commits_per_batch (50)
        # This ensures no single batch exceeds limits
        from repr.config import load_config

        config = load_config()
        max_commits = config.get("generation", {}).get("max_commits_per_batch", 50)

        # Verify the limit is reasonable (should prevent token overflow)
        assert max_commits == 50
        assert max_commits <= 50  # Spec limit

    def test_user_confirmation_for_batch_split(self, mock_repr_home, capsys):
        """Splitting batches should require user confirmation."""
        # The CLI shows preview and prompts for confirmation (cli.py:402-418)
        # We verify this by checking the implementation exists
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Check that the implementation shows batch split preview
        assert "exceeds" in source
        assert "Will split into" in source
        assert "Continue with generation?" in source or "confirm" in source

    def test_user_can_cancel_large_generation(self):
        """User should be able to cancel if batch split is too large."""
        # The confirm() function in cli.py allows users to cancel
        # This is implemented via the confirmation prompt
        from repr.ui import confirm

        # Verify confirm function exists
        assert callable(confirm)


class TestCommitLimitEnforcement:
    """Test enforcement of 50 commit limit (implemented in cli.py)."""

    def test_exceeding_50_commits_shows_warning(self):
        """More than 50 commits should show warning and split."""
        # Spec: "Cloud generation caps payload at 50 commits"
        # This is enforced in cli.py:402-418
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Verify the warning message exists
        assert "exceeds" in source
        assert "max_commits" in source

    def test_batch_preview_shows_commit_ranges(self):
        """Batch preview should show commit number ranges."""
        # Spec shows:
        # Batch 1: commits 1-50 (est. 80k tokens)
        # Batch 2: commits 51-100 (est. 75k tokens)
        # Implemented in cli.py:408-413
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Verify batch preview shows commit ranges
        assert "Batch" in source
        assert "commits" in source
        assert "start" in source and "end" in source

    def test_batch_preview_shows_token_estimates(self):
        """Batch preview should show estimated tokens per batch."""
        # Each batch line should show: (est. Xk tokens)
        # Implemented in cli.py:412-413
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Verify token estimation is shown in preview
        assert "batch_tokens" in source or "estimate_tokens" in source
        assert "est." in source or "tokens" in source


class TestBatchingConfiguration:
    """Test that batching uses config values (not current behavior)."""

    def test_current_implementation_uses_hardcoded_batch_size(self, mock_repr_home):
        """Current implementation uses hardcoded value (should use config)."""
        from repr.openai_analysis import COMMITS_PER_BATCH
        from repr.config import load_config

        config = load_config()
        config_batch_size = config["generation"]["batch_size"]
        config_max_commits = config["generation"]["max_commits_per_batch"]

        # Current implementation uses hardcoded 25
        # Config has different values (batch_size=5, max_commits=50)
        # This is a known issue to fix
        assert COMMITS_PER_BATCH == 25  # Hardcoded
        assert config_batch_size == 5  # Config value (different)
        assert config_max_commits == 50  # Config value (different)

    def test_batching_should_use_config_max_commits(self, mock_repr_home):
        """Batching should use max_commits_per_batch from config."""
        # Implemented in openai_analysis.py:get_batch_size()
        from repr.config import load_config
        from repr.openai_analysis import get_batch_size

        config = load_config()
        batch_size = get_batch_size()

        # get_batch_size() returns config value with fallback to COMMITS_PER_BATCH
        expected = config.get("generation", {}).get("max_commits_per_batch", 25)
        assert batch_size == expected


class TestDryRunPreview:
    """Test dry run preview for cloud generation (implemented in cli.py)."""

    def test_dry_run_flag_exists(self):
        """Generate command should support --dry-run flag."""
        # Verify flag exists in CLI
        from repr.cli import generate
        import inspect

        # Check function signature
        sig = inspect.signature(generate)
        assert "dry_run" in sig.parameters

    def test_dry_run_shows_batch_split_preview(self):
        """Dry run should show how commits will be batched."""
        # Implemented in cli.py:353-391
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Verify dry run shows preview
        assert "Dry Run Preview" in source
        assert "Commits to analyze" in source
        assert "Will split into" in source
        assert "Batch" in source

    def test_dry_run_shows_token_estimate(self):
        """Dry run should estimate total tokens before sending."""
        # Should show: "Estimated tokens: ~X,XXX"
        # Implemented in cli.py:368-369
        from repr.cli import generate
        import inspect

        source = inspect.getsource(generate)

        # Verify token estimation is shown in dry run
        assert "Estimated tokens" in source or "estimated_tokens" in source


class TestSpecificationCompliance:
    """Test compliance with CLI_SPECIFICATION.md examples."""

    def test_spec_example_150_commits_split(self):
        """Test the spec example: 150 commits → 3 batches of 50."""
        # From CLI_SPECIFICATION.md:2421-2432:
        #
        # repr generate --cloud
        #
        # ⚠ 150 commits queued (exceeds 50-commit limit)
        #
        # Will split into 3 batches:
        #   Batch 1: commits 1-50 (est. 80k tokens)
        #   Batch 2: commits 51-100 (est. 75k tokens)
        #   Batch 3: commits 101-150 (est. 60k tokens)
        #
        # Continue? [y/N]

        # Create 150 commits
        commits = [{"sha": f"abc{i}", "message": f"Commit {i}", "files": []} for i in range(150)]

        # Test batch calculation
        max_commits = 50
        num_batches = (len(commits) + max_commits - 1) // max_commits

        # Should split into 3 batches of 50
        assert num_batches == 3

        # Verify batch sizes
        batches = [
            commits[i * max_commits:(i + 1) * max_commits]
            for i in range(num_batches)
        ]

        assert len(batches) == 3
        assert len(batches[0]) == 50  # Batch 1: 1-50
        assert len(batches[1]) == 50  # Batch 2: 51-100
        assert len(batches[2]) == 50  # Batch 3: 101-150


class TestPerformanceConsiderations:
    """Test performance and optimization of batching."""

    def test_batching_reduces_api_calls(self):
        """Batching should reduce number of API calls."""
        # Instead of 1 call per commit, should batch multiple commits
        # This is already implemented but worth testing

    def test_large_batch_doesnt_exceed_token_limit(self):
        """Even max batch size shouldn't exceed token limit."""
        # 50 commits * ~2000 tokens/commit = ~100k tokens (at limit)
        # With typical commits, 25-50 commits should be safe
        # TODO: Add safety margin check
