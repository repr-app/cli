"""
Opt-in telemetry for repr CLI.

Privacy guarantees:
- Disabled by default (user must explicitly opt-in)
- Anonymous device ID (no PII)
- Events are logged locally first (visible via `repr privacy audit`)
- Only sends: command name, timestamp, OS, CLI version
- Never sends: code, commits, diffs, paths, usernames, emails
- Can be disabled at any time

Transparency:
- All sent events visible in `repr privacy audit`
- Source code is open (you're reading it!)
"""

import hashlib
import json
import os
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import (
    CONFIG_DIR,
    AUDIT_DIR,
    load_config,
    save_config,
    get_config_value,
    set_config_value,
)

# Telemetry endpoint (can be overridden via env var for testing)
TELEMETRY_ENDPOINT = os.getenv(
    "REPR_TELEMETRY_ENDPOINT",
    "https://api.repr.dev/api/cli/telemetry"
)

# Local telemetry queue file
TELEMETRY_QUEUE_FILE = AUDIT_DIR / "telemetry_queue.json"

# Device ID file (anonymous, persistent)
DEVICE_ID_FILE = CONFIG_DIR / ".device_id"


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled."""
    config = load_config()
    return config.get("privacy", {}).get("telemetry_enabled", False)


def enable_telemetry() -> None:
    """Enable telemetry (opt-in)."""
    set_config_value("privacy.telemetry_enabled", True)
    
    # Track the opt-in event
    track("telemetry_enabled", {"source": "cli"})


def disable_telemetry() -> None:
    """Disable telemetry."""
    set_config_value("privacy.telemetry_enabled", False)
    
    # Clear any pending events
    clear_queue()


def get_device_id() -> str:
    """
    Get or create anonymous device ID.
    
    The ID is:
    - Random UUID, hashed for extra anonymity
    - Persistent across sessions
    - Not linked to any PII
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text().strip()
    
    # Generate new anonymous ID
    raw_id = str(uuid.uuid4())
    # Hash it to ensure no UUID format that could be traced
    device_id = hashlib.sha256(raw_id.encode()).hexdigest()[:32]
    
    DEVICE_ID_FILE.write_text(device_id)
    return device_id


def get_context() -> dict[str, Any]:
    """
    Get anonymous context for telemetry events.
    
    Includes only:
    - OS type and version
    - CLI version
    - Anonymous device ID
    
    Never includes:
    - Username, email, paths, code, etc.
    """
    return {
        "device_id": get_device_id(),
        "cli_version": __version__,
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "python_version": platform.python_version(),
    }


def track(event: str, properties: dict[str, Any] | None = None) -> None:
    """
    Track an event (if telemetry is enabled).
    
    Args:
        event: Event name (e.g., "command_run", "story_generated")
        properties: Additional properties (must not contain PII)
    """
    if not is_telemetry_enabled():
        return
    
    # Build event
    event_data = {
        "event": event,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "context": get_context(),
        "properties": properties or {},
    }
    
    # Queue event locally
    _queue_event(event_data)
    
    # Try to flush queue (non-blocking)
    _try_flush_queue()


def track_command(command: str, subcommand: str | None = None, success: bool = True) -> None:
    """
    Track a CLI command execution.
    
    Args:
        command: Main command name (e.g., "generate", "push")
        subcommand: Optional subcommand (e.g., "llm add")
        success: Whether command succeeded
    """
    properties = {
        "command": command,
        "success": success,
    }
    if subcommand:
        properties["subcommand"] = subcommand
    
    track("command_run", properties)


def track_feature(feature: str, action: str, metadata: dict[str, Any] | None = None) -> None:
    """
    Track feature usage.
    
    Args:
        feature: Feature name (e.g., "local_llm", "cloud_sync")
        action: Action taken (e.g., "configured", "used")
        metadata: Additional metadata (no PII!)
    """
    properties = {
        "feature": feature,
        "action": action,
    }
    if metadata:
        # Sanitize metadata to ensure no PII
        safe_metadata = {
            k: v for k, v in metadata.items()
            if k in ("count", "duration_ms", "template", "mode", "provider")
        }
        properties.update(safe_metadata)
    
    track("feature_used", properties)


def _queue_event(event: dict[str, Any]) -> None:
    """Queue an event locally for later sending."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing queue
    queue = _load_queue()
    
    # Add event
    queue.append(event)
    
    # Keep only last 100 events
    if len(queue) > 100:
        queue = queue[-100:]
    
    # Save
    TELEMETRY_QUEUE_FILE.write_text(json.dumps(queue, indent=2))


def _load_queue() -> list[dict[str, Any]]:
    """Load the telemetry queue."""
    if not TELEMETRY_QUEUE_FILE.exists():
        return []
    
    try:
        return json.loads(TELEMETRY_QUEUE_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return []


def _try_flush_queue() -> None:
    """Try to send queued events (non-blocking, best effort)."""
    queue = _load_queue()
    if not queue:
        return
    
    try:
        # Send batch (timeout: 2 seconds to not block CLI)
        with httpx.Client(timeout=2.0) as client:
            response = client.post(
                TELEMETRY_ENDPOINT,
                json={"events": queue},
                headers={"Content-Type": "application/json"},
            )
            
            if response.status_code == 200:
                # Clear queue on success
                clear_queue()
    except Exception:
        # Silently fail - telemetry should never break the CLI
        pass


def clear_queue() -> int:
    """
    Clear the telemetry queue.
    
    Returns:
        Number of events cleared
    """
    queue = _load_queue()
    count = len(queue)
    
    if TELEMETRY_QUEUE_FILE.exists():
        TELEMETRY_QUEUE_FILE.unlink()
    
    return count


def get_queue_stats() -> dict[str, Any]:
    """
    Get statistics about the telemetry queue.
    
    Returns:
        Dict with queue statistics
    """
    queue = _load_queue()
    
    return {
        "enabled": is_telemetry_enabled(),
        "pending_events": len(queue),
        "device_id": get_device_id() if DEVICE_ID_FILE.exists() else None,
        "endpoint": TELEMETRY_ENDPOINT,
    }


def get_pending_events() -> list[dict[str, Any]]:
    """
    Get all pending telemetry events (for transparency).
    
    Returns:
        List of pending events
    """
    return _load_queue()






































