"""
Session loader for Claude Code format.

Claude Code stores sessions as JSONL files in:
~/.claude/projects/<project-path-encoded>/*.jsonl

Each line is a JSON object with fields like:
- type: "user", "assistant", "progress", "tool_use", etc.
- sessionId: UUID of the session
- uuid: UUID of this message
- timestamp: ISO timestamp
- message: {role, content} for user/assistant types
- cwd: Working directory
- gitBranch: Current git branch
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..models import (
    ContentBlock,
    ContentBlockType,
    MessageRole,
    Session,
    SessionMessage,
)
from .base import SessionLoader


class ClaudeCodeLoader(SessionLoader):
    """Loader for Claude Code session files."""
    
    CLAUDE_HOME = Path.home() / ".claude" / "projects"
    
    @property
    def name(self) -> str:
        return "claude_code"
    
    def _encode_project_path(self, project_path: Path) -> str:
        """
        Encode a project path to Claude Code's directory naming convention.
        
        Claude Code uses path with / replaced by - and leading -.
        e.g., /Users/mendrika/Projects/foo -> -Users-mendrika-Projects-foo
        """
        path_str = str(project_path.resolve())
        # Replace path separators with dashes, remove leading slash
        encoded = path_str.replace("/", "-")
        if encoded.startswith("-"):
            pass  # Keep leading dash
        else:
            encoded = "-" + encoded
        return encoded
    
    def _decode_project_path(self, encoded: str) -> Path:
        """
        Decode Claude Code's directory name back to a path.
        """
        # Replace dashes with slashes, but skip leading dash
        if encoded.startswith("-"):
            decoded = encoded[1:].replace("-", "/")
        else:
            decoded = encoded.replace("-", "/")
        return Path("/" + decoded)
    
    def find_sessions(
        self,
        project_path: str | Path,
        since: datetime | None = None,
    ) -> list[Path]:
        """Find Claude Code session files for a project."""
        project_path = Path(project_path).resolve()
        
        if not self.CLAUDE_HOME.exists():
            return []
        
        # Try exact encoded path match
        encoded = self._encode_project_path(project_path)
        project_dir = self.CLAUDE_HOME / encoded
        
        if not project_dir.exists():
            # Try to find by scanning directories (handles path variations)
            for dir_path in self.CLAUDE_HOME.iterdir():
                if dir_path.is_dir():
                    decoded = self._decode_project_path(dir_path.name)
                    # Check if project_path is a prefix or match
                    try:
                        if project_path == decoded or decoded.is_relative_to(project_path):
                            project_dir = dir_path
                            break
                        if project_path.is_relative_to(decoded):
                            project_dir = dir_path
                            break
                    except (ValueError, TypeError):
                        continue
            else:
                return []
        
        # Find all .jsonl files
        session_files = []
        for file_path in project_dir.glob("*.jsonl"):
            if since is not None:
                # Quick check: file modification time
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                # Handle timezone-aware since
                if since.tzinfo is not None:
                    from datetime import timezone
                    mtime = mtime.replace(tzinfo=timezone.utc)
                if mtime < since:
                    continue
            session_files.append(file_path)
        
        return sorted(session_files)
    
    def load_session(self, path: Path) -> Session | None:
        """Load a Claude Code session from a JSONL file."""
        try:
            messages = []
            session_id = None
            cwd = None
            git_branch = None
            model = None
            started_at = None
            ended_at = None
            
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    entry_type = entry.get("type")
                    timestamp_str = entry.get("timestamp")
                    
                    # Extract session metadata
                    if session_id is None and entry.get("sessionId"):
                        session_id = entry["sessionId"]
                    if cwd is None and entry.get("cwd"):
                        cwd = entry["cwd"]
                    if git_branch is None and entry.get("gitBranch"):
                        git_branch = entry["gitBranch"]
                    
                    # Track timestamps
                    if timestamp_str:
                        try:
                            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                            if started_at is None or ts < started_at:
                                started_at = ts
                            if ended_at is None or ts > ended_at:
                                ended_at = ts
                        except (ValueError, TypeError):
                            pass
                    
                    # Process user/assistant messages
                    if entry_type == "user":
                        msg_data = entry.get("message", {})
                        content = self._parse_content(msg_data.get("content", ""))
                        if content:
                            messages.append(SessionMessage(
                                timestamp=timestamp_str or started_at or datetime.now(),
                                role=MessageRole.USER,
                                content=content,
                                uuid=entry.get("uuid"),
                            ))
                    
                    elif entry_type == "assistant":
                        msg_data = entry.get("message", {})
                        content_raw = msg_data.get("content", [])
                        content = self._parse_assistant_content(content_raw)
                        
                        # Extract model
                        if model is None and msg_data.get("model"):
                            model = msg_data["model"]
                        
                        if content:
                            messages.append(SessionMessage(
                                timestamp=timestamp_str or ended_at or datetime.now(),
                                role=MessageRole.ASSISTANT,
                                content=content,
                                uuid=entry.get("uuid"),
                            ))
            
            if not session_id or not messages:
                return None
            
            return Session(
                id=session_id,
                started_at=started_at or datetime.now(),
                ended_at=ended_at,
                channel="cli",  # Claude Code is CLI-based
                messages=messages,
                cwd=cwd,
                git_branch=git_branch,
                model=model,
            )
            
        except Exception as e:
            # Log error but don't crash
            import sys
            print(f"Error loading Claude Code session {path}: {e}", file=sys.stderr)
            return None
    
    def _parse_content(self, content) -> list[ContentBlock]:
        """Parse message content into ContentBlocks."""
        blocks = []
        
        if isinstance(content, str):
            if content.strip():
                blocks.append(ContentBlock(
                    type=ContentBlockType.TEXT,
                    text=content,
                ))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    if item.strip():
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TEXT,
                            text=item,
                        ))
                elif isinstance(item, dict):
                    item_type = item.get("type", "text")
                    if item_type == "text":
                        text = item.get("text", "")
                        if text.strip():
                            blocks.append(ContentBlock(
                                type=ContentBlockType.TEXT,
                                text=text,
                            ))
                    elif item_type == "tool_use":
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_CALL,
                            name=item.get("name"),
                            input=item.get("input"),
                        ))
        
        return blocks
    
    def _parse_assistant_content(self, content) -> list[ContentBlock]:
        """Parse assistant message content including tool calls and thinking."""
        blocks = []
        
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "text")
                    
                    if item_type == "text":
                        text = item.get("text", "")
                        if text.strip():
                            blocks.append(ContentBlock(
                                type=ContentBlockType.TEXT,
                                text=text,
                            ))
                    elif item_type == "tool_use":
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_CALL,
                            name=item.get("name"),
                            input=item.get("input"),
                        ))
                    elif item_type == "thinking":
                        thinking = item.get("thinking", "")
                        if thinking.strip():
                            blocks.append(ContentBlock(
                                type=ContentBlockType.THINKING,
                                text=thinking,
                            ))
                elif isinstance(item, str) and item.strip():
                    blocks.append(ContentBlock(
                        type=ContentBlockType.TEXT,
                        text=item,
                    ))
        elif isinstance(content, str) and content.strip():
            blocks.append(ContentBlock(
                type=ContentBlockType.TEXT,
                text=content,
            ))
        
        return blocks
