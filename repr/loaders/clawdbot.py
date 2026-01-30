"""
Session loader for Clawdbot format.

Clawdbot stores sessions as JSONL files in:
~/.clawdbot/agents/<agentId>/sessions/*.jsonl

Format:
- First line: {"type": "session", "version": 3, "id": "...", "timestamp": "...", "cwd": "..."}
- Subsequent lines: various types including:
  - {"type": "model_change", ...}
  - {"type": "message", "message": {"role": "user"|"assistant", "content": [...]}}
  - {"type": "custom", "customType": "...", "data": {...}}
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


class ClawdbotLoader(SessionLoader):
    """Loader for Clawdbot session files."""
    
    CLAWDBOT_HOME = Path.home() / ".clawdbot" / "agents"
    
    @property
    def name(self) -> str:
        return "clawdbot"
    
    def find_sessions(
        self,
        project_path: str | Path,
        since: datetime | None = None,
    ) -> list[Path]:
        """
        Find Clawdbot session files related to a project.
        
        Note: Clawdbot sessions are organized by agent, not project.
        We scan all agents and filter by cwd in the session metadata.
        """
        project_path = Path(project_path).resolve()
        
        if not self.CLAWDBOT_HOME.exists():
            return []
        
        session_files = []
        
        # Scan all agents
        for agent_dir in self.CLAWDBOT_HOME.iterdir():
            if not agent_dir.is_dir():
                continue
            
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.exists():
                continue
            
            # Find session files
            for file_path in sessions_dir.glob("*.jsonl"):
                # Quick check: file modification time
                if since is not None:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    # Handle timezone-aware since
                    if since.tzinfo is not None:
                        from datetime import timezone
                        mtime = mtime.replace(tzinfo=timezone.utc)
                    if mtime < since:
                        continue
                
                # Check if session is related to project by reading first line
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        first_line = f.readline().strip()
                        if first_line:
                            entry = json.loads(first_line)
                            session_cwd = entry.get("cwd", "")
                            if session_cwd:
                                session_cwd_path = Path(session_cwd).resolve()
                                # Check if paths are related
                                try:
                                    if (project_path == session_cwd_path or
                                        session_cwd_path.is_relative_to(project_path) or
                                        project_path.is_relative_to(session_cwd_path)):
                                        session_files.append(file_path)
                                except (ValueError, TypeError):
                                    pass
                except (json.JSONDecodeError, IOError):
                    continue
        
        return sorted(session_files)
    
    def find_all_sessions(
        self,
        since: datetime | None = None,
        agent_id: str | None = None,
    ) -> list[Path]:
        """
        Find all Clawdbot sessions, optionally filtered by agent.
        
        Args:
            since: Only return sessions after this time
            agent_id: Only return sessions from this agent
        
        Returns:
            List of session file paths
        """
        if not self.CLAWDBOT_HOME.exists():
            return []
        
        session_files = []
        
        # Filter agents
        if agent_id:
            agent_dirs = [self.CLAWDBOT_HOME / agent_id]
        else:
            agent_dirs = [d for d in self.CLAWDBOT_HOME.iterdir() if d.is_dir()]
        
        for agent_dir in agent_dirs:
            if not agent_dir.exists():
                continue
            
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.exists():
                continue
            
            for file_path in sessions_dir.glob("*.jsonl"):
                if since is not None:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < since:
                        continue
                session_files.append(file_path)
        
        return sorted(session_files)
    
    def load_session(self, path: Path) -> Session | None:
        """Load a Clawdbot session from a JSONL file."""
        try:
            messages = []
            session_id = None
            cwd = None
            model = None
            channel = "cli"  # Default, may be overridden
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
                    
                    # Session header
                    if entry_type == "session":
                        session_id = entry.get("id")
                        cwd = entry.get("cwd")
                        continue
                    
                    # Model change
                    if entry_type == "model_change":
                        model = entry.get("modelId")
                        continue
                    
                    # Message entries
                    if entry_type == "message":
                        msg_data = entry.get("message", {})
                        role_str = msg_data.get("role", "")
                        content_raw = msg_data.get("content", [])
                        
                        role = self._parse_role(role_str)
                        if role is None:
                            continue
                        
                        content = self._parse_content(content_raw)
                        if content:
                            messages.append(SessionMessage(
                                timestamp=timestamp_str or started_at or datetime.now(),
                                role=role,
                                content=content,
                                uuid=entry.get("id"),
                            ))
                    
                    # User/assistant messages (alternative format)
                    if entry_type in ("user", "assistant"):
                        msg_data = entry.get("message", {})
                        role = MessageRole.USER if entry_type == "user" else MessageRole.ASSISTANT
                        content_raw = msg_data.get("content", [])
                        
                        content = self._parse_content(content_raw)
                        if content:
                            messages.append(SessionMessage(
                                timestamp=timestamp_str or started_at or datetime.now(),
                                role=role,
                                content=content,
                                uuid=entry.get("id"),
                            ))
                    
                    # Custom types for channel info
                    if entry_type == "custom":
                        custom_type = entry.get("customType", "")
                        if "channel" in custom_type.lower():
                            data = entry.get("data", {})
                            if data.get("channel"):
                                channel = data["channel"]
            
            if not session_id:
                # Use filename as fallback
                session_id = path.stem
            
            if not messages:
                return None
            
            return Session(
                id=session_id,
                started_at=started_at or datetime.now(),
                ended_at=ended_at,
                channel=channel,
                messages=messages,
                cwd=cwd,
                model=model,
            )
            
        except Exception as e:
            import sys
            print(f"Error loading Clawdbot session {path}: {e}", file=sys.stderr)
            return None
    
    def _parse_role(self, role_str: str) -> MessageRole | None:
        """Parse role string to MessageRole enum."""
        role_map = {
            "user": MessageRole.USER,
            "assistant": MessageRole.ASSISTANT,
            "system": MessageRole.SYSTEM,
            "tool": MessageRole.TOOL_RESULT,
            "toolResult": MessageRole.TOOL_RESULT,
        }
        return role_map.get(role_str.lower())
    
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
                    elif item_type in ("tool_use", "toolCall"):
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_CALL,
                            name=item.get("name"),
                            input=item.get("input"),
                        ))
                    elif item_type in ("tool_result", "toolResult"):
                        blocks.append(ContentBlock(
                            type=ContentBlockType.TOOL_RESULT,
                            text=str(item.get("content", item.get("result", ""))),
                        ))
                    elif item_type == "thinking":
                        thinking = item.get("thinking", item.get("text", ""))
                        if thinking.strip():
                            blocks.append(ContentBlock(
                                type=ContentBlockType.THINKING,
                                text=thinking,
                            ))
        
        return blocks
