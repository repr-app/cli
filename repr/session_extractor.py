"""
LLM-based context extraction from AI sessions.

Takes session transcripts and extracts structured context:
- Problem: What was the user trying to solve?
- Approach: What strategy/pattern was used?
- Decisions: Key decisions made
- Outcome: Did it work?
- Lessons: Gotchas and learnings
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .models import (
    ContentBlockType,
    MessageRole,
    Session,
    SessionContext,
    SessionMessage,
)


# =============================================================================
# Extraction Schema
# =============================================================================

class ExtractedContext(BaseModel):
    """Schema for LLM extraction output."""
    problem: str = Field(description="What was the user trying to solve? One paragraph max.")
    approach: str = Field(description="What strategy/pattern was used to solve it? Technical details.")
    decisions: list[str] = Field(
        default_factory=list,
        description="Key decisions made (3-5 items). Format: 'Chose X over Y because Z'"
    )
    files_modified: list[str] = Field(
        default_factory=list,
        description="Files that were created or modified"
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Main tools/commands used"
    )
    outcome: str = Field(description="Did it work? What was the result? One sentence.")
    lessons: list[str] = Field(
        default_factory=list,
        description="Gotchas, learnings, things to remember (1-3 items)"
    )


# =============================================================================
# Prompt Templates
# =============================================================================

EXTRACTION_SYSTEM_PROMPT = """You are a technical context extractor. Your job is to read AI coding assistant sessions and extract structured context that will help future AI agents understand:

1. WHAT problem was being solved
2. HOW it was approached (patterns, strategies)
3. WHAT decisions were made and WHY
4. WHAT worked and what didn't

Write for a technical audience. Be specific about:
- Technologies and patterns used
- Tradeoffs considered
- Gotchas discovered

DO NOT:
- Include filler or marketing language
- Describe the extraction process itself
- Make up information not in the session

Output valid JSON matching the schema provided."""

EXTRACTION_USER_PROMPT = """Extract structured context from this AI coding session.

<session>
{session_transcript}
</session>

Extract:
- problem: What was the user trying to solve? (1 paragraph max)
- approach: What strategy/pattern was used? (technical details)
- decisions: Key decisions made (3-5 items, format: "Chose X over Y because Z")
- files_modified: Files that were created or modified
- tools_used: Main tools/commands used
- outcome: Did it work? What was the result? (1 sentence)
- lessons: Gotchas, learnings (1-3 items)

