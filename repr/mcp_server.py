"""
MCP (Model Context Protocol) server for repr.

Exposes repr functionality as tools and resources for AI agents like
Claude Code, Cursor, Windsurf, and other MCP-compatible clients.

Usage:
    repr mcp serve              # Start MCP server (stdio mode)
    repr mcp serve --sse        # SSE mode for remote clients
    repr mcp serve --port 3001  # Custom port for SSE
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .config import (
    get_tracked_repos,
    get_profile_config,
    load_config,
)
from .storage import (
    list_stories,
    load_story,
    STORIES_DIR,
)

# Create the MCP server
mcp = FastMCP(
    "repr",
    instructions="Developer identity tool — stories from git history. "
    "Generate compelling narratives from your commits, build your developer profile, "
    "and create content from your work.",
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _parse_date_reference(date_str: str) -> str | None:
    """Parse a date reference string into an ISO date string."""
    import re
    
    date_str = date_str.lower().strip()
    
    # Try ISO format first
    try:
        parsed = datetime.fromisoformat(date_str)
        return parsed.isoformat()
    except ValueError:
        pass
    
    # Day names
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if date_str in day_names:
        today = datetime.now()
        target_day = day_names.index(date_str)
        current_day = today.weekday()
        days_back = (current_day - target_day) % 7
        if days_back == 0:
            days_back = 7
        target_date = today - timedelta(days=days_back)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Relative time
    match = re.match(r"(\d+)\s+(day|days|week|weeks|month|months)\s+ago", date_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).rstrip("s")
        if unit == "day":
            delta = timedelta(days=amount)
        elif unit == "week":
            delta = timedelta(weeks=amount)
        elif unit == "month":
            delta = timedelta(days=amount * 30)
        else:
            return None
        target_date = datetime.now() - delta
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Yesterday/today
    if date_str == "yesterday":
        target_date = datetime.now() - timedelta(days=1)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if date_str == "today":
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Last week/month
    if date_str == "last week":
        target_date = datetime.now() - timedelta(weeks=1)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if date_str == "last month":
        target_date = datetime.now() - timedelta(days=30)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    return None


def _get_commits_for_period(
    since: str = "7 days ago",
    repo_path: Optional[str] = None,
) -> list[dict]:
    """Get commits for a time period across tracked repos."""
    from .tools import get_commits_with_diffs
    from .discovery import analyze_repo
    
    since_str = _parse_date_reference(since)
    if not since_str:
        since_str = _parse_date_reference("7 days ago")
    
    if repo_path:
        repo_paths = [Path(repo_path)]
    else:
        tracked = get_tracked_repos()
        repo_paths = [Path(r["path"]) for r in tracked if Path(r["path"]).exists()]
    
    all_commits = []
    for rp in repo_paths:
        try:
            commits = get_commits_with_diffs(rp, count=200, days=90, since=since_str)
            for c in commits:
                c["repo_name"] = rp.name
                c["repo_path"] = str(rp)
            all_commits.extend(commits)
        except Exception:
            continue
    
    # Sort by date
    all_commits.sort(key=lambda c: c.get("date", ""), reverse=True)
    return all_commits


def _format_commits_summary(commits: list[dict]) -> str:
    """Format commits into a readable summary."""
    if not commits:
        return "No commits found for this period."
    
    lines = [f"Found {len(commits)} commits:\n"]
    
    # Group by repo
    by_repo: dict[str, list] = {}
    for c in commits:
        repo = c.get("repo_name", "unknown")
        if repo not in by_repo:
            by_repo[repo] = []
        by_repo[repo].append(c)
    
    for repo, repo_commits in by_repo.items():
        lines.append(f"\n## {repo} ({len(repo_commits)} commits)\n")
        for c in repo_commits[:10]:  # Limit per repo
            sha = c.get("sha", "")[:7]
            msg = c.get("message", "").split("\n")[0][:60]
            lines.append(f"- {sha} {msg}")
        if len(repo_commits) > 10:
            lines.append(f"  ... and {len(repo_commits) - 10} more")
    
    return "\n".join(lines)


# =============================================================================
# MCP TOOLS
# =============================================================================

@mcp.tool()
async def repr_generate(
    repo: Optional[str] = None,
    since: str = "7 days ago",
    template: str = "resume",
    batch_size: int = 5,
    local: bool = True,
) -> str:
    """Generate stories from recent git commits.
    
    Analyzes your git history and creates narrative stories describing
    what you built. Stories are saved locally and can be pushed to repr.dev.
    
    Args:
        repo: Path to specific repo (default: all tracked repos)
        since: Date filter — supports ISO dates, day names, or relative 
               (e.g., "monday", "7 days ago", "2026-01-01")
        template: Output template — resume, changelog, narrative, interview
        batch_size: How many commits to include per story
        local: Use local LLM (True) or cloud (False)
    
    Returns:
        Summary of generated stories with their IDs
    """
    from .tools import get_commits_with_diffs
    from .discovery import analyze_repo
    from .storage import get_processed_commit_shas
    
    since_str = _parse_date_reference(since)
    if not since_str:
        return f"Could not parse date: {since}. Try: '7 days ago', 'monday', '2026-01-01'"
    
    # Get repos
    if repo:
        repo_paths = [Path(repo)]
    else:
        tracked = get_tracked_repos()
        if not tracked:
            return "No repositories tracked. Run `repr repos add <path>` first."
        repo_paths = [Path(r["path"]) for r in tracked if Path(r["path"]).exists()]
    
    if not repo_paths:
        return "No valid repositories found."
    
    results = []
    total_stories = 0
    
    for repo_path in repo_paths:
        try:
            repo_info = analyze_repo(repo_path)
        except Exception as e:
            results.append(f"Error analyzing {repo_path}: {e}")
            continue
        
        # Get commits
        commits = get_commits_with_diffs(repo_path, count=500, days=90, since=since_str)
        if not commits:
            results.append(f"{repo_info.name}: No commits found since {since}")
            continue
        
        # Filter already-processed
        processed_shas = get_processed_commit_shas(repo_name=repo_info.name)
        commits = [c for c in commits if c["full_sha"] not in processed_shas]
        
        if not commits:
            results.append(f"{repo_info.name}: All {len(processed_shas)} commits already processed")
            continue
        
        # Generate stories (using existing async logic)
        from .openai_analysis import get_openai_client, extract_commit_batch
        from .templates import build_generation_prompt
        from .config import get_llm_config
        
        llm_config = get_llm_config()
        
        if local:
            client = get_openai_client(
                api_key=llm_config.get("local_api_key") or "ollama",
                base_url=llm_config.get("local_api_url") or "http://localhost:11434/v1",
            )
            model = llm_config.get("local_model") or "llama3.2"
        else:
            client = get_openai_client()
            model = None
        
        # Split into batches
        batches = [commits[i:i + batch_size] for i in range(0, len(commits), batch_size)]
        stories_generated = []
        
        try:
            for i, batch in enumerate(batches):
                system_prompt, user_prompt = build_generation_prompt(
                    template_name=template,
                    repo_name=repo_info.name,
                    commits=batch,
                )
                
                result = await extract_commit_batch(
                    client=client,
                    commits=batch,
                    batch_num=i + 1,
                    total_batches=len(batches),
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    structured=True,
                )
                
                # Handle result
                from .templates import StoryOutput
                from .storage import save_story
                
                story_outputs = []
                if isinstance(result, list):
                    story_outputs = result
                elif isinstance(result, StoryOutput):
                    story_outputs = [result]
                
                for story_output in story_outputs:
                    if not story_output.content:
                        continue
                    
                    metadata = {
                        "summary": story_output.summary,
                        "repo_name": repo_info.name,
                        "repo_path": str(repo_info.path),
                        "commit_shas": [c["full_sha"] for c in batch],
                        "generated_locally": local,
                        "template": template,
                        "category": story_output.category,
                        "scope": story_output.scope,
                        "stack": story_output.stack,
                    }
                    
                    story_id = save_story(story_output.content, metadata)
                    stories_generated.append({
                        "id": story_id,
                        "summary": story_output.summary,
                    })
                    total_stories += 1
        finally:
            await client.close()
        
        if stories_generated:
            results.append(f"{repo_info.name}: Generated {len(stories_generated)} stories")
            for s in stories_generated:
                results.append(f"  - {s['summary']} (ID: {s['id']})")
        else:
            results.append(f"{repo_info.name}: No stories generated")
    
    summary = f"Generated {total_stories} total stories.\n\n" + "\n".join(results)
    return summary


@mcp.tool()
async def repr_stories_list(
    repo: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> str:
    """List existing stories with metadata.
    
    Args:
        repo: Filter by repository name
        category: Filter by category (feature, bugfix, refactor, perf, infra, docs, test, chore)
        limit: Maximum stories to return
    
    Returns:
        List of stories with ID, summary, repo, and creation date
    """
    stories = list_stories(repo_name=repo, limit=limit)
    
    if category:
        stories = [s for s in stories if s.get("category") == category]
    
    if not stories:
        return "No stories found. Run `repr generate` to create stories from commits."
    
    lines = [f"Found {len(stories)} stories:\n"]
    
    for s in stories[:limit]:
        story_id = s.get("id", "unknown")
        summary = s.get("summary", "Untitled")
        repo_name = s.get("repo_name", "unknown")
        created = s.get("created_at", "")[:10]  # Just date
        cat = s.get("category", "")
        cat_str = f"[{cat}] " if cat else ""
        
        lines.append(f"- {cat_str}{summary}")
        lines.append(f"  ID: {story_id} | Repo: {repo_name} | Created: {created}")
    
    return "\n".join(lines)


@mcp.tool()
async def repr_week() -> str:
    """Weekly summary — what you built in the last 7 days.
    
    Provides a quick overview of your work from the past week,
    including commits across all tracked repositories.
    
    Returns:
        Summary of the week's work
    """
    commits = _get_commits_for_period(since="7 days ago")
    
    if not commits:
        return "No commits found in the last 7 days across tracked repositories."
    
    # Get stories from this week too
    week_ago = datetime.now() - timedelta(days=7)
    recent_stories = list_stories(since=week_ago, limit=20)
    
    lines = [
        "# Weekly Summary\n",
        f"**Period:** Last 7 days (since {week_ago.strftime('%Y-%m-%d')})\n",
    ]
    
    # Stats
    total_commits = len(commits)
    repos = set(c.get("repo_name") for c in commits)
    total_adds = sum(c.get("insertions", 0) for c in commits)
    total_dels = sum(c.get("deletions", 0) for c in commits)
    
    lines.append(f"**Stats:** {total_commits} commits across {len(repos)} repos")
    lines.append(f"**Lines:** +{total_adds} / -{total_dels}\n")
    
    # Recent stories
    if recent_stories:
        lines.append(f"## Stories Generated ({len(recent_stories)})\n")
        for s in recent_stories[:5]:
            lines.append(f"- {s.get('summary', 'Untitled')} ({s.get('repo_name', 'unknown')})")
    
    # Commits by repo
    lines.append("\n## Commits by Repository\n")
    by_repo: dict[str, list] = {}
    for c in commits:
        repo = c.get("repo_name", "unknown")
        if repo not in by_repo:
            by_repo[repo] = []
        by_repo[repo].append(c)
    
    for repo, repo_commits in sorted(by_repo.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n### {repo} ({len(repo_commits)} commits)")
        for c in repo_commits[:5]:
            msg = c.get("message", "").split("\n")[0][:60]
            lines.append(f"- {msg}")
        if len(repo_commits) > 5:
            lines.append(f"  ... and {len(repo_commits) - 5} more")
    
    lines.append("\n---")
    lines.append("Run `repr generate --since '7 days ago'` to turn these into stories.")
    
    return "\n".join(lines)


@mcp.tool()
async def repr_standup() -> str:
    """Quick standup — what you did yesterday and today.
    
    Perfect for daily standups or quick status updates.
    Shows commits from the last 2 days.
    
    Returns:
        Summary suitable for a standup meeting
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    
    commits = _get_commits_for_period(since="2 days ago")
    
    if not commits:
        return "No commits found in the last 2 days."
    
    # Split into yesterday and today
    today_commits = []
    yesterday_commits = []
    
    for c in commits:
        try:
            commit_date = datetime.fromisoformat(c.get("date", "").replace("Z", "+00:00"))
            if commit_date.date() >= today.date():
                today_commits.append(c)
            elif commit_date.date() >= yesterday.date():
                yesterday_commits.append(c)
        except (ValueError, TypeError):
            yesterday_commits.append(c)
    
    lines = ["# Standup Summary\n"]
    
    if yesterday_commits:
        lines.append("## Yesterday")
        for c in yesterday_commits[:10]:
            repo = c.get("repo_name", "")
            msg = c.get("message", "").split("\n")[0][:50]
            lines.append(f"- [{repo}] {msg}")
        if len(yesterday_commits) > 10:
            lines.append(f"  ... and {len(yesterday_commits) - 10} more")
        lines.append("")
    
    if today_commits:
        lines.append("## Today")
        for c in today_commits[:10]:
            repo = c.get("repo_name", "")
            msg = c.get("message", "").split("\n")[0][:50]
            lines.append(f"- [{repo}] {msg}")
        if len(today_commits) > 10:
            lines.append(f"  ... and {len(today_commits) - 10} more")
    
    if not today_commits:
        lines.append("## Today\nNo commits yet today.")
    
    return "\n".join(lines)


