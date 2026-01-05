"""
Test multi-user & CI safety (environment variables).

Verifies Gap #3: REPR_HOME, REPR_MODE, REPR_CI should be respected.
Status: ✅ IMPLEMENTED
"""

import os
import pytest
from pathlib import Path


class TestReprHomeVariable:
    """Test REPR_HOME environment variable."""

    def test_repr_home_defaults_to_home_repr(self, monkeypatch, temp_dir):
        """REPR_HOME should default to ~/.repr if not set."""
        # Unset REPR_HOME
        monkeypatch.delenv("REPR_HOME", raising=False)

        # Reload config
        import repr.config
        import importlib
        importlib.reload(repr.config)

        # Should use home directory
        assert repr.config.REPR_HOME == Path.home() / ".repr"

    def test_repr_home_override(self, monkeypatch, temp_dir):
        """REPR_HOME can be overridden via environment variable."""
        custom_home = temp_dir / "custom_repr"
        monkeypatch.setenv("REPR_HOME", str(custom_home))

        # Reload config
        import repr.config
        import importlib
        importlib.reload(repr.config)

        # Should use custom path
        assert repr.config.REPR_HOME == custom_home
        assert repr.config.CONFIG_DIR == custom_home

    def test_repr_home_used_by_keychain(self, monkeypatch, temp_dir):
        """Keychain module should respect REPR_HOME."""
        custom_home = temp_dir / "custom_repr"
        monkeypatch.setenv("REPR_HOME", str(custom_home))

        # Reload modules (keychain first, then config)
        import repr.config
        import repr.keychain
        import importlib
        importlib.reload(repr.keychain)
        importlib.reload(repr.config)

        # Keychain should use custom home
        assert repr.keychain.REPR_HOME == custom_home

    def test_repr_home_used_by_storage(self, monkeypatch, temp_dir):
        """Storage module should respect REPR_HOME."""
        custom_home = temp_dir / "custom_repr"
        monkeypatch.setenv("REPR_HOME", str(custom_home))

        # Reload modules
        import repr.config
        import repr.storage
        import importlib
        importlib.reload(repr.config)
        importlib.reload(repr.storage)

        # Storage should use custom home
        assert repr.storage.REPR_HOME == custom_home
        assert repr.storage.STORIES_DIR == custom_home / "stories"

    def test_multi_user_isolation(self, monkeypatch, temp_dir):
        """Different REPR_HOME values should isolate users."""
        user1_home = temp_dir / "user1"
        user2_home = temp_dir / "user2"

        # User 1 config
        monkeypatch.setenv("REPR_HOME", str(user1_home))
        import repr.config
        import importlib
        importlib.reload(repr.config)

        from repr.config import save_config, DEFAULT_CONFIG
        user1_config = DEFAULT_CONFIG.copy()
        user1_config["profile"]["username"] = "user1"
        save_config(user1_config)

        # User 2 config
        monkeypatch.setenv("REPR_HOME", str(user2_home))
        importlib.reload(repr.config)

        from repr.config import save_config
        user2_config = DEFAULT_CONFIG.copy()
        user2_config["profile"]["username"] = "user2"
        save_config(user2_config)

        # Both configs should exist in different locations
        assert (user1_home / "config.json").exists()
        assert (user2_home / "config.json").exists()

        # Configs should be different
        import json
        u1_data = json.loads((user1_home / "config.json").read_text())
        u2_data = json.loads((user2_home / "config.json").read_text())
        assert u1_data["profile"]["username"] == "user1"
        assert u2_data["profile"]["username"] == "user2"


class TestReprModeVariable:
    """Test REPR_MODE environment variable."""

    def test_repr_mode_not_set(self, monkeypatch):
        """get_forced_mode should return None when REPR_MODE not set."""
        monkeypatch.delenv("REPR_MODE", raising=False)

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.get_forced_mode() is None

    def test_repr_mode_local(self, monkeypatch):
        """REPR_MODE=local should force local mode."""
        monkeypatch.setenv("REPR_MODE", "local")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.get_forced_mode() == "local"

    def test_repr_mode_cloud(self, monkeypatch):
        """REPR_MODE=cloud should force cloud mode."""
        monkeypatch.setenv("REPR_MODE", "cloud")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.get_forced_mode() == "cloud"

    def test_repr_mode_invalid_ignored(self, monkeypatch):
        """Invalid REPR_MODE values should be ignored."""
        monkeypatch.setenv("REPR_MODE", "invalid")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        # Should return None for invalid values
        assert repr.config.get_forced_mode() is None

    def test_repr_mode_local_blocks_cloud_when_authenticated(
        self, monkeypatch, authenticated_config
    ):
        """REPR_MODE=local should block cloud even when authenticated."""
        monkeypatch.setenv("REPR_MODE", "local")

        import repr.config
        import repr.privacy
        import importlib
        importlib.reload(repr.config)
        importlib.reload(repr.privacy)

        from repr.config import is_authenticated
        from repr.privacy import check_cloud_permission

        assert is_authenticated(), "Should be authenticated"

        # But cloud should be blocked
        allowed, reason = check_cloud_permission("cloud_generation")
        assert not allowed
        assert "Local mode forced" in reason


