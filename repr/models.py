"""
Data models for session integration.

These models support multi-source context extraction from:
- Git commits (existing)
- AI session logs (Claude Code, Clawdbot)
- Unified timeline (merged view)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Session Models
# =============================================================================

class ContentBlockType(str, Enum):
    """Type of content block within a message."""
    TEXT = "text"
    TOOL_CALL = "toolCall"
    TOOL_RESULT = "toolResult"
    THINKING = "thinking"


@dataclass
class ContentBlock:
    """Content within a message."""
    type: ContentBlockType
    text: str | None = None
    name: str | None = None  # tool name if toolCall
    input: dict | None = None  # tool input if toolCall
    
    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = ContentBlockType(self.type)


class MessageRole(str, Enum):
    """Role of a message sender."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_RESULT = "toolResult"


@dataclass
class SessionMessage:
    """A single message in an AI session."""
    timestamp: datetime
    role: MessageRole
    content: list[ContentBlock]
    uuid: str | None = None
    
    def __post_init__(self):
        if isinstance(self.role, str):
            self.role = MessageRole(self.role)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))

    @property
    def text_content(self) -> str:
        """Get concatenated text content from all text blocks."""
        texts = []
        for block in self.content:
            if block.type == ContentBlockType.TEXT and block.text:
                texts.append(block.text)
        return "\n".join(texts)

    @property
    def tool_calls(self) -> list[ContentBlock]:
        """Get all tool call blocks."""
        return [b for b in self.content if b.type == ContentBlockType.TOOL_CALL]