@mcp.tool()
async def repr_profile() -> str:
    """Get your developer profile.
    
    Returns your repr profile information including bio,
    skills, and profile settings.
    
    Returns:
        Your developer profile as markdown
    """
    profile = get_profile_config()
    
    lines = ["# Developer Profile\n"]
    
    username = profile.get("username")
    if username:
        lines.append(f"**Username:** @{username}")
        if profile.get("claimed"):
            lines.append(f"**Profile URL:** https://repr.dev/@{username}")
    
    bio = profile.get("bio")
    if bio:
        lines.append(f"\n## Bio\n{bio}")
    
    location = profile.get("location")
    if location:
        lines.append(f"\n**Location:** {location}")
    
    website = profile.get("website")
    if website:
        lines.append(f"**Website:** {website}")
    
    # Show story stats
    all_stories = list_stories(limit=1000)
    if all_stories:
        lines.append(f"\n## Stats")
        lines.append(f"- Total stories: {len(all_stories)}")
        
        # Categories
        categories: dict[str, int] = {}
        for s in all_stories:
            cat = s.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1
        
        if categories:
            lines.append("- By category:")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  - {cat}: {count}")
    
    # Tracked repos
    tracked = get_tracked_repos()
    if tracked:
        lines.append(f"\n## Tracked Repositories ({len(tracked)})")
        for r in tracked[:10]:
            lines.append(f"- {Path(r['path']).name}")
    
    return "\n".join(lines)


