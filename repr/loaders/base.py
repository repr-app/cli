"""
Base session loader interface and utilities.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from ..models import Session


class SessionLoader(ABC):
    """Abstract base class for session loaders."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Loader name (e.g., 'claude_code', 'clawdbot')."""
        pass
    
    @abstractmethod
    def find_sessions(
        self,
        project_path: str | Path,
        since: datetime | None = None,
    ) -> list[Path]:
        """
        Find session files for a project.
        
        Args:
            project_path: Path to the project/repo
            since: Only return sessions after this time
        
        Returns:
            List of session file paths
        """
        pass
    
    @abstractmethod
    def load_session(self, path: Path) -> Session | None:
        """
        Load a single session from a file.
        
        Args:
            path: Path to the session file
        
        Returns:
            Session object or None if loading fails
        """
        pass
    
    def load_sessions(
        self,
        project_path: str | Path,
        since: datetime | None = None,
    ) -> Iterator[Session]:
        """
        Load all sessions for a project.
        
        Args:
            project_path: Path to the project/repo
            since: Only return sessions after this time
        
        Yields:
            Session objects
        """
        for path in self.find_sessions(project_path, since):
            session = self.load_session(path)
            if session:
                yield session


def detect_session_source(project_path: str | Path) -> list[str]:
    """
    Detect which session sources are available for a project.
    
    Args:
        project_path: Path to the project/repo
    
    Returns:
        List of available sources: ["claude_code", "clawdbot"]
    """
    from .claude_code import ClaudeCodeLoader
    from .clawdbot import ClawdbotLoader
    
    sources = []
    project_path = Path(project_path).resolve()
    
    # Check Claude Code
    claude_loader = ClaudeCodeLoader()
    if claude_loader.find_sessions(project_path):
        sources.append("claude_code")
    
    # Check Clawdbot
    clawdbot_loader = ClawdbotLoader()
    if clawdbot_loader.find_sessions(project_path):
        sources.append("clawdbot")
    
    return sources


def load_sessions_for_project(
    project_path: str | Path,
    sources: list[str] | None = None,
    since: datetime | None = None,
    days_back: int | None = None,
) -> list[Session]:
    """
    Load sessions from all sources for a project.
    
    Args:
        project_path: Path to the project/repo
        sources: Specific sources to use, or None for auto-detect
        since: Only return sessions after this time
        days_back: Alternative to since: load sessions from last N days
    
    Returns:
        List of sessions sorted by start time
    """
    from .claude_code import ClaudeCodeLoader
    from .clawdbot import ClawdbotLoader
    
    # Calculate since from days_back if provided
    if days_back is not None and since is None:
        since = datetime.now() - timedelta(days=days_back)
    
    # Auto-detect sources if not specified
    if sources is None:
        sources = detect_session_source(project_path)
    
    # Load from all sources
    loaders = {
        "claude_code": ClaudeCodeLoader(),
        "clawdbot": ClawdbotLoader(),
    }
    
    all_sessions = []
    for source in sources:
        if source in loaders:
            loader = loaders[source]
            for session in loader.load_sessions(project_path, since):
                all_sessions.append(session)
    
    # Sort by start time
    all_sessions.sort(key=lambda s: s.started_at)
    return all_sessions
