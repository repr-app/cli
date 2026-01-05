"""
Story storage management for ~/.repr/stories/

Stories are stored as pairs:
  - <ULID>.md: Story content in Markdown
  - <ULID>.json: Metadata (commits, timestamps, repo, etc.)
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ULID generation (simple implementation)
import random
import time

# Base32 alphabet for ULID
ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    """Generate a ULID (Universally Unique Lexicographically Sortable Identifier)."""
    # Timestamp component (48 bits = 10 chars)
    timestamp_ms = int(time.time() * 1000)
    timestamp_chars = []
    for _ in range(10):
        timestamp_chars.append(ULID_ALPHABET[timestamp_ms & 31])
        timestamp_ms >>= 5
    timestamp_part = "".join(reversed(timestamp_chars))
    
    # Random component (80 bits = 16 chars)
    random_chars = [random.choice(ULID_ALPHABET) for _ in range(16)]
    random_part = "".join(random_chars)
    
    return timestamp_part + random_part


# Storage paths
REPR_HOME = Path(os.getenv("REPR_HOME", Path.home() / ".repr"))
STORIES_DIR = REPR_HOME / "stories"


def ensure_directories() -> None:
    """Ensure storage directories exist."""
    REPR_HOME.mkdir(exist_ok=True)
    STORIES_DIR.mkdir(exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def save_story(
    content: str,
    metadata: dict[str, Any],
    story_id: str | None = None,
) -> str:
    """
    Save a story to ~/.repr/stories/
    
    Args:
        content: Markdown content of the story
        metadata: Story metadata (commits, repo, timestamps, etc.)
        story_id: Optional ULID (generates new one if not provided)
    
    Returns:
        Story ID (ULID)
    """
    ensure_directories()
    
    if story_id is None:
        story_id = generate_ulid()
    
    # Add timestamps to metadata
    now = datetime.now().isoformat()
    if "created_at" not in metadata:
        metadata["created_at"] = now
    metadata["updated_at"] = now
    metadata["id"] = story_id
    
    # Write markdown file
    md_path = STORIES_DIR / f"{story_id}.md"
    _atomic_write(md_path, content)
    
    # Write metadata file
    meta_path = STORIES_DIR / f"{story_id}.json"
    _atomic_write(meta_path, json.dumps(metadata, indent=2, default=str))
    
    return story_id


def load_story(story_id: str) -> tuple[str, dict[str, Any]] | None:
    """
    Load a story by ID.
    
    Args:
        story_id: Story ULID
    
    Returns:
        Tuple of (content, metadata) or None if not found
    """
    md_path = STORIES_DIR / f"{story_id}.md"
    meta_path = STORIES_DIR / f"{story_id}.json"
    
    if not md_path.exists():
        return None
    
    content = md_path.read_text()
    
    metadata = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            pass
    
    return content, metadata


def delete_story(story_id: str) -> bool:
    """
    Delete a story by ID.
    
    Args:
        story_id: Story ULID
    
    Returns:
        True if deleted, False if not found
    """
    md_path = STORIES_DIR / f"{story_id}.md"
    meta_path = STORIES_DIR / f"{story_id}.json"
    
    deleted = False
    
    if md_path.exists():
        md_path.unlink()
        deleted = True
    
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    
    return deleted


def list_stories(
    repo_name: str | None = None,
    since: datetime | None = None,
    needs_review: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    List all stories with metadata.
    
    Args:
        repo_name: Filter by repository name
        since: Filter by creation date
        needs_review: Only show stories needing review
        limit: Maximum stories to return
    
    Returns:
        List of story metadata dicts (sorted by creation date, newest first)
    """
    ensure_directories()
    
    stories = []
    
    for meta_path in STORIES_DIR.glob("*.json"):
        try:
            metadata = json.loads(meta_path.read_text())
            
            # Apply filters
            if repo_name and metadata.get("repo_name") != repo_name:
                continue
            
            if since:
                created_at = metadata.get("created_at")
                if created_at:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created < since:
                        continue
            
            if needs_review and not metadata.get("needs_review", False):
                continue
            
            # Check if content file exists
            story_id = meta_path.stem
            md_path = STORIES_DIR / f"{story_id}.md"
            if md_path.exists():
                metadata["_has_content"] = True
                metadata["_content_size"] = md_path.stat().st_size
            
            stories.append(metadata)
            
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort by creation date (newest first)
    stories.sort(
        key=lambda s: s.get("created_at", ""),
        reverse=True,
    )
    
    if limit:
        stories = stories[:limit]
    
    return stories


