"""
Privacy controls and audit logging.

Tracks what data has been sent to cloud services and provides
privacy guarantee explanations.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import (
    AUDIT_DIR,
    CONFIG_DIR,
    get_privacy_settings,
    get_llm_config,
    is_authenticated,
    is_cloud_allowed,
    load_config,
)


# Audit log file
AUDIT_LOG_FILE = AUDIT_DIR / "cloud_operations.json"


def ensure_audit_dir() -> None:
    """Ensure audit directory exists."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def log_cloud_operation(
    operation: str,
    destination: str,
    payload_summary: dict[str, Any],
    bytes_sent: int = 0,
) -> None:
    """
    Log a cloud operation for audit purposes.
    
    Args:
        operation: Type of operation (e.g., "cloud_generation", "push", "byok_generation")
        destination: Where data was sent (e.g., "repr.dev", "api.openai.com")
        payload_summary: Summary of what was sent (no actual content)
        bytes_sent: Approximate bytes sent
    """
    ensure_audit_dir()
    
    # Load existing log
    log = load_audit_log()
    
    # Add new entry
    log.append({
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "destination": destination,
        "payload_summary": payload_summary,
        "bytes_sent": bytes_sent,
    })
    
    # Keep only last 1000 entries
    if len(log) > 1000:
        log = log[-1000:]
    
    # Save
    AUDIT_LOG_FILE.write_text(json.dumps(log, indent=2))


