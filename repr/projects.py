"""
Project configuration management for repr.

Stores project settings in ~/.repr/projects.json for social post generation
and other project-specific configurations.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

from .config import CONFIG_DIR, ensure_directories


# Project config file location
PROJECTS_FILE = CONFIG_DIR / "projects.json"

# Default platforms for social posts
DEFAULT_PLATFORMS = ["twitter", "linkedin", "reddit", "hackernews", "indiehackers"]

# Valid timeframe values
VALID_TIMEFRAMES = ["daily", "weekly", "monthly", "7days", "14days", "30days"]


def _atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON to file atomically using temp file + rename."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_projects_config() -> dict[str, Any]:
    """Load projects configuration from disk."""
    ensure_directories()
    
    if not PROJECTS_FILE.exists():
        return {"projects": {}, "default_project": None}
    
    try:
        with open(PROJECTS_FILE, "r") as f:
            config = json.load(f)
            # Ensure required keys exist
            config.setdefault("projects", {})
            config.setdefault("default_project", None)
            return config
    except (json.JSONDecodeError, IOError):
        return {"projects": {}, "default_project": None}


def save_projects_config(config: dict[str, Any]) -> None:
    """Save projects configuration to disk."""
    ensure_directories()
    _atomic_json_write(PROJECTS_FILE, config)


def get_project(name: str) -> dict[str, Any] | None:
    """Get a project configuration by name."""
    config = load_projects_config()
    return config["projects"].get(name)


def list_projects() -> List[dict[str, Any]]:
    """List all configured projects with their settings."""
    config = load_projects_config()
    projects = []
    
    for name, settings in config["projects"].items():
        projects.append({
            "name": name,
            "path": settings.get("path"),
            "description": settings.get("description"),
            "platforms": settings.get("platforms", DEFAULT_PLATFORMS),
            "timeframe": settings.get("timeframe", "weekly"),
            "is_default": config.get("default_project") == name,
            "created_at": settings.get("created_at"),
            "updated_at": settings.get("updated_at"),
        })
    
    return projects


def add_project(
    name: str,
    path: str,
    description: Optional[str] = None,
    platforms: Optional[List[str]] = None,
    timeframe: str = "weekly",
    set_default: bool = False,
) -> dict[str, Any]:
    """Add a new project configuration.
    
    Args:
        name: Project display name (used as key)
        path: Path to git repository
        description: Optional project description for context
        platforms: List of platforms to generate for (default: all)
        timeframe: Default timeframe for generation (daily, weekly, monthly)
        set_default: Whether to set this as the default project
    
    Returns:
        The created project configuration
    """
    config = load_projects_config()
    
    # Normalize and validate path
    normalized_path = str(Path(path).expanduser().resolve())
    
    if not Path(normalized_path).exists():
        raise ValueError(f"Path does not exist: {normalized_path}")
    
    if not (Path(normalized_path) / ".git").exists():
        raise ValueError(f"Path is not a git repository: {normalized_path}")
    
    # Validate timeframe
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid timeframe: {timeframe}. Must be one of: {VALID_TIMEFRAMES}")
    
    # Validate platforms
    valid_platforms = ["twitter", "linkedin", "reddit", "hackernews", "indiehackers"]
    if platforms:
        for p in platforms:
            if p not in valid_platforms:
                raise ValueError(f"Invalid platform: {p}. Must be one of: {valid_platforms}")
    
    now = datetime.now().isoformat()
    
    project = {
        "path": normalized_path,
        "description": description,
        "platforms": platforms or DEFAULT_PLATFORMS,
        "timeframe": timeframe,
        "created_at": now,
        "updated_at": now,
    }
    
    config["projects"][name] = project
    
    if set_default or len(config["projects"]) == 1:
        config["default_project"] = name
    
    save_projects_config(config)
    
    return {"name": name, **project}


def update_project(name: str, **updates) -> dict[str, Any]:
    """Update a project configuration.
    
    Args:
        name: Project name to update
        **updates: Fields to update (path, description, platforms, timeframe)
    
    Returns:
        The updated project configuration
    """
    config = load_projects_config()
    
    if name not in config["projects"]:
        raise ValueError(f"Project not found: {name}")
    
    project = config["projects"][name]
    
    # Validate and apply updates
    if "path" in updates:
        path = str(Path(updates["path"]).expanduser().resolve())
        if not Path(path).exists():
            raise ValueError(f"Path does not exist: {path}")
        project["path"] = path
    
    if "description" in updates:
        project["description"] = updates["description"]
    
    if "platforms" in updates:
        valid_platforms = ["twitter", "linkedin", "reddit", "hackernews", "indiehackers"]
        for p in updates["platforms"]:
            if p not in valid_platforms:
                raise ValueError(f"Invalid platform: {p}")
        project["platforms"] = updates["platforms"]
    
    if "timeframe" in updates:
        if updates["timeframe"] not in VALID_TIMEFRAMES:
            raise ValueError(f"Invalid timeframe: {updates['timeframe']}")
        project["timeframe"] = updates["timeframe"]
    
    project["updated_at"] = datetime.now().isoformat()
    
    config["projects"][name] = project
    save_projects_config(config)
    
    return {"name": name, **project}


def remove_project(name: str) -> bool:
    """Remove a project configuration.
    
    Args:
        name: Project name to remove
    
    Returns:
        True if removed, False if not found
    """
    config = load_projects_config()
    
    if name not in config["projects"]:
        return False
    
    del config["projects"][name]
    
    # Clear default if it was this project
    if config.get("default_project") == name:
        # Set first remaining project as default, or None
        if config["projects"]:
            config["default_project"] = next(iter(config["projects"]))
        else:
            config["default_project"] = None
    
    save_projects_config(config)
    return True


def set_default_project(name: str) -> bool:
    """Set the default project.
    
    Args:
        name: Project name to set as default
    
    Returns:
        True if set, False if project not found
    """
    config = load_projects_config()
    
    if name not in config["projects"]:
        return False
    
    config["default_project"] = name
    save_projects_config(config)
    return True


def get_default_project() -> dict[str, Any] | None:
    """Get the default project configuration."""
    config = load_projects_config()
    default_name = config.get("default_project")
    
    if not default_name:
        return None
    
    project = config["projects"].get(default_name)
    if not project:
        return None
    
    return {"name": default_name, **project}


def auto_detect_projects() -> List[dict[str, Any]]:
    """Auto-detect projects from tracked repositories.
    
    Returns:
        List of detected projects not yet configured
    """
    from .config import get_tracked_repos
    from .db import get_db
    
    config = load_projects_config()
    existing_paths = {p.get("path") for p in config["projects"].values()}
    
    detected = []
    
    # Check tracked repos
    for repo in get_tracked_repos():
        path = repo.get("path")
        if path and path not in existing_paths:
            # Try to get repo name
            name = Path(path).name
            detected.append({
                "name": name,
                "path": path,
                "source": "tracked_repo",
            })
    
    # Also check database for projects
    try:
        db = get_db()
        with db.connect() as conn:
            for row in conn.execute("SELECT name, path FROM projects").fetchall():
                path = row["path"]
                if path and path not in existing_paths:
                    detected.append({
                        "name": row["name"],
                        "path": path,
                        "source": "database",
                    })
    except Exception:
        pass
    
    # Deduplicate by path
    seen_paths = set()
    unique = []
    for d in detected:
        if d["path"] not in seen_paths:
            seen_paths.add(d["path"])
            unique.append(d)
    
    return unique


def get_project_for_path(path: str) -> dict[str, Any] | None:
    """Find a project configuration by its path.
    
    Args:
        path: Repository path to look up
    
    Returns:
        Project configuration if found, None otherwise
    """
    config = load_projects_config()
    normalized = str(Path(path).expanduser().resolve())
    
    for name, project in config["projects"].items():
        if project.get("path") == normalized:
            return {"name": name, **project}
    
    return None


def get_project_git_info(path: str) -> dict[str, Any]:
    """Get git information for a project path.
    
    Args:
        path: Repository path
    
    Returns:
        Dict with remote_url, branch, etc.
    """
    try:
        # Get remote URL
        result = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        remote_url = result.stdout.strip() if result.returncode == 0 else None
        
        # Get current branch
        result = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip() if result.returncode == 0 else None
        
        return {
            "remote_url": remote_url,
            "branch": branch,
            "path": path,
        }
    except Exception:
        return {"path": path}