def update_story_metadata(story_id: str, updates: dict[str, Any]) -> bool:
    """
    Update metadata for a story.
    
    Args:
        story_id: Story ULID
        updates: Dict of fields to update
    
    Returns:
        True if updated, False if not found
    """
    meta_path = STORIES_DIR / f"{story_id}.json"
    
    if not meta_path.exists():
        return False
    
    try:
        metadata = json.loads(meta_path.read_text())
        metadata.update(updates)
        metadata["updated_at"] = datetime.now().isoformat()
        _atomic_write(meta_path, json.dumps(metadata, indent=2, default=str))
        return True
    except (json.JSONDecodeError, IOError):
        return False


def get_unpushed_stories() -> list[dict[str, Any]]:
    """Get stories that haven't been pushed to cloud."""
    stories = list_stories()
    return [s for s in stories if not s.get("pushed_at")]


def mark_story_pushed(story_id: str) -> bool:
    """Mark a story as pushed to cloud."""
    return update_story_metadata(story_id, {"pushed_at": datetime.now().isoformat()})


def get_stories_needing_review() -> list[dict[str, Any]]:
    """Get stories that need review."""
    return list_stories(needs_review=True)


def get_story_count() -> int:
    """Get total number of stories."""
    ensure_directories()
    return len(list(STORIES_DIR.glob("*.md")))


# ============================================================================
# Backup & Restore
# ============================================================================

def backup_all_data() -> dict[str, Any]:
    """
    Create a full backup of all repr data.
    
    Returns:
        Dict containing all data (can be serialized to JSON)
    """
    from .config import load_config, PROFILES_DIR, CACHE_DIR
    from .privacy import load_audit_log
    
    ensure_directories()
    
    # Backup stories
    stories_backup = []
    for md_path in STORIES_DIR.glob("*.md"):
        story_id = md_path.stem
        meta_path = STORIES_DIR / f"{story_id}.json"
        
        content = md_path.read_text()
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                pass
        
        stories_backup.append({
            "id": story_id,
            "content": content,
            "metadata": metadata,
        })
    
    # Backup profiles
    profiles_backup = []
    for profile_path in PROFILES_DIR.glob("*.md"):
        content = profile_path.read_text()
        meta_path = profile_path.with_suffix(".meta.json")
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                pass
        
        profiles_backup.append({
            "name": profile_path.stem,
            "content": content,
            "metadata": metadata,
        })
    
    # Get config (without sensitive data)
    config = load_config()
    config_backup = {k: v for k, v in config.items() if k != "auth"}
    
    # Get audit log
    audit_log = load_audit_log()
    
    return {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "stories": stories_backup,
        "profiles": profiles_backup,
        "config": config_backup,
        "audit_log": audit_log,
    }