def load_audit_log() -> list[dict[str, Any]]:
    """Load the audit log."""
    if not AUDIT_LOG_FILE.exists():
        return []
    
    try:
        return json.loads(AUDIT_LOG_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return []


def get_audit_summary(days: int = 30) -> dict[str, Any]:
    """
    Get summary of cloud operations for the last N days.
    
    Args:
        days: Number of days to include
    
    Returns:
        Summary dict with operation counts and details
    """
    log = load_audit_log()
    cutoff = datetime.now() - timedelta(days=days)
    
    # Filter to recent entries
    recent = []
    for entry in log:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                recent.append(entry)
        except (ValueError, KeyError):
            continue
    
    # Group by operation type
    by_operation: dict[str, list] = {}
    for entry in recent:
        op = entry.get("operation", "unknown")
        if op not in by_operation:
            by_operation[op] = []
        by_operation[op].append(entry)
    
    # Calculate totals
    total_bytes = sum(e.get("bytes_sent", 0) for e in recent)
    
    return {
        "period_days": days,
        "total_operations": len(recent),
        "total_bytes_sent": total_bytes,
        "by_operation": {
            op: {
                "count": len(entries),
                "bytes_sent": sum(e.get("bytes_sent", 0) for e in entries),
                "recent": entries[-3:],  # Last 3 entries
            }
            for op, entries in by_operation.items()
        },
        "destinations": list(set(e.get("destination", "") for e in recent)),
    }


def get_privacy_explanation() -> dict[str, Any]:
    """
    Get comprehensive privacy explanation for current state.
    
    Returns:
        Dict with architecture guarantees, current settings, and policies
    """
    privacy_settings = get_privacy_settings()
    llm_config = get_llm_config()
    authenticated = is_authenticated()
    cloud_allowed = is_cloud_allowed()
    
    return {
        "architecture": {
            "guarantee": "Without login, nothing leaves your machine (enforced in code)",
            "no_background_daemons": True,
            "no_silent_uploads": True,
            "all_network_foreground": True,
            "no_telemetry_default": True,
        },
        "current_state": {
            "authenticated": authenticated,
            "mode": "cloud-enabled" if (authenticated and cloud_allowed) else "local only",
            "privacy_lock": privacy_settings.get("lock_local_only", False),
            "privacy_lock_permanent": privacy_settings.get("lock_permanent", False),
            "telemetry_enabled": privacy_settings.get("telemetry_enabled", False),
        },
        "local_mode_network_policy": {
            "allowed": ["127.0.0.1", "localhost", "::1", "Unix domain sockets"],
            "blocked": ["All external network", "DNS to public", "HTTP(S) to internet"],
        },
        "cloud_mode_settings": {
            "path_redaction_enabled": llm_config.get("cloud_redact_paths", True),
            "diffs_disabled": not llm_config.get("cloud_send_diffs", False),
            "email_redaction_enabled": llm_config.get("cloud_redact_emails", False),
            "custom_redact_patterns": llm_config.get("cloud_redact_patterns", []),
            "repo_allowlist": llm_config.get("cloud_allowlist_repos", []),
        },
        "data_retention": {
            "story_deletion": "Immediate removal from repr.dev",
            "account_deletion": "All data deleted within 30 days",
            "backups": "Encrypted snapshots retained 90 days",
            "local_data": "Never touched by cloud operations",
        },
        "ownership": {
            "content_ownership": "Your content belongs to you",
            "no_ownership_claim": "repr claims no ownership over generated stories",
        },
    }


def get_data_sent_history(limit: int = 20) -> list[dict[str, Any]]:
    """
    Get history of data sent to cloud.
    
    Args:
        limit: Maximum entries to return
    
    Returns:
        List of audit entries with human-readable details
    """
    log = load_audit_log()
    
    # Format entries
    formatted = []
    for entry in reversed(log[-limit:]):
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            relative = _relative_time(dt)
        except ValueError:
            relative = ts
        
        formatted.append({
            "timestamp": ts,
            "relative_time": relative,
            "operation": _format_operation(entry.get("operation", "")),
            "destination": entry.get("destination", ""),
            "summary": entry.get("payload_summary", {}),
            "bytes_sent": entry.get("bytes_sent", 0),
        })
    
    return formatted


def _format_operation(op: str) -> str:
    """Format operation name for display."""
    return {
        "cloud_generation": "Cloud LLM Generation",
        "byok_generation": "BYOK Generation",
        "push": "Story Push",
        "sync": "Story Sync",
        "profile_update": "Profile Update",
    }.get(op, op.replace("_", " ").title())


def _relative_time(dt: datetime) -> str:
    """Format datetime as relative time."""
    now = datetime.now()
    delta = now - dt
    
    if delta.days > 365:
        return f"{delta.days // 365}y ago"
    elif delta.days > 30:
        return f"{delta.days // 30}mo ago"
    elif delta.days > 0:
        return f"{delta.days}d ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600}h ago"
    elif delta.seconds > 60:
        return f"{delta.seconds // 60}m ago"
    else:
        return "just now"


def check_cloud_permission(operation: str) -> tuple[bool, str | None]:
    """
    Check if a cloud operation is permitted.
    
    Args:
        operation: Operation type (e.g., "cloud_generation", "push")
    
    Returns:
        Tuple of (allowed, reason_if_blocked)
    """
    from .config import is_ci_mode, get_forced_mode
    
    # CI mode blocks cloud
    if is_ci_mode():
        return False, "CI mode enabled (REPR_CI=true)"
    
    # Forced local mode
    if get_forced_mode() == "local":
        return False, "Local mode forced (REPR_MODE=local)"
    
    # Privacy lock
    privacy = get_privacy_settings()
    if privacy.get("lock_local_only"):
        if privacy.get("lock_permanent"):
            return False, "Cloud features permanently locked"
        return False, "Local-only mode enabled (use `repr privacy unlock-local` to disable)"
    
    # Authentication required
    if not is_authenticated():
        return False, "Not authenticated (run `repr login`)"
    
    return True, None


def get_local_data_info() -> dict[str, Any]:
    """
    Get information about locally stored data.
    
    Returns:
        Dict with local data statistics
    """
    from .storage import STORIES_DIR, get_story_count
    
    def dir_size(path: Path) -> int:
        total = 0
        if path.exists():
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total
    
    stories_size = dir_size(STORIES_DIR) if STORIES_DIR.exists() else 0
    audit_size = dir_size(AUDIT_DIR) if AUDIT_DIR.exists() else 0
    
    return {
        "stories": {
            "count": get_story_count(),
            "size_bytes": stories_size,
            "path": str(STORIES_DIR),
        },
        "audit_log": {
            "entries": len(load_audit_log()),
            "size_bytes": audit_size,
            "path": str(AUDIT_DIR),
        },
        "config": {
            "path": str(CONFIG_DIR / "config.json"),
            "size_bytes": (CONFIG_DIR / "config.json").stat().st_size if (CONFIG_DIR / "config.json").exists() else 0,
        },
    }


def clear_audit_log() -> int:
    """
    Clear the audit log.
    
    Returns:
        Number of entries cleared
    """
    log = load_audit_log()
    count = len(log)
    
    if AUDIT_LOG_FILE.exists():
        AUDIT_LOG_FILE.unlink()
    
    return count






