@dataclass
class Session:
    """A complete AI session."""
    id: str
    started_at: datetime
    ended_at: datetime | None
    channel: str  # "cli", "slack", "web", "telegram", etc.
    messages: list[SessionMessage]
    cwd: str | None = None
    git_branch: str | None = None
    model: str | None = None
    
    # Derived (computed lazily)
    _tools_used: list[str] | None = field(default=None, repr=False)
    _files_touched: list[str] | None = field(default=None, repr=False)
    
    def __post_init__(self):
        if isinstance(self.started_at, str):
            self.started_at = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        if self.ended_at and isinstance(self.ended_at, str):
            self.ended_at = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))

    @property
    def tools_used(self) -> list[str]:
        """Get list of unique tools used in this session."""
        if self._tools_used is None:
            tools = set()
            for msg in self.messages:
                for block in msg.content:
                    if block.type == ContentBlockType.TOOL_CALL and block.name:
                        tools.add(block.name)
            self._tools_used = sorted(tools)
        return self._tools_used

    @property
    def files_touched(self) -> list[str]:
        """Get list of files touched in this session (from tool calls)."""
        if self._files_touched is None:
            files = set()
            file_tools = {"Read", "Write", "Edit", "read_file", "write_file", "edit_file"}
            for msg in self.messages:
                for block in msg.content:
                    if block.type == ContentBlockType.TOOL_CALL and block.name in file_tools:
                        if block.input:
                            # Try common parameter names for file paths
                            for key in ["path", "file_path", "filePath", "filename"]:
                                if key in block.input and block.input[key]:
                                    files.add(block.input[key])
            self._files_touched = sorted(files)
        return self._files_touched

    @property
    def duration_seconds(self) -> float | None:
        """Get session duration in seconds."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    @property
    def message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)

    @property
    def user_message_count(self) -> int:
        """Get user message count."""
        return sum(1 for m in self.messages if m.role == MessageRole.USER)


# =============================================================================
# Context Models (LLM-extracted)
# =============================================================================

class SessionContext(BaseModel):
    """Extracted context from a session (LLM-generated)."""
    session_id: str
    timestamp: datetime
    
    # Core context
    problem: str = Field(description="What was the user trying to solve?")
    approach: str = Field(description="What strategy/pattern was used?")
    decisions: list[str] = Field(default_factory=list, description="Key decisions made")
    files_modified: list[str] = Field(default_factory=list, description="Files that were modified")
    tools_used: list[str] = Field(default_factory=list, description="Tools that were used")
    outcome: str = Field(description="Did it work? What was the result?")
    lessons: list[str] = Field(default_factory=list, description="Gotchas, learnings")
    
    # Linking
    linked_commits: list[str] = Field(default_factory=list, description="Commit SHAs matched by time/files")


# =============================================================================
# Timeline Models
# =============================================================================

class TimelineEntryType(str, Enum):
    """Type of timeline entry."""
    COMMIT = "commit"
    SESSION = "session"
    MERGED = "merged"


@dataclass
class CommitData:
    """Commit data for timeline entries."""
    sha: str
    message: str
    author: str
    timestamp: datetime
    files: list[str]
    insertions: int = 0
    deletions: int = 0
    
    def __post_init__(self):
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))


@dataclass
class TimelineEntry:
    """A single entry in the unified timeline."""
    timestamp: datetime
    type: TimelineEntryType
    
    # Source data (one or both present)
    commit: CommitData | None = None
    session_context: SessionContext | None = None
    
    # Unified story (generated)
    story: dict | None = None  # StoryOutput as dict for flexibility
    
    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = TimelineEntryType(self.type)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))


@dataclass
class ReprTimeline:
    """Unified view stored in .repr/timeline.json"""
    project_path: str
    initialized_at: datetime
    entries: list[TimelineEntry] = field(default_factory=list)
    
    # Metadata
    session_sources: list[str] = field(default_factory=list)  # ["claude_code", "clawdbot"]
    last_updated: datetime | None = None
    
    def __post_init__(self):
        if isinstance(self.initialized_at, str):
            self.initialized_at = datetime.fromisoformat(self.initialized_at.replace("Z", "+00:00"))
        if self.last_updated and isinstance(self.last_updated, str):
            self.last_updated = datetime.fromisoformat(self.last_updated.replace("Z", "+00:00"))

    def add_entry(self, entry: TimelineEntry) -> None:
        """Add an entry and keep timeline sorted by timestamp."""
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.timestamp)
        self.last_updated = datetime.now()

    def get_entries_in_range(
        self,
        start: datetime,
        end: datetime,
        entry_type: TimelineEntryType | None = None,
    ) -> list[TimelineEntry]:
        """Get entries within a time range, optionally filtered by type."""
        result = []
        for entry in self.entries:
            if start <= entry.timestamp <= end:
                if entry_type is None or entry.type == entry_type:
                    result.append(entry)
        return result


# =============================================================================
# Commit-Session Matching
# =============================================================================

@dataclass
class CommitSessionMatch:
    """A match between a commit and a session."""
    commit_sha: str
    session_id: str
    confidence: float  # 0.0 to 1.0
    match_reasons: list[str]  # e.g., ["timestamp_overlap", "files_match"]
    
    # Timestamps for reference
    commit_time: datetime
    session_start: datetime
    session_end: datetime | None
    
    # Overlap details
    overlapping_files: list[str] = field(default_factory=list)
    time_delta_seconds: float = 0.0  # Seconds between session end and commit


def match_commits_to_sessions(
    commits: list[CommitData],
    sessions: list[Session],
    time_window_hours: float = 4.0,
    min_confidence: float = 0.3,
) -> list[CommitSessionMatch]:
    """
    Match commits to sessions based on timestamp and file overlap.
    
    Args:
        commits: List of commit data
        sessions: List of sessions
        time_window_hours: Max hours between session and commit
        min_confidence: Minimum confidence threshold for matches
    
    Returns:
        List of commit-session matches above confidence threshold
    """
    from datetime import timedelta, timezone
    
    def normalize_datetime(dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    matches = []
    time_window = timedelta(hours=time_window_hours)
    
    for commit in commits:
        commit_time = normalize_datetime(commit.timestamp)
        
        for session in sessions:
            reasons = []
            confidence = 0.0
            
            # Calculate time delta (normalize timezones)
            session_start = normalize_datetime(session.started_at)
            session_end = normalize_datetime(session.ended_at or session.started_at)
            time_delta = (commit_time - session_end).total_seconds()
            
            # Check timestamp: commit should be after or during session
            if session_start <= commit_time <= session_end + time_window:
                # Commit during or shortly after session
                if session_start <= commit_time <= session_end:
                    confidence += 0.5
                    reasons.append("commit_during_session")
                else:
                    # Decay confidence based on time after session
                    hours_after = time_delta / 3600
                    time_confidence = max(0, 0.4 * (1 - hours_after / time_window_hours))
                    confidence += time_confidence
                    if time_confidence > 0:
                        reasons.append("timestamp_proximity")
            else:
                # Outside time window
                continue
            
            # Check file overlap
            session_files = set(session.files_touched)
            commit_files = set(commit.files)
            overlapping = session_files & commit_files
            
            if overlapping:
                # Higher confidence for more file matches
                file_confidence = min(0.5, len(overlapping) * 0.15)
                confidence += file_confidence
                reasons.append(f"files_match:{len(overlapping)}")
            
            # Check working directory match
            if session.cwd and any(commit.files):
                # Rough check: does commit touch files in session's cwd?
                # This is a heuristic - real matching would need repo root detection
                pass
            
            # Create match if above threshold
            if confidence >= min_confidence:
                matches.append(CommitSessionMatch(
                    commit_sha=commit.sha,
                    session_id=session.id,
                    confidence=confidence,
                    match_reasons=reasons,
                    commit_time=commit_time,
                    session_start=session_start,
                    session_end=session.ended_at,  # Keep original for display
                    overlapping_files=sorted(overlapping),
                    time_delta_seconds=time_delta,
                ))
    
    # Sort by confidence descending
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches
