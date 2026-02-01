"""
Cron-based story generation scheduling for repr.

Provides predictable, scheduled story generation as an alternative to
hook-triggered generation. Runs every 4 hours by default, skipping
if there aren't enough commits in the queue.
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import REPR_HOME, load_config, save_config

# Cron job identifier - used to find/modify our entry
CRON_MARKER = "# repr-auto-generate"
CRON_MARKER_PAUSED = "# repr-auto-generate-PAUSED"

# Default interval: every 4 hours
DEFAULT_INTERVAL_HOURS = 4

# Minimum commits needed to trigger generation
DEFAULT_MIN_COMMITS = 3


def _get_repr_path() -> str:
    """Get the path to repr executable."""
    # Check common installation paths first
    common_paths = [
        "/usr/local/bin/repr",
        "/opt/homebrew/bin/repr",
        Path.home() / ".local/bin/repr",
    ]

    for p in common_paths:
        if Path(p).exists():
            return str(p)

    # Try to find repr in PATH (avoiding venv paths)
    try:
        result = subprocess.run(
            ["which", "-a", "repr"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for path in result.stdout.strip().split('\n'):
                # Skip venv/virtualenv paths
                if 'venv' not in path and '.venv' not in path:
                    return path
            # If all are venv, use the first one
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass

    # Fallback to python -m repr (using system python, not venv)
    return "python3 -m repr"


def _get_helper_script_path() -> Path:
    """Get path to the cron helper script."""
    return REPR_HOME / "bin" / "cron-generate.sh"


def _create_helper_script(min_commits: int = DEFAULT_MIN_COMMITS) -> Path:
    """
    Create the helper script for cron job.

    This is cleaner than embedding complex shell in crontab.
    """
    repr_path = _get_repr_path()
    log_file = REPR_HOME / "logs" / "cron.log"

    script_path = _get_helper_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)

    script = f'''#!/bin/bash
# repr cron helper - auto-generated, do not edit
# Checks queue and generates stories if enough commits

LOG="{log_file}"
MIN_COMMITS={min_commits}

# Get total queue count across all repos
QUEUE_COUNT=$({repr_path} hooks status --json 2>/dev/null | \\
    python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(r.get('queue_count',0) for r in d))" 2>/dev/null || echo 0)

if [ "$QUEUE_COUNT" -ge "$MIN_COMMITS" ]; then
    echo "[$(date -Iseconds)] Generating stories (queue: $QUEUE_COUNT commits)" >> "$LOG"
    {repr_path} generate --local >> "$LOG" 2>&1
else
    echo "[$(date -Iseconds)] Skipping (queue: $QUEUE_COUNT < $MIN_COMMITS)" >> "$LOG"
fi
'''

    script_path.write_text(script)
    # Make executable
    script_path.chmod(script_path.stat().st_mode | 0o755)

    return script_path


def _get_cron_command(min_commits: int = DEFAULT_MIN_COMMITS) -> str:
    """
    Build the cron command.

    Creates a helper script and returns the path to run it.
    """
    script_path = _create_helper_script(min_commits)
    return str(script_path)


def _get_cron_line(interval_hours: int = DEFAULT_INTERVAL_HOURS, min_commits: int = DEFAULT_MIN_COMMITS) -> str:
    """Build the full crontab line."""
    cmd = _get_cron_command(min_commits)
    # Run at minute 0 every N hours
    # Format: minute hour day month weekday command
    return f"0 */{interval_hours} * * * {cmd} {CRON_MARKER}"


def _read_crontab() -> list[str]:
    """Read current user's crontab."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip().split('\n') if result.stdout.strip() else []
        return []
    except Exception:
        return []


