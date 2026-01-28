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
