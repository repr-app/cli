"""
Session loaders for different AI assistant formats.

Supported formats:
- Claude Code: ~/.claude/projects/<project>/*.jsonl
- Clawdbot: ~/.clawdbot/agents/<id>/sessions/*.jsonl
"""

from .claude_code import ClaudeCodeLoader
from .clawdbot import ClawdbotLoader
from .base import SessionLoader, detect_session_source, load_sessions_for_project

__all__ = [
    "SessionLoader",
    "ClaudeCodeLoader",
    "ClawdbotLoader",
    "detect_session_source",
    "load_sessions_for_project",
]