class TestReprCiVariable:
    """Test REPR_CI environment variable."""

    def test_repr_ci_not_set(self, monkeypatch):
        """is_ci_mode should return False when REPR_CI not set."""
        monkeypatch.delenv("REPR_CI", raising=False)

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.is_ci_mode() is False

    def test_repr_ci_true(self, monkeypatch):
        """REPR_CI=true should enable CI mode."""
        monkeypatch.setenv("REPR_CI", "true")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.is_ci_mode() is True

    def test_repr_ci_1(self, monkeypatch):
        """REPR_CI=1 should enable CI mode."""
        monkeypatch.setenv("REPR_CI", "1")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.is_ci_mode() is True

    def test_repr_ci_yes(self, monkeypatch):
        """REPR_CI=yes should enable CI mode."""
        monkeypatch.setenv("REPR_CI", "yes")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.is_ci_mode() is True

    def test_repr_ci_false(self, monkeypatch):
        """REPR_CI=false should not enable CI mode."""
        monkeypatch.setenv("REPR_CI", "false")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.is_ci_mode() is False

    def test_ci_mode_blocks_cloud(self, monkeypatch, mock_config):
        """CI mode should block cloud operations."""
        monkeypatch.setenv("REPR_CI", "true")

        import repr.config
        import repr.privacy
        import importlib
        importlib.reload(repr.config)
        importlib.reload(repr.privacy)

        from repr.config import is_ci_mode
        from repr.privacy import check_cloud_permission

        assert is_ci_mode()

        # Cloud should be blocked
        allowed, reason = check_cloud_permission("cloud_generation")
        assert not allowed
        assert "CI mode enabled" in reason


class TestCombinedEnvironmentVariables:
    """Test combinations of environment variables."""

    def test_custom_home_with_local_mode(self, monkeypatch, temp_dir):
        """REPR_HOME + REPR_MODE=local should work together."""
        custom_home = temp_dir / "custom"
        monkeypatch.setenv("REPR_HOME", str(custom_home))
        monkeypatch.setenv("REPR_MODE", "local")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.REPR_HOME == custom_home
        assert repr.config.get_forced_mode() == "local"

    def test_ci_mode_overrides_cloud_mode(self, monkeypatch, authenticated_config):
        """REPR_CI=true should block cloud even with REPR_MODE=cloud."""
        monkeypatch.setenv("REPR_CI", "true")
        monkeypatch.setenv("REPR_MODE", "cloud")

        import repr.config
        import repr.privacy
        import importlib
        importlib.reload(repr.config)
        importlib.reload(repr.privacy)

        from repr.privacy import check_cloud_permission

        # CI mode should win
        allowed, reason = check_cloud_permission("cloud_generation")
        assert not allowed
        assert "CI mode enabled" in reason

    def test_all_three_variables(self, monkeypatch, temp_dir):
        """Test all three environment variables together."""
        custom_home = temp_dir / "ci_custom"
        monkeypatch.setenv("REPR_HOME", str(custom_home))
        monkeypatch.setenv("REPR_MODE", "local")
        monkeypatch.setenv("REPR_CI", "true")

        import repr.config
        import importlib
        importlib.reload(repr.config)

        assert repr.config.REPR_HOME == custom_home
        assert repr.config.get_forced_mode() == "local"
        assert repr.config.is_ci_mode()


class TestCIUsageExample:
    """Test realistic CI environment usage."""

    def test_ci_workflow(self, monkeypatch, temp_dir):
        """Simulate a CI workflow with safe defaults."""
        # CI environment setup
        ci_home = temp_dir / "ci_repr"
        monkeypatch.setenv("REPR_HOME", str(ci_home))
        monkeypatch.setenv("REPR_CI", "true")
        monkeypatch.setenv("REPR_MODE", "local")

        import repr.config
        import repr.privacy
        import importlib
        importlib.reload(repr.config)
        importlib.reload(repr.privacy)

        from repr.config import is_ci_mode, get_forced_mode
        from repr.privacy import check_cloud_permission

        # Verify CI mode active
        assert is_ci_mode()
        assert get_forced_mode() == "local"

        # Verify cloud blocked
        allowed, _ = check_cloud_permission("cloud_generation")
        assert not allowed

        # Verify isolated data directory
        assert repr.config.REPR_HOME == ci_home

        # Should be able to init config
        from repr.config import save_config, DEFAULT_CONFIG
        save_config(DEFAULT_CONFIG)
        assert (ci_home / "config.json").exists()
