"""
Timeline management for unified commit + session context.

Handles:
- Timeline storage (.repr/timeline.json)
- Commit extraction from git
- Session loading and context extraction
- Commit-session matching and merging
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from git import Repo
from git.exc import InvalidGitRepositoryError

from .models import (
    CommitData,
    CommitSessionMatch,
    ReprTimeline,
    SessionContext,
    TimelineEntry,
    TimelineEntryType,
    match_commits_to_sessions,
)


# =============================================================================
# Constants
# =============================================================================

REPR_DIR = ".repr"
TIMELINE_FILE = "timeline.json"


# =============================================================================
# Helpers
# =============================================================================

def get_repr_dir(project_path: Path) -> Path:
    """Get the .repr directory for a project."""
    return project_path / REPR_DIR


def get_timeline_path(project_path: Path) -> Path:
    """Get the timeline.json path for a project."""
    return get_repr_dir(project_path) / TIMELINE_FILE


def ensure_repr_dir(project_path: Path) -> Path:
    """Ensure .repr directory exists and return its path."""
    repr_dir = get_repr_dir(project_path)
    repr_dir.mkdir(parents=True, exist_ok=True)
    
    # Add .gitignore to .repr if it doesn't exist
    gitignore_path = repr_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("# Ignore everything in .repr\n*\n!.gitignore\n")
    
    return repr_dir


def is_initialized(project_path: Path) -> bool:
    """Check if a project has been initialized with repr timeline."""
    return get_timeline_path(project_path).exists()


def detect_project_root(start_path: Path | None = None) -> Path | None:
    """
    Detect the git repository root from a starting path.
    
    Args:
        start_path: Starting path (defaults to cwd)
    
    Returns:
        Repository root path or None if not in a git repo
    """
    start_path = start_path or Path.cwd()
    
    try:
        repo = Repo(start_path, search_parent_directories=True)
        return Path(repo.working_tree_dir)
    except InvalidGitRepositoryError:
        return None


# =============================================================================
# Timeline Serialization
# =============================================================================

def _datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string with timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize_commit(commit: CommitData | None) -> dict | None:
    """Serialize CommitData to JSON-safe dict."""
    if commit is None:
        return None
    return {
        "sha": commit.sha,
        "message": commit.message,
        "author": commit.author,
        "timestamp": _datetime_to_iso(commit.timestamp),
        "files": commit.files,
        "insertions": commit.insertions,
        "deletions": commit.deletions,
    }


def _serialize_session_context(ctx: SessionContext | None) -> dict | None:
    """Serialize SessionContext to JSON-safe dict."""
    if ctx is None:
        return None
    return {
        "session_id": ctx.session_id,
        "timestamp": _datetime_to_iso(ctx.timestamp),
        "problem": ctx.problem,
        "approach": ctx.approach,
        "decisions": ctx.decisions,
        "files_modified": ctx.files_modified,
        "tools_used": ctx.tools_used,
        "outcome": ctx.outcome,
        "lessons": ctx.lessons,
        "linked_commits": ctx.linked_commits,
    }


def _serialize_entry(entry: TimelineEntry) -> dict:
    """Serialize TimelineEntry to JSON-safe dict."""
    return {
        "timestamp": _datetime_to_iso(entry.timestamp),
        "type": entry.type.value,
        "commit": _serialize_commit(entry.commit),
        "session_context": _serialize_session_context(entry.session_context),
        "story": entry.story,
    }


def _deserialize_commit(data: dict | None) -> CommitData | None:
    """Deserialize CommitData from JSON dict."""
    if data is None:
        return None
    return CommitData(
        sha=data["sha"],
        message=data["message"],
        author=data["author"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        files=data["files"],
        insertions=data.get("insertions", 0),
        deletions=data.get("deletions", 0),
    )


def _deserialize_session_context(data: dict | None) -> SessionContext | None:
    """Deserialize SessionContext from JSON dict."""
    if data is None:
        return None
    return SessionContext(
        session_id=data["session_id"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        problem=data["problem"],
        approach=data["approach"],
        decisions=data.get("decisions", []),
        files_modified=data.get("files_modified", []),
        tools_used=data.get("tools_used", []),
        outcome=data["outcome"],
        lessons=data.get("lessons", []),
        linked_commits=data.get("linked_commits", []),
    )


def _deserialize_entry(data: dict) -> TimelineEntry:
    """Deserialize TimelineEntry from JSON dict."""
    return TimelineEntry(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        type=TimelineEntryType(data["type"]),
        commit=_deserialize_commit(data.get("commit")),
        session_context=_deserialize_session_context(data.get("session_context")),
        story=data.get("story"),
    )


def serialize_timeline(timeline: ReprTimeline) -> dict:
    """Serialize ReprTimeline to JSON-safe dict."""
    return {
        "project_path": timeline.project_path,
        "initialized_at": _datetime_to_iso(timeline.initialized_at),
        "entries": [_serialize_entry(e) for e in timeline.entries],
        "session_sources": timeline.session_sources,
        "last_updated": _datetime_to_iso(timeline.last_updated) if timeline.last_updated else None,
    }


def deserialize_timeline(data: dict) -> ReprTimeline:
    """Deserialize ReprTimeline from JSON dict."""
    timeline = ReprTimeline(
        project_path=data["project_path"],
        initialized_at=datetime.fromisoformat(data["initialized_at"]),
        entries=[_deserialize_entry(e) for e in data.get("entries", [])],
        session_sources=data.get("session_sources", []),
        last_updated=datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else None,
    )
    return timeline


# =============================================================================
# Timeline Storage
# =============================================================================

def save_timeline(timeline: ReprTimeline, project_path: Path) -> Path:
    """
    Save timeline to .repr/timeline.json.
    
    Args:
        timeline: Timeline to save
        project_path: Project root path
    
    Returns:
        Path to the saved timeline file
    """
    ensure_repr_dir(project_path)
    timeline_path = get_timeline_path(project_path)
    
    timeline.last_updated = datetime.now(timezone.utc)
    
    with open(timeline_path, "w") as f:
        json.dump(serialize_timeline(timeline), f, indent=2)
    
    return timeline_path


def load_timeline(project_path: Path) -> ReprTimeline | None:
    """
    Load timeline from .repr/timeline.json.
    
    Args:
        project_path: Project root path
    
    Returns:
        ReprTimeline or None if not found
    """
    timeline_path = get_timeline_path(project_path)
    
    if not timeline_path.exists():
        return None
    
    with open(timeline_path) as f:
        data = json.load(f)
    
    return deserialize_timeline(data)


# =============================================================================
# Commit Extraction
# =============================================================================

def extract_commits_from_git(
    project_path: Path,
    days: int = 90,
    max_commits: int = 500,
    since: datetime | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[CommitData]:
    """
    Extract commits from git history.
    
    Args:
        project_path: Path to git repository
        days: Number of days to look back
        max_commits: Maximum number of commits to extract
        since: Only get commits after this time
        progress_callback: Optional callback(current, total) for progress
    
    Returns:
        List of CommitData objects sorted by timestamp
    """
    repo = Repo(project_path)
    commits = []
    
    # Calculate cutoff
    if since:
        cutoff = since
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    cutoff_timestamp = cutoff.timestamp()
    
    # Collect commits
    commit_count = 0
    for commit in repo.iter_commits(max_count=max_commits):
        if commit.committed_date < cutoff_timestamp:
            break
        
        # Skip merge commits
        if len(commit.parents) > 1:
            continue
        
        # Get files changed
        files = list(commit.stats.files.keys())
        
        commits.append(CommitData(
            sha=commit.hexsha,
            message=commit.message.strip(),
            author=commit.author.name,
            timestamp=datetime.fromtimestamp(commit.committed_date, tz=timezone.utc),
            files=files,
            insertions=commit.stats.total.get("insertions", 0),
            deletions=commit.stats.total.get("deletions", 0),
        ))
        
        commit_count += 1
        if progress_callback:
            progress_callback(commit_count, max_commits)
    
    # Sort by timestamp (oldest first)
    commits.sort(key=lambda c: c.timestamp)
    
    return commits


# =============================================================================
# Timeline Initialization
# =============================================================================

def init_timeline_commits_only(
    project_path: Path,
    days: int = 90,
    max_commits: int = 500,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> ReprTimeline:
    """
    Initialize timeline with commits only (no session extraction).
    
    Args:
        project_path: Path to git repository
        days: Number of days to look back
        max_commits: Maximum number of commits
        progress_callback: Optional callback(stage, current, total)
    
    Returns:
        Initialized ReprTimeline
    """
    project_path = Path(project_path).resolve()
    
    # Create timeline
    timeline = ReprTimeline(
        project_path=str(project_path),
        initialized_at=datetime.now(timezone.utc),
        entries=[],
        session_sources=[],
    )
    
    # Extract commits
    def commit_progress(current: int, total: int) -> None:
        if progress_callback:
            progress_callback("commits", current, total)
    
    commits = extract_commits_from_git(
        project_path,
        days=days,
        max_commits=max_commits,
        progress_callback=commit_progress,
    )
    
    # Create timeline entries from commits
    for commit in commits:
        entry = TimelineEntry(
            timestamp=commit.timestamp,
            type=TimelineEntryType.COMMIT,
            commit=commit,
            session_context=None,
            story=None,
        )
        timeline.entries.append(entry)
    
    # Save timeline
    save_timeline(timeline, project_path)
    
    return timeline


async def init_timeline_with_sessions(
    project_path: Path,
    days: int = 90,
    max_commits: int = 500,
    session_sources: list[str] | None = None,
    api_key: str | None = None,
    model: str = "openai/gpt-4.1-mini",
    extraction_concurrency: int = 3,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> ReprTimeline:
    """
    Initialize timeline with commits and session context extraction.
    
    Args:
        project_path: Path to git repository
        days: Number of days to look back
        max_commits: Maximum number of commits
        session_sources: Sources to use (None = auto-detect)
        api_key: API key for LLM extraction
        model: Model for extraction
        extraction_concurrency: Max concurrent LLM extractions
        progress_callback: Optional callback(stage, current, total)
    
    Returns:
        Initialized ReprTimeline with session context
    """
    from .loaders import load_sessions_for_project, detect_session_source
    from .session_extractor import SessionExtractor
    
    project_path = Path(project_path).resolve()
    
    # Create timeline
    timeline = ReprTimeline(
        project_path=str(project_path),
        initialized_at=datetime.now(timezone.utc),
        entries=[],
        session_sources=[],
    )
    
    # Extract commits
    def commit_progress(current: int, total: int) -> None:
        if progress_callback:
            progress_callback("commits", current, total)
    
    commits = extract_commits_from_git(
        project_path,
        days=days,
        max_commits=max_commits,
        progress_callback=commit_progress,
    )
    
    # Load sessions
    if session_sources is None:
        session_sources = detect_session_source(project_path)
    
    timeline.session_sources = session_sources
    
    sessions = load_sessions_for_project(
        project_path,
        sources=session_sources,
        days_back=days,
    )
    
    if progress_callback:
        progress_callback("sessions_loaded", len(sessions), len(sessions))
    
    # Match commits to sessions
    matches = match_commits_to_sessions(commits, sessions)
    
    # Build lookup of commit SHA -> matched sessions
    commit_to_sessions: dict[str, list[str]] = {}
    for match in matches:
        if match.commit_sha not in commit_to_sessions:
            commit_to_sessions[match.commit_sha] = []
        commit_to_sessions[match.commit_sha].append(match.session_id)
    
    # Extract context from sessions
    session_contexts: dict[str, SessionContext] = {}
    
    if sessions:
        extractor = SessionExtractor(api_key=api_key, model=model)
        
        # Extract in batches with progress
        total_sessions = len(sessions)
        for i, session in enumerate(sessions):
            if progress_callback:
                progress_callback("extracting", i + 1, total_sessions)
            
            try:
                # Find linked commits for this session
                linked_commits = [
                    m.commit_sha for m in matches
                    if m.session_id == session.id
                ]
                
                context = await extractor.extract_context(session, linked_commits=linked_commits)
                session_contexts[session.id] = context
            except Exception as e:
                # Log but continue
                print(f"Warning: Failed to extract context from session {session.id}: {e}")
    
    # Create timeline entries
    # First, add all commits
    commit_entries: dict[str, TimelineEntry] = {}
    for commit in commits:
        entry = TimelineEntry(
            timestamp=commit.timestamp,
            type=TimelineEntryType.COMMIT,
            commit=commit,
            session_context=None,
            story=None,
        )
        commit_entries[commit.sha] = entry
        timeline.entries.append(entry)
    
    # Merge session context into matching commits
    for match in matches:
        if match.session_id in session_contexts and match.commit_sha in commit_entries:
            entry = commit_entries[match.commit_sha]
            ctx = session_contexts[match.session_id]
            
            # Upgrade to merged entry if we have session context
            if entry.session_context is None:
                entry.session_context = ctx
                entry.type = TimelineEntryType.MERGED
    
    # Add standalone sessions (those not matched to any commit)
    matched_session_ids = {m.session_id for m in matches}
    for session_id, ctx in session_contexts.items():
        if session_id not in matched_session_ids:
            entry = TimelineEntry(
                timestamp=ctx.timestamp,
                type=TimelineEntryType.SESSION,
                commit=None,
                session_context=ctx,
                story=None,
            )
            timeline.entries.append(entry)
    
    # Sort entries by timestamp
    timeline.entries.sort(key=lambda e: e.timestamp)
    
    # Save timeline
    save_timeline(timeline, project_path)
    
    return timeline


def init_timeline_with_sessions_sync(
    project_path: Path,
    **kwargs,
) -> ReprTimeline:
    """Synchronous wrapper for init_timeline_with_sessions."""
    import asyncio
    return asyncio.run(init_timeline_with_sessions(project_path, **kwargs))


# =============================================================================
# Timeline Queries
# =============================================================================

def get_timeline_stats(timeline: ReprTimeline) -> dict[str, Any]:
    """
    Get statistics about a timeline.
    
    Returns dict with:
        - total_entries
        - commit_count
        - session_count
        - merged_count
        - date_range (first, last)
        - session_sources
    """
    stats = {
        "total_entries": len(timeline.entries),
        "commit_count": 0,
        "session_count": 0,
        "merged_count": 0,
        "date_range": {"first": None, "last": None},
        "session_sources": timeline.session_sources,
    }
    
    for entry in timeline.entries:
        if entry.type == TimelineEntryType.COMMIT:
            stats["commit_count"] += 1
        elif entry.type == TimelineEntryType.SESSION:
            stats["session_count"] += 1
        elif entry.type == TimelineEntryType.MERGED:
            stats["merged_count"] += 1
    
    if timeline.entries:
        stats["date_range"]["first"] = timeline.entries[0].timestamp.isoformat()
        stats["date_range"]["last"] = timeline.entries[-1].timestamp.isoformat()
    
    return stats


def query_timeline(
    timeline: ReprTimeline,
    since: datetime | None = None,
    until: datetime | None = None,
    entry_types: list[TimelineEntryType] | None = None,
    files: list[str] | None = None,
) -> list[TimelineEntry]:
    """
    Query timeline entries with filters.
    
    Args:
        timeline: Timeline to query
        since: Only entries after this time
        until: Only entries before this time
        entry_types: Filter by entry types
        files: Filter by files touched
    
    Returns:
        Filtered list of timeline entries
    """
    results = []
    
    for entry in timeline.entries:
        # Time filters
        if since and entry.timestamp < since:
            continue
        if until and entry.timestamp > until:
            continue
        
        # Type filter
        if entry_types and entry.type not in entry_types:
            continue
        
        # File filter
        if files:
            entry_files = set()
            if entry.commit:
                entry_files.update(entry.commit.files)
            if entry.session_context:
                entry_files.update(entry.session_context.files_modified)
            
            if not any(f in entry_files for f in files):
                continue
        
        results.append(entry)
    
    return results