Respond with valid JSON only."""


# =============================================================================
# Session Formatter
# =============================================================================

def format_session_for_extraction(
    session: Session,
    max_messages: int = 50,
    max_chars: int = 30000,
) -> str:
    """
    Format a session transcript for LLM extraction.
    
    Includes:
    - User messages (full text)
    - Assistant text responses (summarized if long)
    - Tool calls (name + key inputs)
    
    Args:
        session: Session to format
        max_messages: Maximum number of messages to include
        max_chars: Maximum total characters
    
    Returns:
        Formatted transcript string
    """
    lines = []
    total_chars = 0
    
    # Add session metadata
    lines.append(f"Session ID: {session.id}")
    lines.append(f"Started: {session.started_at.isoformat()}")
    if session.cwd:
        lines.append(f"Working Directory: {session.cwd}")
    if session.git_branch:
        lines.append(f"Git Branch: {session.git_branch}")
    lines.append("")
    lines.append("=== CONVERSATION ===")
    lines.append("")
    
    # Process messages
    messages_included = 0
    for msg in session.messages:
        if messages_included >= max_messages:
            lines.append(f"... ({len(session.messages) - messages_included} more messages)")
            break
        
        role_label = msg.role.value.upper()
        timestamp = msg.timestamp.strftime("%H:%M") if isinstance(msg.timestamp, datetime) else ""
        
        # Format content
        content_parts = []
        for block in msg.content:
            if block.type == ContentBlockType.TEXT and block.text:
                # Truncate long text
                text = block.text.strip()
                if len(text) > 2000:
                    text = text[:1500] + "\n... (truncated) ...\n" + text[-300:]
                content_parts.append(text)
            
            elif block.type == ContentBlockType.TOOL_CALL:
                tool_str = f"[TOOL: {block.name}]"
                if block.input:
                    # Extract key inputs
                    key_inputs = []
                    for key in ["path", "command", "query", "url", "file_path"]:
                        if key in block.input:
                            key_inputs.append(f"{key}={block.input[key]}")
                    if key_inputs:
                        tool_str += f" {', '.join(key_inputs[:3])}"
                content_parts.append(tool_str)
            
            elif block.type == ContentBlockType.TOOL_RESULT and block.text:
                # Very brief tool results
                result = block.text.strip()
                if len(result) > 500:
                    result = result[:200] + "... (truncated)"
                content_parts.append(f"[RESULT]: {result}")
        
        if content_parts:
            content = "\n".join(content_parts)
            message_text = f"[{role_label}] {timestamp}\n{content}\n"
            
            # Check character limit
            if total_chars + len(message_text) > max_chars:
                lines.append(f"... (truncated at {max_chars} chars)")
                break
            
            lines.append(message_text)
            total_chars += len(message_text)
            messages_included += 1
    
    return "\n".join(lines)


# =============================================================================
# Extractor
# =============================================================================

class SessionExtractor:
    """Extract structured context from sessions using LLM."""
    
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "openai/gpt-4.1-mini",
    ):
        """
        Initialize extractor.
        
        Args:
            api_key: API key for LLM provider
            base_url: Base URL for API (for local LLMs)
            model: Model to use for extraction
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client = None
    
    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            
            # Try to get config from repr config
            try:
                from .config import get_litellm_config
                litellm_config = get_litellm_config()
                api_key = self.api_key or litellm_config.get("api_key")
                base_url = self.base_url or litellm_config.get("api_base")
            except Exception:
                api_key = self.api_key
                base_url = self.base_url
            
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        return self._client
    
    async def extract_context(
        self,
        session: Session,
        linked_commits: list[str] | None = None,
    ) -> SessionContext:
        """
        Extract context from a session.
        
        Args:
            session: Session to extract from
            linked_commits: Optional list of linked commit SHAs
        
        Returns:
            Extracted SessionContext
        """
        # Format session for LLM
        transcript = format_session_for_extraction(session)
        
        # Call LLM
        client = self._get_client()
        
        try:
            response = await client.chat.completions.create(
                model=self.model.split("/")[-1] if "/" in self.model else self.model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": EXTRACTION_USER_PROMPT.format(
                        session_transcript=transcript
                    )},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            # Parse response
            content = response.choices[0].message.content
            extracted = ExtractedContext.model_validate_json(content)
            
        except Exception as e:
            # Fallback: create minimal context from session metadata
            extracted = ExtractedContext(
                problem=f"AI coding session in {session.cwd or 'unknown directory'}",
                approach="Could not extract - session too short or extraction failed",
                decisions=[],
                files_modified=session.files_touched[:10],
                tools_used=session.tools_used[:10],
                outcome=f"Session lasted {session.duration_seconds or 0:.0f}s with {session.message_count} messages",
                lessons=[f"Extraction error: {str(e)[:100]}"],
            )
        
        # Build SessionContext
        return SessionContext(
            session_id=session.id,
            timestamp=session.started_at,
            problem=extracted.problem,
            approach=extracted.approach,
            decisions=extracted.decisions,
            files_modified=extracted.files_modified or session.files_touched,
            tools_used=extracted.tools_used or session.tools_used,
            outcome=extracted.outcome,
            lessons=extracted.lessons,
            linked_commits=linked_commits or [],
        )
    
    async def extract_batch(
        self,
        sessions: list[Session],
        concurrency: int = 3,
    ) -> list[SessionContext]:
        """
        Extract context from multiple sessions with concurrency control.
        
        Args:
            sessions: Sessions to extract from
            concurrency: Max concurrent extractions
        
        Returns:
            List of extracted SessionContexts
        """
        semaphore = asyncio.Semaphore(concurrency)
        
        async def extract_with_semaphore(session: Session) -> SessionContext:
            async with semaphore:
                return await self.extract_context(session)
        
        tasks = [extract_with_semaphore(s) for s in sessions]
        return await asyncio.gather(*tasks)


# =============================================================================
# Convenience Functions
# =============================================================================

async def extract_session_context(
    session: Session,
    api_key: str | None = None,
    model: str = "openai/gpt-4.1-mini",
) -> SessionContext:
    """
    Convenience function to extract context from a single session.
    
    Args:
        session: Session to extract from
        api_key: Optional API key
        model: Model to use
    
    Returns:
        Extracted SessionContext
    """
    extractor = SessionExtractor(api_key=api_key, model=model)
    return await extractor.extract_context(session)


def extract_session_context_sync(
    session: Session,
    api_key: str | None = None,
    model: str = "openai/gpt-4.1-mini",
) -> SessionContext:
    """
    Synchronous wrapper for extract_session_context.
    """
    return asyncio.run(extract_session_context(session, api_key, model))


# =============================================================================
# CLI Support
# =============================================================================

def summarize_session(session: Session) -> dict[str, Any]:
    """
    Create a quick summary of a session without LLM extraction.
    
    Useful for listing/previewing sessions before full extraction.
    
    Args:
        session: Session to summarize
    
    Returns:
        Summary dict
    """
    # Get first user message as summary
    first_user_msg = ""
    for msg in session.messages:
        if msg.role == MessageRole.USER:
            first_user_msg = msg.text_content[:200]
            if len(msg.text_content) > 200:
                first_user_msg += "..."
            break
    
    return {
        "id": session.id,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration_seconds": session.duration_seconds,
        "channel": session.channel,
        "cwd": session.cwd,
        "model": session.model,
        "message_count": session.message_count,
        "user_messages": session.user_message_count,
        "tools_used": session.tools_used[:5],
        "files_touched": session.files_touched[:5],
        "first_message": first_user_msg,
    }
