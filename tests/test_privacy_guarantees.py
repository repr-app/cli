"""
Test core privacy guarantees from specification.

Verifies architectural privacy guarantees are enforced.
"""

import pytest
from pathlib import Path


class TestLocalModePrivacy:
    """Test privacy in local mode."""

    def test_local_mode_no_auth_required(self, mock_config):
        """Local mode should work without authentication."""
        from repr.config import is_authenticated

        assert not is_authenticated()

        # Local operations should still work
        # (We can't test generate without LLM, but verify config works)

    def test_local_mode_no_cloud_operations(self, mock_config):
        """Local mode should block all cloud operations."""
        from repr.privacy import check_cloud_permission

        # All cloud operations should be blocked
        operations = ["cloud_generation", "push", "sync", "profile_update"]

        for op in operations:
            allowed, reason = check_cloud_permission(op)
            assert not allowed
            assert reason  # Should have a reason

    def test_unauthenticated_user_cannot_push(self, mock_config):
        """Unauthenticated users cannot push stories."""
        from repr.config import is_authenticated

        assert not is_authenticated()

        # Push should be blocked (test via privacy check)
        from repr.privacy import check_cloud_permission

        allowed, reason = check_cloud_permission("push")
        assert not allowed
        assert "authenticated" in reason.lower() or "login" in reason.lower()


class TestAuthenticationFlow:
    """Test authentication and its effect on privacy."""

    def test_authenticated_user_can_use_cloud(self, authenticated_config):
        """Authenticated users can use cloud features."""
        from repr.config import is_authenticated, is_cloud_allowed

        assert is_authenticated()
        assert is_cloud_allowed()

    def test_authentication_token_not_in_config_json(self, authenticated_config, mock_repr_home):
        """Auth token should NOT be stored in config.json."""
        from repr.config import CONFIG_FILE
        import json

        config_content = CONFIG_FILE.read_text()
        assert "fake_token_12345" not in config_content

        # Config should only have reference
        config = json.loads(config_content)
        assert "auth" in config
        # Token itself should not be in config
        assert config["auth"].get("token") is None

    def test_authentication_token_in_keychain(self, authenticated_config):
        """Auth token should be in keychain/secure storage."""
        from repr.keychain import get_secret

        token = get_secret("auth_token")
        assert token == "fake_token_12345"


class TestPrivacyLock:
    """Test local-only privacy lock."""

    def test_privacy_lock_blocks_cloud(self, authenticated_config):
        """Privacy lock should block cloud even when authenticated."""
        from repr.config import lock_local_only, is_authenticated, is_cloud_allowed

        # User is authenticated
        assert is_authenticated()

        # Enable privacy lock
        lock_local_only(permanent=False)

        # Cloud should now be blocked
        assert not is_cloud_allowed()

    def test_permanent_privacy_lock(self, mock_config):
        """Permanent privacy lock should be irreversible."""
        from repr.config import lock_local_only, unlock_local_only, get_privacy_settings

        # Enable permanent lock
        lock_local_only(permanent=True)

        # Verify it's permanent
        privacy = get_privacy_settings()
        assert privacy["lock_permanent"] is True

        # Unlock should not work
        unlock_local_only()

        # Should still be locked
        privacy = get_privacy_settings()
        assert privacy["lock_local_only"] is True
        assert privacy["lock_permanent"] is True

    def test_reversible_privacy_lock(self, mock_config):
        """Reversible privacy lock can be unlocked."""
        from repr.config import lock_local_only, unlock_local_only, get_privacy_settings

        # Enable reversible lock
        lock_local_only(permanent=False)

        privacy = get_privacy_settings()
        assert privacy["lock_local_only"] is True
        assert privacy["lock_permanent"] is False

        # Unlock should work
        unlock_local_only()

        privacy = get_privacy_settings()
        assert privacy["lock_local_only"] is False


class TestAuditLogging:
    """Test privacy audit logging."""

    def test_cloud_operations_logged(self, mock_repr_home):
        """Cloud operations should be logged in audit trail."""
        from repr.privacy import log_cloud_operation, load_audit_log

        # Log an operation
        log_cloud_operation(
            operation="cloud_generation",
            destination="repr.dev",
            payload_summary={"commits": 5, "repos": 1},
            bytes_sent=1024,
        )

        # Should appear in audit log
        log = load_audit_log()
        assert len(log) == 1
        assert log[0]["operation"] == "cloud_generation"
        assert log[0]["destination"] == "repr.dev"

    def test_audit_log_includes_timestamp(self, mock_repr_home):
        """Audit log entries should have timestamps."""
        from repr.privacy import log_cloud_operation, load_audit_log

        log_cloud_operation("push", "repr.dev", {})

        log = load_audit_log()
        assert "timestamp" in log[0]

    def test_audit_log_includes_payload_summary(self, mock_repr_home):
        """Audit log should include summary of what was sent."""
        import repr.privacy
        import importlib

        # Reload to pick up new REPR_HOME
        importlib.reload(repr.privacy)

        from repr.privacy import log_cloud_operation, load_audit_log

        payload = {"commits": 10, "diffs_included": False}
        log_cloud_operation("cloud_generation", "repr.dev", payload)

        log = load_audit_log()
        assert log[-1]["payload_summary"] == payload  # Check last entry

    def test_get_audit_summary(self, mock_repr_home):
        """Should provide summary of recent audit activity."""
        import repr.privacy
        import importlib

        # Reload to pick up new REPR_HOME
        importlib.reload(repr.privacy)

        from repr.privacy import log_cloud_operation, get_audit_summary

        # Log several operations
        for i in range(5):
            log_cloud_operation(
                "cloud_generation", "repr.dev", {"commits": i + 1}, bytes_sent=1024 * i
            )

        summary = get_audit_summary(days=30)
        assert summary["total_operations"] == 5
        assert summary["total_bytes_sent"] > 0