# =============================================================================
# TIMELINE & SESSION TOOLS (Phase 5)
# =============================================================================

@mcp.tool()
async def init_project(
    repo_path: str,
    include_sessions: bool = True,
    session_source: str = "auto",
    days_back: int = 90,
    max_commits: int = 500,
) -> dict:
    """
    Initialize repr for a project with unified timeline.
    
    Creates .repr/timeline.json with commits and optionally AI session context.
    Use this before querying context from a project.
    
    Args:
        repo_path: Path to the git repository
        include_sessions: Include AI session context (Claude Code, Clawdbot)
        session_source: "auto" (detect), "claude_code", "clawdbot", or "none"
        days_back: Number of days of history to include
        max_commits: Maximum commits to include
    
    Returns:
        Initialization status with stats
    """
    from pathlib import Path
    from .timeline import (
        detect_project_root,
        is_initialized,
        init_timeline_commits_only,
        init_timeline_with_sessions,
        get_timeline_stats,
    )
    from .loaders import detect_session_source
    
    project_path = Path(repo_path).resolve()
    
    # Verify it's a git repo
    repo_root = detect_project_root(project_path)
    if not repo_root:
        return {"success": False, "error": f"Not a git repository: {repo_path}"}
    
    project_path = repo_root
    
    # Check if already initialized
    if is_initialized(project_path):
        return {
            "success": True,
            "already_initialized": True,
            "project": str(project_path),
            "message": "Timeline already exists. Use get_context to query it.",
        }
    
    # Determine session sources
    session_sources = []
    if include_sessions and session_source != "none":
        if session_source == "auto":
            session_sources = detect_session_source(project_path)
        else:
            session_sources = [session_source]
    
    try:
        if session_sources:
            # Get API key, base_url, and model - check all sources including local LLM
            from .config import get_byok_config, get_litellm_config, get_llm_config
            import os

            api_key = None
            base_url = None
            model = None

            # Check BYOK first
            byok_config = get_byok_config("openai")
            if byok_config:
                api_key = byok_config.get("api_key")
                base_url = byok_config.get("base_url")

            # Check local LLM config
            if not api_key:
                llm_config = get_llm_config()
                if llm_config.get("default") == "local" and llm_config.get("local_api_key"):
                    api_key = llm_config["local_api_key"]
                    base_url = llm_config.get("local_api_url")
                    model = llm_config.get("local_model")

            # Check LiteLLM (cloud)
            if not api_key:
                _, api_key = get_litellm_config()

            # Check environment
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY")

            if not api_key:
                # Fall back to commits only
                session_sources = []
        
        if session_sources:
            kwargs = {
                "days": days_back,
                "max_commits": max_commits,
                "session_sources": session_sources,
                "api_key": api_key,
                "base_url": base_url,
            }
            if model:
                kwargs["model"] = model
            timeline = await init_timeline_with_sessions(project_path, **kwargs)
        else:
            timeline = init_timeline_commits_only(
                project_path,
                days=days_back,
                max_commits=max_commits,
            )
        
        stats = get_timeline_stats(timeline)
        
        return {
            "success": True,
            "project": str(project_path),
            "timeline_path": str(project_path / ".repr" / "timeline.json"),
            "session_sources": session_sources,
            "stats": {
                "total_entries": stats["total_entries"],
                "commits": stats["commit_count"],
                "sessions": stats["session_count"],
                "merged": stats["merged_count"],
            },
        }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def ingest_session(
    session_file: Optional[str] = None,
    project_path: Optional[str] = None,
    session_source: str = "auto",
) -> dict:
    """
    Ingest a completed AI session into the timeline.
    
    Called by SessionEnd hooks to capture context from AI coding sessions.
    Extracts structured context (problem, approach, decisions, outcome)
    and links to related commits.
    
    Args:
        session_file: Path to session JSONL file
        project_path: Project path (auto-detected from session cwd if not provided)
        session_source: "auto", "claude_code", or "clawdbot"
    
    Returns:
        Ingestion result with extracted context summary
    """
    from pathlib import Path
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        save_timeline,
        extract_commits_from_git,
    )
    from .models import (
        TimelineEntry,
        TimelineEntryType,
        match_commits_to_sessions,
    )
    from .loaders import ClaudeCodeLoader, ClawdbotLoader
    from .session_extractor import SessionExtractor
    from .config import get_byok_config, get_litellm_config
    import os
    
    if not session_file:
        return {"success": False, "error": "session_file is required"}
    
    file_path = Path(session_file).resolve()
    if not file_path.exists():
        return {"success": False, "error": f"Session file not found: {session_file}"}
    
    # Determine source
    if session_source == "auto":
        if ".claude" in str(file_path):
            session_source = "claude_code"
        elif ".clawdbot" in str(file_path):
            session_source = "clawdbot"
        else:
            session_source = "claude_code"  # Default
    
    # Load session
    if session_source == "claude_code":
        loader = ClaudeCodeLoader()
    elif session_source == "clawdbot":
        loader = ClawdbotLoader()
    else:
        return {"success": False, "error": f"Unknown source: {session_source}"}
    
    session = loader.load_session(file_path)
    if not session:
        return {"success": False, "error": "Failed to load session"}
    
    # Determine project path
    if project_path:
        proj_path = Path(project_path).resolve()
    elif session.cwd:
        proj_path = detect_project_root(Path(session.cwd))
    else:
        proj_path = None
    
    if not proj_path:
        return {"success": False, "error": "Could not detect project path. Provide project_path."}
    
    # Check timeline exists
    if not is_initialized(proj_path):
        return {
            "success": False,
            "error": f"Timeline not initialized for {proj_path}",
            "hint": "Run init_project first",
        }
    
    # Load timeline
    timeline = load_timeline(proj_path)
    if not timeline:
        return {"success": False, "error": "Failed to load timeline"}
    
    # Check if already ingested
    for entry in timeline.entries:
        if entry.session_context and entry.session_context.session_id == session.id:
            return {
                "success": True,
                "skipped": True,
                "reason": "Session already ingested",
                "session_id": session.id,
            }
    
    # Get API key
    api_key = None
    byok_config = get_byok_config("openai")
    if byok_config:
        api_key = byok_config.get("api_key")
    if not api_key:
        _, api_key = get_litellm_config()
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        return {"success": False, "error": "No API key for extraction"}
    
    # Extract context
    try:
        extractor = SessionExtractor(api_key=api_key)
        context = await extractor.extract_context(session)
    except Exception as e:
        return {"success": False, "error": f"Extraction failed: {e}"}
    
    # Get recent commits to link
    recent_commits = extract_commits_from_git(proj_path, days=1, max_commits=50)
    
    if recent_commits:
        matches = match_commits_to_sessions(recent_commits, [session])
        context.linked_commits = [m.commit_sha for m in matches if m.session_id == session.id]
    
    # Create entry
    entry_type = TimelineEntryType.SESSION
    
    # Try to merge with existing commit entries
    if context.linked_commits:
        for commit_sha in context.linked_commits:
            for entry in timeline.entries:
                if entry.commit and entry.commit.sha == commit_sha:
                    entry.session_context = context
                    entry.type = TimelineEntryType.MERGED
                    entry_type = None
                    break
            if entry_type is None:
                break
    
    # Add standalone if not merged
    if entry_type is not None:
        entry = TimelineEntry(
            timestamp=context.timestamp,
            type=entry_type,
            commit=None,
            session_context=context,
            story=None,
        )
        timeline.add_entry(entry)
    
    # Save
    save_timeline(timeline, proj_path)
    
    return {
        "success": True,
        "session_id": session.id,
        "project": str(proj_path),
        "context": {
            "problem": context.problem[:200],
            "approach": context.approach[:200],
            "decisions": context.decisions[:3],
            "outcome": context.outcome,
            "files_modified": context.files_modified[:10],
        },
        "linked_commits": context.linked_commits,
        "entry_type": entry_type.value if entry_type else "merged",
    }