def restore_from_backup(backup_data: dict[str, Any], merge: bool = True) -> dict[str, int]:
    """
    Restore data from a backup.
    
    Args:
        backup_data: Backup dict (from backup_all_data or JSON file)
        merge: If True, merge with existing data. If False, replace.
    
    Returns:
        Dict with counts of restored items
    """
    from .config import save_config, load_config, PROFILES_DIR
    
    ensure_directories()
    
    restored = {
        "stories": 0,
        "profiles": 0,
        "config_keys": 0,
    }
    
    # Restore stories
    for story in backup_data.get("stories", []):
        story_id = story.get("id")
        if not story_id:
            continue
        
        # Check if exists
        md_path = STORIES_DIR / f"{story_id}.md"
        if md_path.exists() and merge:
            continue  # Skip existing in merge mode
        
        # Write story
        _atomic_write(md_path, story.get("content", ""))
        meta_path = STORIES_DIR / f"{story_id}.json"
        _atomic_write(meta_path, json.dumps(story.get("metadata", {}), indent=2))
        restored["stories"] += 1
    
    # Restore profiles
    for profile in backup_data.get("profiles", []):
        name = profile.get("name")
        if not name:
            continue
        
        profile_path = PROFILES_DIR / f"{name}.md"
        if profile_path.exists() and merge:
            continue
        
        profile_path.write_text(profile.get("content", ""))
        if profile.get("metadata"):
            meta_path = profile_path.with_suffix(".meta.json")
            _atomic_write(meta_path, json.dumps(profile.get("metadata"), indent=2))
        restored["profiles"] += 1
    
    # Restore config (merge non-sensitive keys)
    if backup_data.get("config"):
        current_config = load_config()
        backup_config = backup_data["config"]
        
        # Only restore safe keys
        safe_keys = ["settings", "llm", "generation", "publish", "privacy", "tracked_repos", "profile"]
        for key in safe_keys:
            if key in backup_config:
                if merge and key in current_config:
                    # Deep merge for dicts
                    if isinstance(current_config.get(key), dict) and isinstance(backup_config[key], dict):
                        current_config[key] = {**backup_config[key], **current_config[key]}
                    else:
                        current_config[key] = backup_config[key]
                else:
                    current_config[key] = backup_config[key]
                restored["config_keys"] += 1
        
        save_config(current_config)
    
    return restored


def export_stories_json() -> str:
    """
    Export all stories as JSON.
    
    Returns:
        JSON string of all stories
    """
    stories = []
    for md_path in STORIES_DIR.glob("*.md"):
        story_id = md_path.stem
        result = load_story(story_id)
        if result:
            content, metadata = result
            stories.append({
                "id": story_id,
                "content": content,
                "metadata": metadata,
            })
    
    return json.dumps(stories, indent=2, default=str)


def import_stories_json(json_data: str, merge: bool = True) -> int:
    """
    Import stories from JSON.
    
    Args:
        json_data: JSON string of stories
        merge: If True, skip existing stories
    
    Returns:
        Number of stories imported
    """
    try:
        stories = json.loads(json_data)
    except json.JSONDecodeError:
        return 0
    
    imported = 0
    for story in stories:
        story_id = story.get("id")
        
        # Generate new ID if not provided or if exists and not merging
        md_path = STORIES_DIR / f"{story_id}.md" if story_id else None
        if not story_id or (md_path and md_path.exists() and not merge):
            story_id = generate_ulid()
        elif md_path and md_path.exists() and merge:
            continue  # Skip existing
        
        # Save story
        content = story.get("content", "")
        metadata = story.get("metadata", {})
        save_story(content, metadata, story_id)
        imported += 1
    
    return imported


def get_storage_stats() -> dict[str, Any]:
    """
    Get storage statistics.
    
    Returns:
        Dict with storage stats
    """
    from .config import PROFILES_DIR, CACHE_DIR, CONFIG_FILE
    
    ensure_directories()
    
    def dir_size(path: Path) -> int:
        total = 0
        if path.exists():
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total
    
    def file_count(path: Path, pattern: str = "*") -> int:
        if path.exists():
            return len(list(path.glob(pattern)))
        return 0
    
    stories_size = dir_size(STORIES_DIR)
    profiles_size = dir_size(PROFILES_DIR)
    cache_size = dir_size(CACHE_DIR)
    config_size = CONFIG_FILE.stat().st_size if CONFIG_FILE.exists() else 0
    
    return {
        "stories": {
            "count": file_count(STORIES_DIR, "*.md"),
            "size_bytes": stories_size,
            "path": str(STORIES_DIR),
        },
        "profiles": {
            "count": file_count(PROFILES_DIR, "*.md"),
            "size_bytes": profiles_size,
            "path": str(PROFILES_DIR),
        },
        "cache": {
            "size_bytes": cache_size,
            "path": str(CACHE_DIR),
        },
        "config": {
            "size_bytes": config_size,
            "path": str(CONFIG_FILE),
        },
        "total_size_bytes": stories_size + profiles_size + cache_size + config_size,
    }
