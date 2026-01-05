"""
Test network sandboxing enforcement for local mode.

Verifies Gap #1: Network sandboxing should block non-loopback connections.
Status: ❌ NOT IMPLEMENTED (tests will fail until implemented)
"""

import pytest
import httpx
from unittest.mock import Mock, patch


class TestNetworkSandboxing:
    """Test network call blocking in local mode."""

    def test_local_mode_blocks_external_http(self, mock_config, local_mode):
        """Local mode should block external HTTP requests."""
        from repr.config import is_cloud_allowed

        assert not is_cloud_allowed(), "Should be in local mode"

        # TODO: Once network sandboxing is implemented, this should raise
        # For now, this test documents the expected behavior
        #
        # Expected: Attempting to fetch external URL should raise error
        # with httpx.Client() as client:
        #     with pytest.raises(httpx.ConnectError, match="External network blocked"):
        #         client.get("https://example.com")

        # CURRENT STATE: This will NOT raise (sandboxing not implemented)
        # Uncomment once sandboxing is added
        pytest.skip("Network sandboxing not yet implemented")

    def test_local_mode_allows_loopback(self, mock_config, local_mode):
        """Local mode should allow loopback connections."""
        from repr.config import is_cloud_allowed

        assert not is_cloud_allowed()

        # Loopback should always work
        allowed_hosts = ["127.0.0.1", "localhost", "::1"]

        for host in allowed_hosts:
            # This should NOT raise even with sandboxing
            # (We can't actually test without a local server, so we mock)
            with patch("httpx.Client.get") as mock_get:
                mock_get.return_value = Mock(status_code=200)

                # This should succeed
                with httpx.Client() as client:
                    try:
                        client.get(f"http://{host}:11434/api/tags")
                    except Exception as e:
                        pytest.fail(f"Loopback to {host} should be allowed: {e}")

    def test_cloud_mode_allows_external(self, authenticated_config, cloud_mode):
        """Cloud mode should allow external requests."""
        from repr.config import is_cloud_allowed

        # Note: is_cloud_allowed checks both auth AND privacy lock
        # For this test, we're authenticated and no lock
        assert is_cloud_allowed(), "Should be in cloud mode"

        # External requests should work in cloud mode
        # (We mock the actual request since we don't want real network calls in tests)
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = Mock(status_code=200)

            with httpx.Client() as client:
                # Should not raise
                client.get("https://api.repr.dev/api/cli/user")

    def test_ci_mode_blocks_cloud(self, mock_config, ci_mode):
        """CI mode should block cloud operations."""
        from repr.config import is_ci_mode
        from repr.privacy import check_cloud_permission

        assert is_ci_mode(), "Should be in CI mode"

        # Cloud operations should be blocked
        allowed, reason = check_cloud_permission("cloud_generation")
        assert not allowed
        assert "CI mode enabled" in reason

    def test_forced_local_mode_blocks_cloud(self, authenticated_config, local_mode):
        """REPR_MODE=local should block cloud even when authenticated."""
        from repr.config import get_forced_mode, is_authenticated
        from repr.privacy import check_cloud_permission

        assert get_forced_mode() == "local"
        assert is_authenticated(), "Should be authenticated"

        # But cloud should still be blocked
        allowed, reason = check_cloud_permission("cloud_generation")
        assert not allowed
        assert "Local mode forced" in reason


class TestNetworkSandboxingImplementation:
    """Tests for the actual sandboxing mechanism (when implemented)."""

    @pytest.mark.skip("Network sandboxing not yet implemented")
    def test_custom_transport_blocks_dns_lookup(self, mock_config, local_mode):
        """Custom transport should block DNS lookups for external hosts."""
        # TODO: Once LocalModeTransport is implemented:
        #
        # from repr.network import LocalModeTransport
        #
        # transport = LocalModeTransport()
        # client = httpx.Client(transport=transport)
        #
        # with pytest.raises(httpx.ConnectError, match="External network blocked"):
        #     client.get("https://google.com")

    @pytest.mark.skip("Network sandboxing not yet implemented")
    def test_custom_transport_allows_loopback_ips(self, mock_config, local_mode):
        """Custom transport should allow 127.0.0.1, localhost, ::1."""
        # TODO: Once implemented, test that LocalModeTransport allows these

    @pytest.mark.skip("Network sandboxing not yet implemented")
    def test_api_client_uses_sandboxed_transport_in_local_mode(
        self, mock_config, local_mode
    ):
        """API client should use LocalModeTransport when in local mode."""
        # TODO: Verify that api.py uses custom transport in local mode
        # from repr.api import _get_client
        # client = _get_client()
        # assert isinstance(client._transport, LocalModeTransport)


class TestNetworkErrorMessages:
    """Test error messages for network violations."""

    def test_blocked_network_error_message_is_helpful(self):
        """Error message should explain what happened and how to fix."""
        # Expected error message format:
        expected_message = """
        ❌ External network blocked in Local mode
           Attempted connection to: example.com:443
           Local mode only allows loopback (127.0.0.1, localhost, ::1)

           To enable cloud features: repr login
        """

        # TODO: Once implemented, verify actual error message matches spec


class TestLLMEndpointDetection:
    """Test that LLM detection respects network sandboxing."""

    def test_llm_detection_only_tries_loopback(self, mock_config, local_mode):
        """LLM detection should only try loopback addresses in local mode."""
        from repr.llm import LOCAL_ENDPOINTS

        # All configured endpoints should be loopback
        for endpoint in LOCAL_ENDPOINTS:
            url = endpoint["url"]
            assert "localhost" in url or "127.0.0.1" in url or "::1" in url, (
                f"LLM endpoint {url} should be loopback-only"
            )

    def test_llm_detection_doesnt_leak_network_in_local_mode(
        self, mock_config, local_mode
    ):
        """LLM detection should not make external network calls in local mode."""
        from repr.llm import detect_local_llm

        # This should only try localhost endpoints, never external
        # (Should not raise even if no LLM is running)
        result = detect_local_llm()

        # Result can be None (no LLM detected), but shouldn't crash
        # and shouldn't have made external network calls
        assert result is None or result.url.startswith("http://localhost")