@mcp.tool()
async def get_context(
    query: str,
    project: Optional[str] = None,
    days_back: int = 30,
    include_sessions: bool = True,
    limit: int = 10,
) -> list[dict]:
    """
    Query developer context from the timeline.
    
    Searches through commits and session context to find relevant
    information about how this developer approaches problems.
    
    Args:
        query: Natural language query (e.g., "how do I handle auth", "what patterns for caching")
        project: Project path (default: current directory or all tracked repos)
        days_back: How many days of history to search
        include_sessions: Include session context in results
        limit: Maximum results to return
    
    Returns:
        List of relevant context entries with problem, approach, decisions, etc.
    """
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        query_timeline,
    )
    from .models import TimelineEntryType
    from .config import get_tracked_repos
    
    results = []
    
    # Determine projects to search
    projects = []
    if project:
        proj_path = Path(project).resolve()
        repo_root = detect_project_root(proj_path)
        if repo_root and is_initialized(repo_root):
            projects.append(repo_root)
    else:
        # Try current directory
        cwd_root = detect_project_root(Path.cwd())
        if cwd_root and is_initialized(cwd_root):
            projects.append(cwd_root)
        
        # Also check tracked repos
        for repo in get_tracked_repos():
            repo_path = Path(repo["path"])
            if repo_path.exists() and is_initialized(repo_path):
                if repo_path not in projects:
                    projects.append(repo_path)
    
    if not projects:
        return [{
            "error": "No initialized projects found",
            "hint": "Run init_project first or specify a project path",
        }]
    
    # Query keywords from natural language
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    for proj_path in projects:
        timeline = load_timeline(proj_path)
        if not timeline:
            continue
        
        # Get entries in time range
        entries = query_timeline(timeline, since=since)
        
        for entry in entries:
            score = 0.0
            matched_fields = []
            
            # Score based on commit message
            if entry.commit:
                msg_lower = entry.commit.message.lower()
                for word in query_words:
                    if word in msg_lower:
                        score += 0.3
                        matched_fields.append("commit_message")
                        break
                
                # Check files
                for f in entry.commit.files:
                    f_lower = f.lower()
                    for word in query_words:
                        if word in f_lower:
                            score += 0.2
                            matched_fields.append("files")
                            break
            
            # Score based on session context
            if entry.session_context and include_sessions:
                ctx = entry.session_context
                
                # Check problem
                if any(word in ctx.problem.lower() for word in query_words):
                    score += 0.5
                    matched_fields.append("problem")
                
                # Check approach
                if any(word in ctx.approach.lower() for word in query_words):
                    score += 0.4
                    matched_fields.append("approach")
                
                # Check decisions
                for decision in ctx.decisions:
                    if any(word in decision.lower() for word in query_words):
                        score += 0.3
                        matched_fields.append("decisions")
                        break
                
                # Check lessons
                for lesson in ctx.lessons:
                    if any(word in lesson.lower() for word in query_words):
                        score += 0.3
                        matched_fields.append("lessons")
                        break
            
            if score > 0:
                result = {
                    "score": round(score, 2),
                    "matched_fields": list(set(matched_fields)),
                    "project": proj_path.name,
                    "timestamp": entry.timestamp.isoformat(),
                    "type": entry.type.value,
                }
                
                if entry.commit:
                    result["commit"] = {
                        "sha": entry.commit.sha[:8],
                        "message": entry.commit.message.split("\n")[0][:100],
                        "files": entry.commit.files[:5],
                    }
                
                if entry.session_context:
                    ctx = entry.session_context
                    result["context"] = {
                        "problem": ctx.problem,
                        "approach": ctx.approach,
                        "decisions": ctx.decisions,
                        "outcome": ctx.outcome,
                        "lessons": ctx.lessons,
                    }
                
                results.append(result)
    
    # Sort by score and limit
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# =============================================================================
# STORY-CENTRIC TOOLS (Phase 7)
# =============================================================================