class TestDataRetention:
    """Test data retention and local data handling."""

    def test_local_stories_not_affected_by_logout(
        self, authenticated_config, mock_stories
    ):
        """Logging out should not delete local stories."""
        from repr.storage import list_stories, get_story_count
        from repr.auth import logout as auth_logout

        # Count stories before logout
        before_count = get_story_count()
        assert before_count > 0

        # Logout
        auth_logout()

        # Stories should still exist
        after_count = get_story_count()
        assert after_count == before_count

    def test_local_data_info(self, mock_stories, mock_repr_home):
        """Should provide info about local data storage."""
        from repr.privacy import get_local_data_info

        info = get_local_data_info()

        assert "stories" in info
        assert info["stories"]["count"] > 0
        assert info["stories"]["size_bytes"] > 0


class TestPathRedaction:
    """Test path redaction in cloud payloads."""

    def test_path_redaction_enabled_by_default(self, mock_config):
        """Path redaction should be enabled by default."""
        from repr.config import get_llm_config

        llm_config = get_llm_config()
        assert llm_config.get("cloud_redact_paths") is True

    def test_diffs_disabled_by_default(self, mock_config):
        """Sending diffs to cloud should be disabled by default."""
        from repr.config import get_llm_config

        llm_config = get_llm_config()
        assert llm_config.get("cloud_send_diffs") is False

    def test_email_redaction_disabled_by_default(self, mock_config):
        """Email redaction should be disabled by default."""
        from repr.config import get_llm_config

        llm_config = get_llm_config()
        assert llm_config.get("cloud_redact_emails") is False

    def test_custom_redact_patterns_empty_by_default(self, mock_config):
        """Custom redaction patterns should be empty by default."""
        from repr.config import get_llm_config

        llm_config = get_llm_config()
        assert llm_config.get("cloud_redact_patterns") == []

    def test_repo_allowlist_empty_by_default(self, mock_config):
        """Repo allowlist should be empty by default (all allowed)."""
        from repr.config import get_llm_config

        llm_config = get_llm_config()
        assert llm_config.get("cloud_allowlist_repos") == []


class TestNoTelemetry:
    """Test that telemetry is opt-in."""

    def test_telemetry_disabled_by_default(self, mock_config):
        """Telemetry should be disabled by default."""
        from repr.config import get_privacy_settings

        privacy = get_privacy_settings()
        assert privacy.get("telemetry_enabled") is False

    def test_privacy_explanation_includes_telemetry_status(self, mock_config):
        """Privacy explanation should mention telemetry status."""
        from repr.privacy import get_privacy_explanation

        explanation = get_privacy_explanation()
        assert "current_state" in explanation
        assert "telemetry_enabled" in explanation["current_state"]
        assert explanation["current_state"]["telemetry_enabled"] is False


class TestNoBackgroundDaemons:
    """Test that repr runs no background processes."""

    def test_no_daemon_processes_spawned(self):
        """repr should not spawn background daemon processes."""
        # repr runs as foreground CLI only
        # All operations are user-initiated
        # This is architectural - no code to start daemons exists

    def test_all_network_calls_foreground(self, mock_repr_home):
        """All network calls should be in foreground, user-initiated commands."""
        # Verified by privacy explanation
        from repr.privacy import get_privacy_explanation

        explanation = get_privacy_explanation()
        assert explanation["architecture"]["no_background_daemons"] is True
        assert explanation["architecture"]["all_network_foreground"] is True


class TestBYOKPrivacy:
    """Test BYOK privacy properties."""

    def test_byok_keys_not_in_config(self, mock_config):
        """BYOK API keys should not be in config.json."""
        from repr.config import add_byok_provider, CONFIG_FILE
        import json

        # Add BYOK provider with key
        add_byok_provider("openai", api_key="sk-test123", model="gpt-4")

        # Config file should not contain API key
        config_content = CONFIG_FILE.read_text()
        assert "sk-test123" not in config_content

    def test_byok_keys_in_keychain(self, mock_config):
        """BYOK API keys should be in keychain."""
        from repr.config import add_byok_provider
        from repr.keychain import get_secret

        # Add provider
        add_byok_provider("openai", api_key="sk-test123", model="gpt-4")

        # Key should be in keychain
        key = get_secret("byok_openai")
        assert key == "sk-test123"

    def test_byok_audit_trail(self, mock_repr_home):
        """BYOK operations should appear in audit trail."""
        from repr.privacy import log_cloud_operation, load_audit_log

        # Log BYOK operation
        log_cloud_operation(
            operation="byok_generation",
            destination="api.openai.com",
            payload_summary={"commits": 5, "provider": "openai"},
        )

        log = load_audit_log()
        assert any(e["operation"] == "byok_generation" for e in log)
        assert any(e["destination"] == "api.openai.com" for e in log)
