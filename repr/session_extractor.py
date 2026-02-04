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

EXTRACTION_SYSTEM_PROMPT = """You are a technical context extractor. Your job is to read AI coding assistant sessions and extract structured context that will help future AI agents understand this developer's work.

Extract the ESSENTIAL context that answers:
1. WHAT problem was being solved (the motivation, not just the task)
2. HOW it was approached (specific patterns, architectures, strategies)
3. WHAT decisions were made and WHY (alternatives considered, tradeoffs made)
4. WHAT worked, what didn't, what to watch out for

Write for a technical audience. Be SPECIFIC:
- Name exact technologies, libraries, patterns used
- Quote actual decisions from the conversation ("chose X because...")
- Include gotchas and learnings that would help someone working on similar code

DO NOT:
- Use generic descriptions ("improved the system", "fixed the issue")
- Include filler or marketing language
- Describe the extraction process itself
- Make up information not present in the session
- Leave fields empty - extract something meaningful or say "Not discussed"

Output valid JSON matching the schema provided."""

EXTRACTION_USER_PROMPT = """Extract structured context from this AI coding session.

<session>
{session_transcript}
</session>

Extract these fields (be specific, not generic):

- problem: What was the user trying to solve? What was broken/slow/missing? (1 paragraph)
- approach: What technical strategy/pattern was used? How does the solution work? (specific details)
- decisions: Key decisions made - each formatted as "Chose X over Y because Z" (3-5 items)
- files_modified: Files that were created or significantly modified
- tools_used: Main tools, commands, or APIs used
- outcome: Did it work? What was the observable result? (1-2 sentences)
- lessons: Gotchas discovered, things to remember, warnings for future work (1-3 items)

If a field wasn't discussed in the session, write "Not discussed" rather than guessing.

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

    async def close(self):
        """Close the underlying OpenAI client (no-op for sync client)."""
        # Sync client doesn't need explicit closing
        self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_client(self):
        """Get or create OpenAI client.

        Uses sync client to avoid event loop cleanup issues when called
        from sync contexts via asyncio.run().

        Tries multiple sources for API key in order:
        1. Explicit api_key passed to constructor
        2. BYOK OpenAI config from repr
        3. Local LLM config from repr
        4. OPENAI_API_KEY environment variable
        5. LiteLLM config from repr (cloud mode)
        """
        if self._client is None:
            import os
            from openai import OpenAI

            api_key = self.api_key
            base_url = self.base_url

            if not api_key:
                try:
                    # Try BYOK OpenAI config first
                    from .config import get_byok_config, get_llm_config

                    byok = get_byok_config("openai")
                    if byok and byok.get("api_key"):
                        api_key = byok["api_key"]
                        base_url = base_url or byok.get("base_url")

                    # Try local LLM config
                    if not api_key:
                        llm_config = get_llm_config()
                        if llm_config.get("local_api_key"):
                            api_key = llm_config["local_api_key"]
                            base_url = base_url or llm_config.get("local_api_url")
                except Exception:
                    pass

                # Try environment variable
                if not api_key:
                    api_key = os.getenv("OPENAI_API_KEY")

                # Try LiteLLM config (cloud mode)
                if not api_key:
                    try:
                        from .config import get_litellm_config
                        litellm_url, litellm_key = get_litellm_config()
                        if litellm_key:
                            api_key = litellm_key
                            base_url = base_url or litellm_url
                    except Exception:
                        pass

            if not api_key:
                raise ValueError(
                    "No API key found. Configure one via:\n"
                    "  - repr llm byok openai <key>  (recommended)\n"
                    "  - OPENAI_API_KEY environment variable\n"
                    "  - repr login (for cloud mode)"
                )

            self._client = OpenAI(
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

        # Call LLM (using sync client to avoid event loop cleanup issues)
        client = self._get_client()

        def make_extraction_request(use_temperature: bool = True):
            kwargs = {
                "model": self.model.split("/")[-1] if "/" in self.model else self.model,
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": EXTRACTION_USER_PROMPT.format(
                        session_transcript=transcript
                    )},
                ],
                "response_format": {"type": "json_object"},
            }
            if use_temperature:
                kwargs["temperature"] = 0.3
            return client.chat.completions.create(**kwargs)

        try:
            try:
                response = make_extraction_request(use_temperature=True)
            except Exception as e:
                if "temperature" in str(e).lower() and "unsupported" in str(e).lower():
                    response = make_extraction_request(use_temperature=False)
                else:
                    raise

            # Parse response
            content = response.choices[0].message.content
            extracted = ExtractedContext.model_validate_json(content)

        except Exception as e:
            # Fallback: create context from session metadata + first user message
            first_user_msg = ""
            for msg in session.messages:
                if msg.role == MessageRole.USER and msg.text_content:
                    first_user_msg = msg.text_content[:500]
                    break

            # Try to infer problem from first message
            problem = first_user_msg if first_user_msg else f"AI coding session in {session.cwd or 'project directory'}"

            # Determine if this is an API error vs other error
            error_str = str(e)
            is_api_error = any(x in error_str.lower() for x in ["401", "403", "api key", "unauthorized", "authentication"])

            if is_api_error:
                lesson = "Extraction skipped - configure API key with 'repr llm byok openai <key>'"
            else:
                lesson = f"Extraction failed: {error_str[:80]}"

            extracted = ExtractedContext(
                problem=problem[:500],
                approach="Not extracted - see lessons",
                decisions=[],
                files_modified=session.files_touched[:10],
                tools_used=session.tools_used[:10],
                outcome=f"Session: {session.message_count} messages, {session.duration_seconds or 0:.0f}s",
                lessons=[lesson],
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