@mcp.tool()
async def search_stories(
    query: str,
    files: Optional[list[str]] = None,
    since: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search developer stories using the content index.
    
    Efficiently finds relevant stories by keyword, file, or time range.
    Returns Story objects with full WHY/WHAT context.
    
    Args:
        query: Keywords to search (matches title, problem, keywords)
        files: Optional file paths to filter by
        since: Optional time filter (e.g., "7 days ago", "2026-01-01")
        category: Optional category filter (feature, bugfix, refactor, etc.)
        limit: Maximum stories to return
    
    Returns:
        List of matching stories with context
    """
    from pathlib import Path
    from .timeline import detect_project_root, is_initialized
    from .storage import load_repr_store
    from .config import get_tracked_repos
    
    results = []
    query_words = set(query.lower().split())
    
    # Find all initialized projects
    projects = []
    cwd_root = detect_project_root(Path.cwd())
    if cwd_root and is_initialized(cwd_root):
        projects.append(cwd_root)
    
    for repo in get_tracked_repos():
        repo_path = Path(repo["path"])
        if repo_path.exists() and is_initialized(repo_path):
            if repo_path not in projects:
                projects.append(repo_path)
    
    for proj_path in projects:
        try:
            store = load_repr_store(proj_path)
            if not store:
                continue
            
            # Use index for efficient lookup
            index = store.index
            matching_story_ids = set()
            
            # Search by file
            if files:
                for f in files:
                    if f in index.files_to_stories:
                        matching_story_ids.update(index.files_to_stories[f])
            
            # Search by keyword
            for word in query_words:
                if word in index.keywords_to_stories:
                    if files:
                        # AND with file matches
                        matching_story_ids &= set(index.keywords_to_stories[word])
                    else:
                        matching_story_ids.update(index.keywords_to_stories[word])
            
            # Get full stories
            story_map = {s.id: s for s in store.stories}
            
            for story_id in matching_story_ids:
                if story_id not in story_map:
                    continue
                story = story_map[story_id]
                
                # Apply category filter
                if category and story.category != category:
                    continue
                
                # Score by relevance
                score = 0.0
                if any(word in story.title.lower() for word in query_words):
                    score += 0.5
                if any(word in story.problem.lower() for word in query_words):
                    score += 0.4
                if files and any(f in story.files for f in files):
                    score += 0.3
                
                results.append({
                    "score": round(score, 2),
                    "project": proj_path.name,
                    "story": {
                        "id": story.id,
                        "title": story.title,
                        "problem": story.problem,
                        "approach": story.approach,
                        "implementation_details": story.implementation_details,
                        "decisions": story.decisions,
                        "outcome": story.outcome,
                        "lessons": story.lessons,
                        "category": story.category,
                        "files": story.files[:10],
                        "commit_count": len(story.commit_shas),
                        "session_count": len(story.session_ids),
                        "started_at": story.started_at.isoformat() if story.started_at else None,
                    }
                })
        except Exception:
            continue
    
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


@mcp.tool()
async def get_story(story_id: str) -> dict:
    """
    Get full details of a specific story by ID.
    
    Args:
        story_id: Story UUID
    
    Returns:
        Complete story with all context and linked commits/sessions
    """
    from pathlib import Path
    from .timeline import detect_project_root, is_initialized
    from .storage import load_repr_store
    from .config import get_tracked_repos
    
    # Search all projects for the story
    projects = []
    cwd_root = detect_project_root(Path.cwd())
    if cwd_root and is_initialized(cwd_root):
        projects.append(cwd_root)
    
    for repo in get_tracked_repos():
        repo_path = Path(repo["path"])
        if repo_path.exists() and is_initialized(repo_path):
            projects.append(repo_path)
    
    for proj_path in projects:
        try:
            store = load_repr_store(proj_path)
            if not store:
                continue
            
            for story in store.stories:
                if story.id == story_id:
                    # Get linked commits
                    commits = [c for c in store.commits if c.sha in story.commit_shas]
                    # Get linked sessions
                    sessions = [s for s in store.sessions if s.session_id in story.session_ids]
                    
                    return {
                        "found": True,
                        "project": proj_path.name,
                        "story": story.model_dump(),
                        "commits": [
                            {"sha": c.sha[:8], "message": c.message, "files": c.files}
                            for c in commits
                        ],
                        "sessions": [
                            {"id": s.session_id, "problem": s.problem, "approach": s.approach}
                            for s in sessions
                        ],
                    }
        except Exception:
            continue
    
    return {"found": False, "story_id": story_id}


@mcp.tool()
async def list_recent_stories(
    days: int = 7,
    category: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    List recent stories from the timeline.
    
    Args:
        days: Number of days to look back
        category: Optional category filter
        limit: Maximum stories to return
    
    Returns:
        List of recent stories with summaries
    """
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from .timeline import detect_project_root, is_initialized
    from .storage import load_repr_store
    from .config import get_tracked_repos
    
    results = []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Find all projects
    projects = []
    cwd_root = detect_project_root(Path.cwd())
    if cwd_root and is_initialized(cwd_root):
        projects.append(cwd_root)
    
    for repo in get_tracked_repos():
        repo_path = Path(repo["path"])
        if repo_path.exists() and is_initialized(repo_path):
            if repo_path not in projects:
                projects.append(repo_path)
    
    for proj_path in projects:
        try:
            store = load_repr_store(proj_path)
            if not store:
                continue
            
            for story in store.stories:
                # Filter by time
                story_time = story.started_at or story.created_at
                if story_time < since:
                    continue
                
                # Filter by category
                if category and story.category != category:
                    continue
                
                results.append({
                    "project": proj_path.name,
                    "id": story.id,
                    "title": story.title,
                    "problem": story.problem[:200] if story.problem else "",
                    "category": story.category,
                    "commit_count": len(story.commit_shas),
                    "session_count": len(story.session_ids),
                    "implementation_detail_count": len(story.implementation_details),
                    "timestamp": story_time.isoformat(),
                })
        except Exception:
            continue
    
    # Sort by time descending
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:limit]


# =============================================================================
# MCP RESOURCES
# =============================================================================


@mcp.resource("repr://profile")
async def get_profile_resource() -> str:
    """Current developer profile."""
    return await repr_profile()


@mcp.resource("repr://stories/recent")
async def get_recent_stories_resource() -> str:
    """Last 10 stories."""
    return await repr_stories_list(limit=10)


# =============================================================================
# SERVER RUNNER
# =============================================================================

def run_server(
    sse: bool = False,
    port: int = 3001,
    host: str = "127.0.0.1",
) -> None:
    """Run the MCP server.
    
    Args:
        sse: Use SSE transport instead of stdio
        port: Port for SSE mode
        host: Host for SSE mode
    """
    if sse:
        # SSE mode for remote/web clients
        mcp.run(transport="sse", host=host, port=port)
    else:
        # Default stdio mode for local MCP clients
        mcp.run()


if __name__ == "__main__":
    run_server()