def _write_crontab(lines: list[str]) -> bool:
    """Write lines to user's crontab."""
    try:
        content = '\n'.join(lines) + '\n' if lines else ''
        result = subprocess.run(
            ["crontab", "-"],
            input=content,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _find_repr_cron_line(lines: list[str]) -> tuple[int, bool]:
    """
    Find repr cron line in crontab.

    Returns:
        (index, is_paused) - index is -1 if not found
    """
    for i, line in enumerate(lines):
        # Check PAUSED first since MARKER is a substring of MARKER_PAUSED
        if CRON_MARKER_PAUSED in line:
            return i, True
        if CRON_MARKER in line:
            return i, False
    return -1, False


def get_cron_status() -> dict[str, Any]:
    """
    Get current cron job status.

    Returns:
        Dict with 'installed', 'paused', 'interval_hours', 'next_run' keys
    """
    lines = _read_crontab()
    idx, is_paused = _find_repr_cron_line(lines)

    if idx == -1:
        return {
            "installed": False,
            "paused": False,
            "interval_hours": None,
            "cron_line": None,
        }

    line = lines[idx]

    # Parse interval from cron expression (e.g., "0 */4 * * *")
    interval_hours = DEFAULT_INTERVAL_HOURS
    match = re.search(r'\*/(\d+)', line)
    if match:
        interval_hours = int(match.group(1))

    return {
        "installed": True,
        "paused": is_paused,
        "interval_hours": interval_hours,
        "cron_line": line if not is_paused else line.lstrip('# '),
    }


def install_cron(
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
    min_commits: int = DEFAULT_MIN_COMMITS,
) -> dict[str, Any]:
    """
    Install cron job for automatic story generation.

    Args:
        interval_hours: Hours between runs (default 4)
        min_commits: Minimum commits in queue to trigger generation

    Returns:
        Dict with 'success', 'message', 'already_installed' keys
    """
    # Ensure log directory exists
    log_dir = REPR_HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    lines = _read_crontab()
    idx, is_paused = _find_repr_cron_line(lines)

    cron_line = _get_cron_line(interval_hours, min_commits)

    if idx >= 0:
        if is_paused:
            # Replace paused line with active one
            lines[idx] = cron_line
            if _write_crontab(lines):
                _update_config_cron_status(True, interval_hours, min_commits)
                return {
                    "success": True,
                    "message": "Cron job resumed and updated",
                    "already_installed": False,
                }
            return {
                "success": False,
                "message": "Failed to write crontab",
                "already_installed": False,
            }
        else:
            # Update existing active line
            lines[idx] = cron_line
            if _write_crontab(lines):
                _update_config_cron_status(True, interval_hours, min_commits)
                return {
                    "success": True,
                    "message": "Cron job updated",
                    "already_installed": True,
                }
            return {
                "success": False,
                "message": "Failed to write crontab",
                "already_installed": True,
            }

    # Add new line
    lines.append(cron_line)
    if _write_crontab(lines):
        _update_config_cron_status(True, interval_hours, min_commits)
        return {
            "success": True,
            "message": f"Cron job installed (every {interval_hours}h, min {min_commits} commits)",
            "already_installed": False,
        }

    return {
        "success": False,
        "message": "Failed to write crontab",
        "already_installed": False,
    }


def remove_cron() -> dict[str, Any]:
    """
    Remove cron job for story generation.

    Returns:
        Dict with 'success', 'message' keys
    """
    lines = _read_crontab()
    idx, _ = _find_repr_cron_line(lines)

    if idx == -1:
        return {
            "success": True,
            "message": "No cron job to remove",
        }

    lines.pop(idx)
    if _write_crontab(lines):
        _update_config_cron_status(False, None, None)
        return {
            "success": True,
            "message": "Cron job removed",
        }

    return {
        "success": False,
        "message": "Failed to write crontab",
    }


def pause_cron() -> dict[str, Any]:
    """
    Pause cron job by commenting it out.

    Returns:
        Dict with 'success', 'message' keys
    """
    lines = _read_crontab()
    idx, is_paused = _find_repr_cron_line(lines)

    if idx == -1:
        return {
            "success": False,
            "message": "No cron job installed",
        }

    if is_paused:
        return {
            "success": True,
            "message": "Cron job already paused",
        }

    # Comment out the line, change marker to PAUSED
    line = lines[idx]
    paused_line = "# " + line.replace(CRON_MARKER, CRON_MARKER_PAUSED)
    lines[idx] = paused_line

    if _write_crontab(lines):
        config = load_config()
        if "cron" not in config:
            config["cron"] = {}
        config["cron"]["paused"] = True
        save_config(config)
        return {
            "success": True,
            "message": "Cron job paused",
        }

    return {
        "success": False,
        "message": "Failed to write crontab",
    }


def resume_cron() -> dict[str, Any]:
    """
    Resume paused cron job.

    Returns:
        Dict with 'success', 'message' keys
    """
    lines = _read_crontab()
    idx, is_paused = _find_repr_cron_line(lines)

    if idx == -1:
        return {
            "success": False,
            "message": "No cron job installed",
        }

    if not is_paused:
        return {
            "success": True,
            "message": "Cron job already active",
        }

    # Uncomment the line, change marker back
    line = lines[idx].lstrip('# ')
    active_line = line.replace(CRON_MARKER_PAUSED, CRON_MARKER)
    lines[idx] = active_line

    if _write_crontab(lines):
        config = load_config()
        if "cron" not in config:
            config["cron"] = {}
        config["cron"]["paused"] = False
        save_config(config)
        return {
            "success": True,
            "message": "Cron job resumed",
        }

    return {
        "success": False,
        "message": "Failed to write crontab",
    }


def _update_config_cron_status(
    installed: bool,
    interval_hours: int | None,
    min_commits: int | None,
) -> None:
    """Update cron status in config file."""
    config = load_config()

    if installed:
        config["cron"] = {
            "installed": True,
            "paused": False,
            "interval_hours": interval_hours,
            "min_commits": min_commits,
            "installed_at": datetime.now().isoformat(),
        }
    else:
        config["cron"] = {
            "installed": False,
            "paused": False,
            "interval_hours": None,
            "min_commits": None,
        }

    save_config(config)
