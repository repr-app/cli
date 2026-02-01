"""
Session loaders for different AI assistant formats.

Supported formats:
- Claude Code: ~/.claude/projects/<project>/*.jsonl
- Clawdbot: ~/.clawdbot/agents/<id>/sessions/*.jsonl
- Gemini Antigravity: ~/.gemini/antigravity/brain/<conversation-id>/
"""

from .claude_code import ClaudeCodeLoader
from .clawdbot import ClawdbotLoader
from .gemini_antigravity import GeminiAntigravityLoader
from .base import SessionLoader, detect_session_source, load_sessions_for_project

__all__ = [
    "SessionLoader",
    "ClaudeCodeLoader",
    "ClawdbotLoader",
    "GeminiAntigravityLoader",
    "detect_session_source",
    "load_sessions_for_project",
]
