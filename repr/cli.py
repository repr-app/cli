"""
repr CLI - understand what you've actually worked on.

Commands follow the CLI_SPECIFICATION.md structure:
- init: First-time setup
- generate: Create stories from commits
- week/since/standup: Quick reflection summaries
- stories: Manage stories
- push/sync/pull: Cloud operations
- repos/hooks: Repository management
- login/logout/whoami: Authentication
- llm: LLM configuration
- privacy/config/data: Privacy and data management
- profile: Profile management
- doctor: Health check
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from collections import defaultdict

import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import __version__
from .ui import (
    console,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_next_steps,
    print_markdown,
    print_auth_code,
    create_spinner,
    create_table,
    format_relative_time,
    format_bytes,
    confirm,
    BRAND_PRIMARY,
    BRAND_SUCCESS,
    BRAND_WARNING,
    BRAND_ERROR,
    BRAND_MUTED,
)
from .config import (
    CONFIG_DIR,
    CONFIG_FILE,
    load_config,
    save_config,
    is_authenticated,
    get_access_token,
    get_llm_config,
    get_litellm_config,
    set_dev_mode,
    is_dev_mode,
    get_api_base,
    get_tracked_repos,
    add_tracked_repo,
    remove_tracked_repo,
    set_llm_config,
    get_config_value,
    set_config_value,
    is_cloud_allowed,
    lock_local_only,
    unlock_local_only,
    get_privacy_settings,
    add_byok_provider,
    remove_byok_provider,
    get_byok_config,
    list_byok_providers,
    BYOK_PROVIDERS,
    get_default_llm_mode,
    set_repo_hook_status,
    set_repo_paused,
    get_profile_config,
    set_profile_config,
)
from .storage import (
    save_story,
    load_story,
    delete_story,
    list_stories,
    get_story_count,
    get_unpushed_stories,
    mark_story_pushed,
    update_story_metadata,
    STORIES_DIR,
    backup_all_data,
    restore_from_backup,
    get_storage_stats,
)
from .auth import AuthFlow, AuthError, logout as auth_logout, get_current_user, migrate_plaintext_auth
from .api import APIError

# Create Typer app
app = typer.Typer(
    name="repr",
    help="repr - understand what you've actually worked on",
    add_completion=False,
    no_args_is_help=True,
)

# Sub-apps for command groups
hooks_app = typer.Typer(help="Manage git post-commit hooks")
llm_app = typer.Typer(help="Configure LLM (local/cloud/BYOK)")
privacy_app = typer.Typer(help="Privacy audit and controls")
config_app = typer.Typer(help="View and modify configuration")
data_app = typer.Typer(help="Backup, restore, and manage data")
profile_app = typer.Typer(help="View and manage profile")

app.add_typer(hooks_app, name="hooks")
app.add_typer(llm_app, name="llm")
app.add_typer(privacy_app, name="privacy")
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(profile_app, name="profile")


def version_callback(value: bool):
    if value:
        console.print(f"repr v{__version__}")
        raise typer.Exit()


def dev_callback(value: bool):
    if value:
        set_dev_mode(True)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    dev: bool = typer.Option(
        False, "--dev",
        callback=dev_callback,
        is_eager=True,
        help="Use localhost backend.",
    ),
):
    """repr - understand what you've actually worked on.
    
    Cloud features require sign-in. Local generation always works offline.
    """
    # Migrate plaintext auth tokens on startup
    migrate_plaintext_auth()
    
    # Track command usage (if telemetry enabled)
    from .telemetry import track_command
    if ctx.invoked_subcommand:
        track_command(ctx.invoked_subcommand)


# =============================================================================
# INIT
# =============================================================================

@app.command()
def init(
    path: Optional[Path] = typer.Argument(
        None,
        help="Directory to scan for repositories (default: ~/code)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
):
    """
    Initialize repr - scan for repositories and set up local config.
    
    Example:
        repr init
        repr init ~/projects
    """
    print_header()
    console.print("Works locally first — sign in later for sync and sharing.")
    console.print()
    
    # Determine scan path
    scan_path = path or Path.home() / "code"
    if not scan_path.exists():
        scan_path = Path.cwd()
    
    console.print(f"Scanning {scan_path} for repositories...")
    console.print()
    
    # Import discovery
    from .discovery import discover_repos
    
    with create_spinner() as progress:
        task = progress.add_task("Scanning...", total=None)
        repos = discover_repos([scan_path], min_commits=5)
    
    if not repos:
        print_warning(f"No repositories found in {scan_path}")
        print_info("Try running: repr init <path-to-your-code>")
        raise typer.Exit(1)
    
    console.print(f"Found [bold]{len(repos)}[/] repositories")
    console.print()
    
    for repo in repos[:10]:  # Show first 10
        lang = repo.primary_language or "Unknown"
        console.print(f"✓ {repo.name} ({repo.commit_count} commits) [{lang}]")
    
    if len(repos) > 10:
        console.print(f"  ... and {len(repos) - 10} more")
    
    console.print()
    
    # Ask to track
    if confirm("Track these repositories?", default=True):
        for repo in repos:
            add_tracked_repo(str(repo.path))
        print_success(f"Tracking {len(repos)} repositories")
    
    # Check for local LLM
    console.print()
    from .llm import detect_local_llm
    llm_info = detect_local_llm()
    if llm_info:
        console.print(f"Local LLM: detected {llm_info.name} at {llm_info.url}")
    else:
        console.print(f"[{BRAND_MUTED}]Local LLM: not detected (install Ollama for offline generation)[/]")
    
    console.print()
    print_next_steps([
        "repr week               See what you worked on this week",
        "repr generate --local   Save stories permanently",
        "repr login              Unlock cloud sync and publishing",
    ])


# =============================================================================
# GENERATE
# =============================================================================

def _parse_date_reference(date_str: str) -> str | None:
    """
    Parse a date reference string into an ISO date string.
    
    Supports:
    - ISO dates: "2024-01-01"
    - Day names: "monday", "tuesday", etc.
    - Relative: "3 days ago", "2 weeks ago", "1 month ago"
    
    Returns ISO date string or None if parsing fails.
    """
    import re
    from datetime import datetime, timedelta
    
    date_str = date_str.lower().strip()
    
    # Try ISO format first
    try:
        parsed = datetime.fromisoformat(date_str)
        return parsed.isoformat()
    except ValueError:
        pass
    
    # Day names (find previous occurrence)
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if date_str in day_names:
        today = datetime.now()
        target_day = day_names.index(date_str)
        current_day = today.weekday()
        
        # Calculate days back to that day
        days_back = (current_day - target_day) % 7
        if days_back == 0:
            days_back = 7  # Go to last week's occurrence
        
        target_date = today - timedelta(days=days_back)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Relative time: "N days/weeks/months ago"
    match = re.match(r"(\d+)\s+(day|days|week|weeks|month|months)\s+ago", date_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).rstrip("s")  # Normalize to singular
        
        if unit == "day":
            delta = timedelta(days=amount)
        elif unit == "week":
            delta = timedelta(weeks=amount)
        elif unit == "month":
            delta = timedelta(days=amount * 30)  # Approximate
        else:
            return None
        
        target_date = datetime.now() - delta
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # "yesterday" / "today"
    if date_str == "yesterday":
        target_date = datetime.now() - timedelta(days=1)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if date_str == "today":
        target_date = datetime.now()
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # "last week" / "last month"
    if date_str == "last week":
        target_date = datetime.now() - timedelta(weeks=1)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if date_str == "last month":
        target_date = datetime.now() - timedelta(days=30)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    return None


@app.command()
def generate(
    local: bool = typer.Option(
        False, "--local", "-l",
        help="Use local LLM (Ollama)",
    ),
    cloud: bool = typer.Option(
        False, "--cloud",
        help="Use cloud LLM (requires login)",
    ),
    repo: Optional[Path] = typer.Option(
        None, "--repo",
        help="Generate for specific repo",
        exists=True,
        dir_okay=True,
    ),
    commits: Optional[str] = typer.Option(
        None, "--commits",
        help="Generate from specific commits (comma-separated)",
    ),
    since_date: Optional[str] = typer.Option(
        None, "--since",
        help="Generate from commits since date (e.g., '2024-01-01', 'monday', '2 weeks ago')",
    ),
    days: Optional[int] = typer.Option(
        None, "--days",
        help="Generate from commits in the last N days",
    ),
    batch_size: int = typer.Option(
        5, "--batch-size",
        help="Commits per story",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Preview what would be sent",
    ),
    template: str = typer.Option(
        "resume", "--template", "-t",
        help="Template: resume, changelog, narrative, interview",
    ),
    prompt: Optional[str] = typer.Option(
        None, "--prompt", "-p",
        help="Custom prompt to append",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Generate stories from commits.
    
    Examples:
        repr generate --local
        repr generate --cloud
        repr generate --since "2 weeks ago"
        repr generate --days 30
        repr generate --template changelog
        repr generate --commits abc123,def456
    """
    from .privacy import check_cloud_permission, log_cloud_operation
    
    # Determine mode
    if cloud:
        allowed, reason = check_cloud_permission("cloud_generation")
        if not allowed:
            if json_output:
                print(json.dumps({"generated": 0, "stories": [], "error": f"Cloud generation blocked: {reason}"}, indent=2))
                raise typer.Exit(1)
            print_error("Cloud generation blocked")
            print_info(reason)
            console.print()
            print_info("Local generation is available:")
            console.print("  repr generate --local")
            raise typer.Exit(1)
    
    if not local and not cloud:
        # Default: local if not signed in, cloud if signed in
        if is_authenticated() and is_cloud_allowed():
            cloud = True
        else:
            local = True
    
    if not json_output:
        print_header()
    
    mode_str = "local LLM" if local else "cloud LLM"
    
    # Build timeframe string for display
    if commits:
        timeframe_str = f"specific commits"
    elif since_date:
        timeframe_str = f"since {since_date}"
    elif days:
        timeframe_str = f"last {days} days"
    else:
        timeframe_str = "last 90 days"
    
    if not json_output:
        console.print(f"Generating stories ({mode_str}, {timeframe_str})...")
        console.print()
    
    # Get repos to analyze
    if repo:
        repo_paths = [repo]
    else:
        tracked = get_tracked_repos()
        if not tracked:
            if json_output:
                print(json.dumps({"generated": 0, "stories": [], "error": "No repositories tracked"}, indent=2))
                raise typer.Exit(1)
            print_warning("No repositories tracked.")
            print_info("Run `repr init` or `repr repos add <path>` first.")
            raise typer.Exit(1)
        repo_paths = [Path(r["path"]) for r in tracked if Path(r["path"]).exists()]
    
    if not repo_paths:
        if json_output:
            print(json.dumps({"generated": 0, "stories": [], "error": "No valid repositories found"}, indent=2))
            raise typer.Exit(1)
        print_error("No valid repositories found")
        raise typer.Exit(1)
    
    # Get commits
    from .tools import get_commits_with_diffs, get_commits_by_shas
    from .discovery import analyze_repo
    
    total_stories = 0
    all_stories = []  # Collect all generated stories for JSON output
    
    for repo_path in repo_paths:
        repo_info = analyze_repo(repo_path)
        if not json_output:
            console.print(f"[bold]{repo_info.name}[/]")
        
        if commits:
            # Specific commits
            commit_shas = [s.strip() for s in commits.split(",")]
            commit_list = get_commits_by_shas(repo_path, commit_shas)
        else:
            # Determine timeframe
            timeframe_days = days if days is not None else 90  # Default 90 days
            since_str = None
            
            # Parse natural language date if provided
            if since_date:
                since_str = _parse_date_reference(since_date)
            
            # Recent commits within timeframe
            commit_list = get_commits_with_diffs(
                repo_path, 
                count=500,  # Higher limit when filtering by time
                days=timeframe_days,
                since=since_str,
            )
        
        if not commit_list:
            if not json_output:
                console.print(f"  [{BRAND_MUTED}]No commits found[/]")
            continue
        
        # Dry run: show what would be sent
        if dry_run:
            from .openai_analysis import estimate_tokens, get_batch_size
            from .config import load_config

            config = load_config()
            max_commits = config.get("generation", {}).get("max_commits_per_batch", 50)
            token_limit = config.get("generation", {}).get("token_limit", 100000)

            console.print(f"  [bold]Dry Run Preview[/]")
            console.print(f"  Commits to analyze: {len(commit_list)}")
            console.print(f"  Template: {template}")
            console.print()

            # Estimate tokens
            estimated_tokens = estimate_tokens(commit_list)
            console.print(f"  Estimated tokens: ~{estimated_tokens:,}")

            # Check if we need to split into batches
            if len(commit_list) > max_commits:
                num_batches = (len(commit_list) + max_commits - 1) // max_commits
                console.print()
                console.print(f"  ⚠ {len(commit_list)} commits exceeds {max_commits}-commit limit")
                console.print()
                console.print(f"  Will split into {num_batches} batches:")
                for batch_num in range(num_batches):
                    start = batch_num * max_commits + 1
                    end = min((batch_num + 1) * max_commits, len(commit_list))
                    batch_commits = commit_list[batch_num * max_commits:end]
                    batch_tokens = estimate_tokens(batch_commits)
                    console.print(f"    Batch {batch_num + 1}: commits {start}-{end} (est. {batch_tokens // 1000}k tokens)")

            console.print()
            console.print("  Sample commits:")
            for c in commit_list[:5]:
                console.print(f"    • {c['sha'][:7]} {c['message'][:50]}")
            if len(commit_list) > 5:
                console.print(f"    ... and {len(commit_list) - 5} more")
            continue
        
        # Check token limits and prompt user if needed
        from .openai_analysis import estimate_tokens
        from .config import load_config

        config = load_config()
        max_commits = config.get("generation", {}).get("max_commits_per_batch", 50)
        token_limit = config.get("generation", {}).get("token_limit", 100000)

        # Check if we exceed limits (only warn for cloud generation)
        if cloud and len(commit_list) > max_commits:
            num_batches = (len(commit_list) + max_commits - 1) // max_commits
            console.print()
            console.print(f"  ⚠ {len(commit_list)} commits exceeds {max_commits}-commit limit")
            console.print()
            console.print(f"  Will split into {num_batches} batches:")
            for batch_num in range(num_batches):
                start = batch_num * max_commits + 1
                end = min((batch_num + 1) * max_commits, len(commit_list))
                batch_commits = commit_list[batch_num * max_commits:end]
                batch_tokens = estimate_tokens(batch_commits)
                console.print(f"    Batch {batch_num + 1}: commits {start}-{end} (est. {batch_tokens // 1000}k tokens)")
            console.print()

            if not confirm("Continue with generation?"):
                console.print(f"  [{BRAND_MUTED}]Skipped {repo_info.name}[/]")
                continue

        # Generate stories
        stories = _generate_stories(
            commits=commit_list,
            repo_info=repo_info,
            batch_size=batch_size,
            local=local,
            template=template,
            custom_prompt=prompt,
        )
        
        for story in stories:
            if not json_output:
                console.print(f"  • {story['summary']}")
            total_stories += 1
            all_stories.append(story)
        
        # Log cloud operation if using cloud
        if cloud and stories:
            log_cloud_operation(
                operation="cloud_generation",
                destination="repr.dev",
                payload_summary={
                    "repo": repo_info.name,
                    "commits": len(commit_list),
                    "stories_generated": len(stories),
                },
                bytes_sent=len(str(commit_list)) // 2,  # Rough estimate
            )
        
        if not json_output:
            console.print()
    
    if json_output:
        print(json.dumps({"generated": total_stories, "stories": all_stories}, indent=2, default=str))
        return
    
    if dry_run:
        console.print()
        console.print("Continue with generation? (run without --dry-run)")
    else:
        print_success(f"Generated {total_stories} stories")
        console.print()
        console.print(f"Stories saved to: {STORIES_DIR}")
        print_next_steps([
            "repr stories            View your stories",
            "repr push               Publish to repr.dev (requires login)",
        ])


async def _generate_stories_async(
    commits: list[dict],
    repo_info,
    batch_size: int,
    local: bool,
    template: str = "resume",
    custom_prompt: str | None = None,
) -> list[dict]:
    """Generate stories from commits using LLM (async implementation)."""
    from .openai_analysis import get_openai_client, extract_commit_batch
    from .templates import build_generation_prompt
    
    stories = []
    
    # Split into batches
    batches = [
        commits[i:i + batch_size]
        for i in range(0, len(commits), batch_size)
    ]
    
    # Create client once, reuse for all batches
    if local:
        llm_config = get_llm_config()
        client = get_openai_client(
            api_key=llm_config.get("local_api_key") or "ollama",
            base_url=llm_config.get("local_api_url") or "http://localhost:11434/v1",
        )
        model = llm_config.get("local_model") or llm_config.get("extraction_model") or "llama3.2"
    else:
        client = get_openai_client()
        model = None  # Use default
    
    try:
        for i, batch in enumerate(batches):
            try:
                # Build prompt with template
                system_prompt, user_prompt = build_generation_prompt(
                    template_name=template,
                    repo_name=repo_info.name,
                    commits=batch,
                    custom_prompt=custom_prompt,
                )
                
                # Extract story from batch
                content = await extract_commit_batch(
                    client=client,
                    commits=batch,
                    batch_num=i + 1,
                    total_batches=len(batches),
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                
                if not content or content.startswith("[Batch"):
                    continue
                
                # Extract summary (first non-empty line)
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                summary = lines[0][:100] if lines else "Story"
                # Clean up summary
                summary = summary.lstrip("#-•* ").strip()
                
                # Build metadata
                commit_shas = [c["full_sha"] for c in batch]
                first_date = min(c["date"] for c in batch)
                last_date = max(c["date"] for c in batch)
                total_files = sum(len(c.get("files", [])) for c in batch)
                total_adds = sum(c.get("insertions", 0) for c in batch)
                total_dels = sum(c.get("deletions", 0) for c in batch)
                
                metadata = {
                    "summary": summary,
                    "repo_name": repo_info.name,
                    "repo_path": str(repo_info.path),
                    "commit_shas": commit_shas,
                    "first_commit_at": first_date,
                    "last_commit_at": last_date,
                    "files_changed": total_files,
                    "lines_added": total_adds,
                    "lines_removed": total_dels,
                    "generated_locally": local,
                    "template": template,
                    "needs_review": False,
                }
                
                # Save story
                story_id = save_story(content, metadata)
                metadata["id"] = story_id
                stories.append(metadata)
                
            except Exception as e:
                console.print(f"  [{BRAND_MUTED}]Batch {i+1} failed: {e}[/]")
    finally:
        # Properly close the async client
        await client.close()
    
    return stories


def _generate_stories(
    commits: list[dict],
    repo_info,
    batch_size: int,
    local: bool,
    template: str = "resume",
    custom_prompt: str | None = None,
) -> list[dict]:
    """Generate stories from commits using LLM."""
    return asyncio.run(_generate_stories_async(
        commits=commits,
        repo_info=repo_info,
        batch_size=batch_size,
        local=local,
        template=template,
        custom_prompt=custom_prompt,
    ))


# =============================================================================
# STORIES MANAGEMENT
# =============================================================================

@app.command()
def stories(
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repository"),
    needs_review: bool = typer.Option(False, "--needs-review", help="Show only stories needing review"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List all stories.
    
    Example:
        repr stories
        repr stories --repo myproject
        repr stories --needs-review
    """
    story_list = list_stories(repo_name=repo, needs_review=needs_review)
    
    if json_output:
        print(json.dumps(story_list, indent=2, default=str))
        return
    
    if not story_list:
        print_info("No stories found.")
        print_info("Run `repr generate` to create stories from your commits.")
        raise typer.Exit()
    
    console.print(f"[bold]Stories[/] ({len(story_list)} total)")
    console.print()

    # Group stories by repository
    by_repo = defaultdict(list)
    for story in story_list[:20]:
        r_name = story.get("repo_name", "unknown")
        by_repo[r_name].append(story)
    
    # Sort repositories by their most recent story
    sorted_repos = sorted(
        by_repo.keys(),
        key=lambda r: max(s.get("created_at", "") for s in by_repo[r]),
        reverse=True
    )

    for repo_name in sorted_repos:
        console.print(f"[bold]{repo_name}[/]")
        for story in by_repo[repo_name]:
            # Status indicator
            if story.get("needs_review"):
                status = f"[{BRAND_WARNING}]⚠[/]"
            elif story.get("pushed_at"):
                status = f"[{BRAND_SUCCESS}]✓[/]"
            else:
                status = f"[{BRAND_MUTED}]○[/]"
            
            summary = story.get("summary", "Untitled")
            created = format_relative_time(story.get("created_at", ""))
            
            console.print(f"  {status} {summary} [{BRAND_MUTED}]• {created}[/]")
        console.print()

    if len(story_list) > 20:
        console.print(f"[{BRAND_MUTED}]... and {len(story_list) - 20} more[/]")


@app.command()
def story(
    action: str = typer.Argument(..., help="Action: view, edit, delete, hide, feature, regenerate"),
    story_id: str = typer.Argument(..., help="Story ID (ULID)"),
):
    """
    Manage a single story.
    
    Examples:
        repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV
        repr story delete 01ARYZ6S41TSV4RRFFQ69G5FAV
    """
    result = load_story(story_id)
    
    if not result:
        print_error(f"Story not found: {story_id}")
        raise typer.Exit(1)
    
    content, metadata = result
    
    if action == "view":
        print_markdown(content)
        console.print()
        console.print(f"[{BRAND_MUTED}]ID: {story_id}[/]")
        console.print(f"[{BRAND_MUTED}]Created: {metadata.get('created_at', 'unknown')}[/]")
    
    elif action == "edit":
        # Open in $EDITOR
        import subprocess
        
        editor = os.environ.get("EDITOR", "vim")
        md_path = STORIES_DIR / f"{story_id}.md"
        
        subprocess.run([editor, str(md_path)])
        print_success("Story updated")
    
    elif action == "delete":
        if confirm(f"Delete story '{metadata.get('summary', story_id)}'?"):
            delete_story(story_id)
            print_success("Story deleted")
        else:
            print_info("Cancelled")
    
    elif action == "hide":
        update_story_metadata(story_id, {"is_hidden": True})
        print_success("Story hidden from profile")
    
    elif action == "feature":
        update_story_metadata(story_id, {"is_featured": True})
        print_success("Story featured on profile")
    
    elif action == "regenerate":
        print_info("Regeneration not yet implemented")
        print_info("Use `repr generate --commits <sha>` with specific commits")
    
    else:
        print_error(f"Unknown action: {action}")
        print_info("Valid actions: view, edit, delete, hide, feature, regenerate")
        raise typer.Exit(1)


@app.command("review")
def stories_review():
    """
    Interactive review workflow for stories needing review.
    
    Example:
        repr review
    """
    from .storage import get_stories_needing_review
    
    needs_review = get_stories_needing_review()
    
    if not needs_review:
        print_success("No stories need review!")
        raise typer.Exit()
    
    console.print(f"[bold]{len(needs_review)} stories need review[/]")
    console.print()
    
    for i, story in enumerate(needs_review):
        console.print(f"[bold]Story {i+1} of {len(needs_review)}[/]")
        console.print()

        # Show story summary
        console.print(f"⚠ \"{story.get('summary', 'Untitled')}\"")
        console.print(f"  {story.get('repo_name', 'unknown')} • {len(story.get('commit_shas', []))} commits")
        console.print()

        # Load and show content preview
        result = load_story(story["id"])
        if result:
            content, metadata = result

            # Check if this is a STAR format story (interview template)
            template = metadata.get('template', '')
            if template == 'interview':
                # Display STAR format
                console.print("[bold]What was built:[/]")
                # Extract "what was built" section from content
                lines = content.split('\n')
                for line in lines[:10]:  # Show first 10 lines as preview
                    console.print(f"  {line}")

                console.print()
                console.print("[bold]Technologies:[/]")
                # Try to extract technologies from metadata or content
                techs = metadata.get('technologies', [])
                if techs:
                    console.print(f"  {', '.join(techs)}")
                else:
                    console.print("  (Not specified)")

                console.print()
                console.print("[bold]Confidence:[/] {0}".format(
                    metadata.get('confidence', 'Medium')
                ))
            else:
                # Show first 500 chars as preview
                preview = content[:500]
                if len(content) > 500:
                    preview += "..."
                console.print(preview)

        console.print()

        # Prompt for action (added regenerate option)
        action = Prompt.ask(
            "[a] Approve  [e] Edit  [r] Regenerate  [d] Delete  [s] Skip  [q] Quit",
            choices=["a", "e", "r", "d", "s", "q"],
            default="s",
        )
        
        if action == "a":
            update_story_metadata(story["id"], {"needs_review": False})
            print_success("Story approved")
        elif action == "e":
            editor = os.environ.get("EDITOR", "vim")
            md_path = STORIES_DIR / f"{story['id']}.md"
            import subprocess
            subprocess.run([editor, str(md_path)])
            update_story_metadata(story["id"], {"needs_review": False})
            print_success("Story updated and approved")
        elif action == "r":
            # Regenerate story with different template
            print_info("Regenerate action not yet implemented")
            print_info("This feature is planned for a future release")
            print_info("For now, you can delete and re-generate the story manually")
        elif action == "d":
            if confirm("Delete this story?"):
                delete_story(story["id"])
                print_success("Story deleted")
        elif action == "q":
            break
        
        console.print()


# =============================================================================
# CLOUD OPERATIONS
# =============================================================================

@app.command()
def push(
    story_id: Optional[str] = typer.Option(None, "--story", help="Push specific story"),
    all_stories: bool = typer.Option(False, "--all", help="Push all unpushed stories"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be pushed"),
):
    """
    Publish stories to repr.dev.
    
    Examples:
        repr push
        repr push --story 01ARYZ6S41TSV4RRFFQ69G5FAV
    """
    from .privacy import check_cloud_permission, log_cloud_operation
    
    allowed, reason = check_cloud_permission("push")
    if not allowed:
        print_error("Publishing blocked")
        print_info(reason)
        raise typer.Exit(1)
    
    # Get stories to push
    if story_id:
        result = load_story(story_id)
        if not result:
            print_error(f"Story not found: {story_id}")
            raise typer.Exit(1)
        content, metadata = result
        to_push = [{"id": story_id, "content": content, **metadata}]
    else:
        to_push = get_unpushed_stories()
    
    if not to_push:
        print_success("All stories already synced!")
        raise typer.Exit()
    
    console.print(f"Publishing {len(to_push)} story(ies) to repr.dev...")
    console.print()
    
    if dry_run:
        for s in to_push:
            console.print(f"  • {s.get('summary', s.get('id'))}")
        console.print()
        console.print("Run without --dry-run to publish")
        raise typer.Exit()
    
    # Actually push
    from .api import push_story as api_push_story
    
    pushed = 0
    for s in to_push:
        try:
            content, meta = load_story(s["id"])
            asyncio.run(api_push_story({**meta, "content": content}))
            mark_story_pushed(s["id"])
            console.print(f"  [{BRAND_SUCCESS}]✓[/] {s.get('summary', s.get('id'))[:50]}")
            pushed += 1
        except (APIError, AuthError) as e:
            console.print(f"  [{BRAND_ERROR}]✗[/] {s.get('summary', s.get('id'))[:50]}: {e}")
    
    # Log operation
    if pushed > 0:
        log_cloud_operation(
            operation="push",
            destination="repr.dev",
            payload_summary={"stories_pushed": pushed},
            bytes_sent=0,
        )
    
    console.print()
    print_success(f"Pushed {pushed}/{len(to_push)} stories")


@app.command()
def sync():
    """
    Sync stories across devices.
    
    Example:
        repr sync
    """
    from .privacy import check_cloud_permission
    
    allowed, reason = check_cloud_permission("sync")
    if not allowed:
        print_error("Sync blocked")
        print_info(reason)
        raise typer.Exit(1)
    
    console.print("Syncing with repr.dev...")
    console.print()
    
    unpushed = get_unpushed_stories()
    
    if unpushed:
        console.print(f"↑ {len(unpushed)} local stories to push")
        if confirm("Upload these stories?"):
            # Reuse push logic
            from .api import push_story as api_push_story
            for s in unpushed:
                try:
                    content, meta = load_story(s["id"])
                    asyncio.run(api_push_story({**meta, "content": content}))
                    mark_story_pushed(s["id"])
                except Exception:
                    pass
            print_success(f"Pushed {len(unpushed)} stories")
    else:
        console.print(f"[{BRAND_SUCCESS}]✓[/] All stories synced")


@app.command()
def pull():
    """
    Pull remote stories to local device.
    
    Example:
        repr pull
    """
    from .privacy import check_cloud_permission
    
    allowed, reason = check_cloud_permission("pull")
    if not allowed:
        print_error("Pull blocked")
        print_info(reason)
        raise typer.Exit(1)
    
    console.print("Pulling from repr.dev...")
    console.print()
    
    # TODO: Implement actual pull from API
    print_info("Pull from cloud not yet implemented")
    print_info("Local stories are preserved")


# =============================================================================
# COMMITS
# =============================================================================

@app.command("commits")
def list_commits(
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repo name"),
    limit: int = typer.Option(50, "--limit", "-n", help="Number of commits"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Show commits from last N days (e.g., 7 for week, 3 for standup)"),
    since: Optional[str] = typer.Option(None, "--since", help="Since date (e.g., '2024-01-01', 'monday', '2 weeks ago')"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List recent commits across all tracked repos.
    
    Examples:
        repr commits --limit 10
        repr commits --repo myproject
        repr commits --days 7           # Last week
        repr commits --days 3           # For standup
        repr commits --since monday
        repr commits --since "2 weeks ago"
    """
    from .tools import get_commits_with_diffs
    
    tracked = get_tracked_repos()
    if not tracked:
        print_warning("No repositories tracked.")
        raise typer.Exit(1)
    
    # Determine days filter
    filter_days = days if days is not None else 90
    
    # Parse natural language date if --since provided
    since_str = None
    if since:
        since_str = _parse_date_reference(since)
        if not since_str:
            print_error(f"Could not parse date: {since}")
            print_info("Try: '2024-01-01', 'monday', '3 days ago', 'last week'")
            raise typer.Exit(1)
    
    all_commits = []
    
    for repo_info in tracked:
        repo_path = Path(repo_info["path"])
        if repo and repo_path.name != repo:
            continue
        if not repo_path.exists():
            continue
        
        commits = get_commits_with_diffs(repo_path, count=limit, days=filter_days, since=since_str)
        for c in commits:
            c["repo_name"] = repo_path.name
        all_commits.extend(commits)
    
    # Sort by date
    all_commits.sort(key=lambda c: c.get("date", ""), reverse=True)
    all_commits = all_commits[:limit]
    
    if json_output:
        print(json.dumps(all_commits, indent=2, default=str))
        return
    
    if not all_commits:
        print_info("No commits found")
        raise typer.Exit()
    
    # Build label for display
    if days:
        label = f"last {days} days"
    elif since:
        label = f"since {since}"
    else:
        label = "recent"
    
    console.print(f"[bold]Commits ({label})[/] — {len(all_commits)} total")
    console.print()
    
    current_repo = None
    for c in all_commits:
        if c["repo_name"] != current_repo:
            current_repo = c["repo_name"]
            console.print(f"[bold]{current_repo}:[/]")
        
        sha = c.get("sha", "")[:7]
        msg = c.get("message", "").split("\n")[0][:50]
        date = format_relative_time(c.get("date", ""))
        console.print(f"  {sha}  {msg}  [{BRAND_MUTED}]{date}[/]")
    
    console.print()
    print_info("Generate stories: repr generate --commits <sha1>,<sha2>")


# =============================================================================
# AUTHENTICATION
# =============================================================================

@app.command()
def login():
    """
    Authenticate with repr.dev.
    
    Example:
        repr login
    """
    print_header()
    
    if is_authenticated():
        user = get_current_user()
        email = user.get("email", "unknown") if user else "unknown"
        print_info(f"Already authenticated as {email}")
        
        if not confirm("Re-authenticate?"):
            raise typer.Exit()
    
    console.print("[bold]Authenticate with repr[/]")
    console.print()
    
    async def run_auth():
        flow = AuthFlow()
        
        def on_code_received(device_code):
            console.print("To sign in, visit:")
            console.print()
            console.print(f"  [bold {BRAND_PRIMARY}]{device_code.verification_url}[/]")
            console.print()
            console.print("And enter this code:")
            print_auth_code(device_code.user_code)
        
        def on_progress(remaining):
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            console.print(f"\rWaiting for authorization... {mins}:{secs:02d}  ", end="")
        
        def on_success(token):
            console.print()
            console.print()
            print_success(f"Authenticated as {token.email}")
        
        def on_error(error):
            console.print()
            print_error(str(error))
        
        flow.on_code_received = on_code_received
        flow.on_progress = on_progress
        flow.on_success = on_success
        flow.on_error = on_error
        
        try:
            await flow.run()
        except AuthError:
            raise typer.Exit(1)
    
    asyncio.run(run_auth())
    
    # Check for local stories
    local_count = get_story_count()
    if local_count > 0:
        console.print()
        console.print(f"You have {local_count} local stories.")
        console.print("Run `repr sync` to upload them.")


@app.command()
def logout():
    """
    Sign out and clear credentials.
    
    Example:
        repr logout
    """
    if not is_authenticated():
        print_info("Not currently authenticated.")
        raise typer.Exit()
    
    auth_logout()
    
    print_success("Signed out")
    console.print()
    console.print(f"  Local stories preserved in {STORIES_DIR}")


@app.command()
def whoami(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show current user.
    
    Example:
        repr whoami
    """
    if not is_authenticated():
        if json_output:
            print(json.dumps({"error": "Not authenticated"}))
        else:
            print_info("Not signed in")
            print_info("Run `repr login` to sign in")
        raise typer.Exit(1)
    
    user = get_current_user()
    
    if json_output:
        print(json.dumps(user, indent=2))
        return
    
    email = user.get("email", "unknown")
    console.print(f"Signed in as: [bold]{email}[/]")


# =============================================================================
# REPOSITORY MANAGEMENT
# =============================================================================

@app.command()
def repos(
    action: str = typer.Argument("list", help="Action: list, add, remove, pause, resume"),
    path: Optional[Path] = typer.Argument(None, help="Repository path (for add/remove/pause/resume)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Manage tracked repositories.
    
    Examples:
        repr repos
        repr repos add ~/code/myproject
        repr repos remove ~/code/old-project
        repr repos pause ~/code/work-project
    """
    if action == "list":
        tracked = get_tracked_repos()
        
        if json_output:
            print(json.dumps(tracked, indent=2))
            return
        
        if not tracked:
            print_info("No repositories tracked.")
            print_info("Run `repr repos add <path>` to track a repository.")
            raise typer.Exit()
        
        console.print(f"[bold]Tracked Repositories[/] ({len(tracked)})")
        console.print()
        
        for repo in tracked:
            repo_path = Path(repo["path"])
            exists = repo_path.exists()
            paused = repo.get("paused", False)
            hook = repo.get("hook_installed", False)
            
            if not exists:
                status = f"[{BRAND_ERROR}]✗[/]"
            elif paused:
                status = f"[{BRAND_WARNING}]○[/]"
            else:
                status = f"[{BRAND_SUCCESS}]✓[/]"
            
            console.print(f"  {status} {repo_path.name}")
            details = []
            if hook:
                details.append("hook: on")
            if paused:
                details.append("paused")
            if not exists:
                details.append("missing")
            
            info_str = " • ".join(details) if details else repo["path"]
            console.print(f"    [{BRAND_MUTED}]{info_str}[/]")
    
    elif action == "add":
        if not path:
            print_error("Path required: repr repos add <path>")
            raise typer.Exit(1)
        
        if not (path / ".git").exists():
            print_error(f"Not a git repository: {path}")
            raise typer.Exit(1)
        
        add_tracked_repo(str(path))
        print_success(f"Added: {path.name}")
    
    elif action == "remove":
        if not path:
            print_error("Path required: repr repos remove <path>")
            raise typer.Exit(1)
        
        if remove_tracked_repo(str(path)):
            print_success(f"Removed: {path.name}")
        else:
            print_warning(f"Not tracked: {path.name}")
    
    elif action == "pause":
        if not path:
            print_error("Path required: repr repos pause <path>")
            raise typer.Exit(1)
        
        set_repo_paused(str(path), True)
        print_success(f"Paused auto-tracking for: {path.name}")
    
    elif action == "resume":
        if not path:
            print_error("Path required: repr repos resume <path>")
            raise typer.Exit(1)
        
        set_repo_paused(str(path), False)
        print_success(f"Resumed auto-tracking for: {path.name}")
    
    else:
        print_error(f"Unknown action: {action}")
        print_info("Valid actions: list, add, remove, pause, resume")


# =============================================================================
# HOOKS MANAGEMENT
# =============================================================================

@hooks_app.command("install")
def hooks_install(
    all_repos: bool = typer.Option(False, "--all", help="Install in all tracked repos"),
    repo: Optional[Path] = typer.Option(None, "--repo", help="Install in specific repo"),
):
    """
    Install git post-commit hooks for auto-tracking.
    
    Example:
        repr hooks install --all
        repr hooks install --repo ~/code/myproject
    """
    from .hooks import install_hook
    
    if repo:
        repos_to_install = [{"path": str(repo)}]
    elif all_repos:
        repos_to_install = get_tracked_repos()
    else:
        print_error("Specify --all or --repo <path>")
        raise typer.Exit(1)
    
    if not repos_to_install:
        print_warning("No repositories to install hooks in")
        raise typer.Exit(1)
    
    console.print(f"Installing hooks in {len(repos_to_install)} repositories...")
    console.print()
    
    installed = 0
    already = 0
    
    for repo_info in repos_to_install:
        repo_path = Path(repo_info["path"])
        result = install_hook(repo_path)
        
        if result["success"]:
            if result["already_installed"]:
                console.print(f"  [{BRAND_MUTED}]○[/] {repo_path.name}: already installed")
                already += 1
            else:
                console.print(f"  [{BRAND_SUCCESS}]✓[/] {repo_path.name}: hook installed")
                set_repo_hook_status(str(repo_path), True)
                installed += 1
        else:
            console.print(f"  [{BRAND_ERROR}]✗[/] {repo_path.name}: {result['message']}")
    
    console.print()
    print_success(f"Hooks installed: {installed}, Already installed: {already}")
    console.print()
    console.print(f"[{BRAND_MUTED}]Hooks queue commits locally. Run `repr generate` to create stories.[/]")


@hooks_app.command("remove")
def hooks_remove(
    all_repos: bool = typer.Option(False, "--all", help="Remove from all tracked repos"),
    repo: Optional[Path] = typer.Option(None, "--repo", help="Remove from specific repo"),
):
    """
    Remove git post-commit hooks.
    
    Example:
        repr hooks remove --all
    """
    from .hooks import remove_hook
    
    if repo:
        repos_to_remove = [{"path": str(repo)}]
    elif all_repos:
        repos_to_remove = get_tracked_repos()
    else:
        print_error("Specify --all or --repo <path>")
        raise typer.Exit(1)
    
    removed = 0
    for repo_info in repos_to_remove:
        repo_path = Path(repo_info["path"])
        result = remove_hook(repo_path)
        
        if result["success"]:
            console.print(f"  [{BRAND_SUCCESS}]✓[/] {repo_path.name}: {result['message']}")
            set_repo_hook_status(str(repo_path), False)
            removed += 1
        else:
            console.print(f"  [{BRAND_MUTED}]○[/] {repo_path.name}: {result['message']}")
    
    print_success(f"Hooks removed: {removed}")


@hooks_app.command("status")
def hooks_status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show hook status for all tracked repos.
    
    Example:
        repr hooks status
    """
    from .hooks import get_hook_status, get_queue_stats
    
    tracked = get_tracked_repos()
    
    if not tracked:
        print_warning("No repositories tracked")
        raise typer.Exit()
    
    results = []
    for repo_info in tracked:
        repo_path = Path(repo_info["path"])
        if not repo_path.exists():
            continue
        
        status = get_hook_status(repo_path)
        queue = get_queue_stats(repo_path)
        
        results.append({
            "name": repo_path.name,
            "path": str(repo_path),
            "installed": status["installed"],
            "executable": status["executable"],
            "queue_count": queue["count"],
        })
    
    if json_output:
        print(json.dumps(results, indent=2))
        return
    
    console.print("[bold]Hook Status[/]")
    console.print()
    
    for r in results:
        if r["installed"]:
            status = f"[{BRAND_SUCCESS}]✓[/]"
            msg = "Hook installed and active"
        else:
            status = f"[{BRAND_MUTED}]○[/]"
            msg = "No hook installed"
        
        console.print(f"{status} {r['name']}")
        console.print(f"  [{BRAND_MUTED}]{msg}[/]")
        if r["queue_count"] > 0:
            console.print(f"  [{BRAND_MUTED}]Queue: {r['queue_count']} commits[/]")
        console.print()


@hooks_app.command("queue")
def hooks_queue(
    commit_sha: str = typer.Argument(..., help="Commit SHA to queue"),
    repo: Path = typer.Option(..., "--repo", help="Repository path"),
):
    """
    Queue a commit (called by git hook).
    
    This is an internal command used by the git post-commit hook.
    """
    from .hooks import queue_commit
    
    success = queue_commit(repo, commit_sha)
    if not success:
        # Silent failure - don't block git commit
        pass


# =============================================================================
# LLM CONFIGURATION
# =============================================================================

@llm_app.command("add")
def llm_add(
    provider: str = typer.Argument(..., help="Provider: openai, anthropic, groq, together"),
):
    """
    Configure a BYOK provider.
    
    Example:
        repr llm add openai
    """
    if provider not in BYOK_PROVIDERS:
        print_error(f"Unknown provider: {provider}")
        print_info(f"Available: {', '.join(BYOK_PROVIDERS.keys())}")
        raise typer.Exit(1)
    
    provider_info = BYOK_PROVIDERS[provider]
    console.print(f"Configure {provider_info['name']}")
    console.print()
    
    api_key = Prompt.ask("API Key", password=True)
    if not api_key:
        print_error("API key required")
        raise typer.Exit(1)
    
    # Test the key
    console.print("Testing connection...")
    from .llm import test_byok_provider
    result = test_byok_provider(provider, api_key)
    
    if result.success:
        add_byok_provider(provider, api_key)
        print_success(f"Added {provider_info['name']}")
        console.print(f"  Response time: {result.response_time_ms:.0f}ms")
    else:
        print_error(f"Connection failed: {result.error}")
        if confirm("Save anyway?"):
            add_byok_provider(provider, api_key)
            print_success(f"Added {provider_info['name']}")


@llm_app.command("remove")
def llm_remove(
    provider: str = typer.Argument(..., help="Provider to remove"),
):
    """
    Remove a BYOK provider key.
    
    Example:
        repr llm remove openai
    """
    if remove_byok_provider(provider):
        print_success(f"Removed {provider}")
    else:
        print_warning(f"Provider not configured: {provider}")


@llm_app.command("use")
def llm_use(
    mode: str = typer.Argument(..., help="Mode: local, cloud, byok:<provider>"),
):
    """
    Set default LLM mode.
    
    Examples:
        repr llm use local
        repr llm use cloud
        repr llm use byok:openai
    """
    valid_modes = ["local", "cloud"]
    byok_providers = list_byok_providers()
    valid_modes.extend([f"byok:{p}" for p in byok_providers])
    
    if mode not in valid_modes and not mode.startswith("byok:"):
        print_error(f"Invalid mode: {mode}")
        print_info(f"Valid modes: {', '.join(valid_modes)}")
        raise typer.Exit(1)
    
    if mode == "cloud" and not is_authenticated():
        print_warning("Cloud mode requires sign-in")
        print_info("When not signed in, local mode will be used instead")
    
    if mode.startswith("byok:"):
        provider = mode.split(":", 1)[1]
        if provider not in byok_providers:
            print_error(f"BYOK provider not configured: {provider}")
            print_info(f"Run `repr llm add {provider}` first")
            raise typer.Exit(1)
    
    set_llm_config(default=mode)
    print_success(f"Default LLM mode: {mode}")


@llm_app.command("configure")
def llm_configure():
    """
    Configure local LLM endpoint interactively.
    
    Example:
        repr llm configure
    """
    from .llm import detect_all_local_llms, list_ollama_models
    
    console.print("[bold]Configure Local LLM[/]")
    console.print()
    
    # Detect available LLMs
    detected = detect_all_local_llms()
    
    if detected:
        console.print("Detected local LLMs:")
        for i, llm in enumerate(detected, 1):
            console.print(f"  {i}. {llm.name} ({llm.url})")
        console.print(f"  {len(detected) + 1}. Custom endpoint")
        console.print()
        
        choice = Prompt.ask(
            "Select",
            choices=[str(i) for i in range(1, len(detected) + 2)],
            default="1",
        )
        
        if int(choice) <= len(detected):
            selected = detected[int(choice) - 1]
            url = selected.url
            models = selected.models
        else:
            url = Prompt.ask("Custom endpoint URL")
            models = []
    else:
        console.print(f"[{BRAND_MUTED}]No local LLMs detected[/]")
        url = Prompt.ask("Endpoint URL", default="http://localhost:11434")
        models = []
    
    # Select model
    if models:
        console.print()
        console.print("Available models:")
        for i, model in enumerate(models[:10], 1):
            console.print(f"  {i}. {model}")
        console.print()
        
        model_choice = Prompt.ask("Select model", default="1")
        try:
            model = models[int(model_choice) - 1]
        except (ValueError, IndexError):
            model = model_choice  # Use as literal model name
    else:
        model = Prompt.ask("Model name", default="llama3.2")
    
    # Save config
    set_llm_config(
        local_api_url=f"{url}/v1",
        local_model=model,
    )
    
    print_success(f"Configured local LLM")
    console.print(f"  Endpoint: {url}")
    console.print(f"  Model: {model}")


@llm_app.command("test")
def llm_test():
    """
    Test LLM connection and generation.
    
    Example:
        repr llm test
    """
    from .llm import test_local_llm, get_llm_status
    
    console.print("Testing LLM connection...")
    console.print()
    
    status = get_llm_status()
    
    # Test local
    console.print("[bold]Local LLM:[/]")
    if status["local"]["available"]:
        result = test_local_llm(
            url=status["local"]["url"],
            model=status["local"]["model"],
        )
        
        if result.success:
            console.print(f"  [{BRAND_SUCCESS}]✓[/] Connection successful")
            console.print(f"  Provider: {result.provider}")
            console.print(f"  Model: {result.model}")
            console.print(f"  Response time: {result.response_time_ms:.0f}ms")
        else:
            console.print(f"  [{BRAND_ERROR}]✗[/] {result.error}")
    else:
        console.print(f"  [{BRAND_MUTED}]Not detected[/]")
    
    console.print()
    
    # Show cloud status
    console.print("[bold]Cloud LLM:[/]")
    if status["cloud"]["available"]:
        console.print(f"  [{BRAND_SUCCESS}]✓[/] Available")
        console.print(f"  Model: {status['cloud']['model']}")
    else:
        console.print(f"  [{BRAND_MUTED}]✗[/] {status['cloud']['blocked_reason']}")
    
    # Show BYOK status
    if status["byok"]["providers"]:
        console.print()
        console.print("[bold]BYOK Providers:[/]")
        for provider in status["byok"]["providers"]:
            console.print(f"  [{BRAND_SUCCESS}]✓[/] {provider}")


# =============================================================================
# PRIVACY
# =============================================================================

@privacy_app.command("telemetry")
def privacy_telemetry(
    action: str = typer.Argument("status", help="Action: status, enable, disable"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Manage anonymous telemetry.
    
    Telemetry is disabled by default. When enabled, it sends:
    - Command names and timestamps
    - OS type and CLI version
    - Anonymous device ID (random, not linked to you)
    
    It NEVER sends: code, commits, paths, usernames, emails.
    
    Examples:
        repr privacy telemetry              Show telemetry status
        repr privacy telemetry enable       Opt-in to telemetry
        repr privacy telemetry disable      Opt-out of telemetry
    """
    from .telemetry import (
        is_telemetry_enabled,
        enable_telemetry,
        disable_telemetry,
        get_queue_stats,
        get_pending_events,
    )
    
    if action == "status":
        stats = get_queue_stats()
        
        if json_output:
            print(json.dumps(stats, indent=2))
            return
        
        status = f"[{BRAND_SUCCESS}]enabled[/]" if stats["enabled"] else f"[{BRAND_MUTED}]disabled[/]"
        console.print(f"[bold]Telemetry[/]: {status}")
        console.print()
        
        if stats["enabled"]:
            console.print(f"Device ID: {stats['device_id']}")
            console.print(f"Pending events: {stats['pending_events']}")
            console.print()
            
            # Show pending events for transparency
            pending = get_pending_events()
            if pending:
                console.print("[bold]Pending events:[/]")
                for event in pending[-5:]:
                    console.print(f"  • {event.get('event', '')} ({event.get('timestamp', '')[:10]})")
                if len(pending) > 5:
                    console.print(f"  [{BRAND_MUTED}]... and {len(pending) - 5} more[/]")
        else:
            console.print("Enable with: repr privacy telemetry enable")
        
        console.print()
        console.print(f"[{BRAND_MUTED}]Telemetry helps improve repr. No PII is ever sent.[/]")
    
    elif action == "enable":
        enable_telemetry()
        print_success("Telemetry enabled")
        console.print()
        console.print("What we collect:")
        console.print("  ✓ Command names and timestamps")
        console.print("  ✓ OS type and CLI version")
        console.print("  ✓ Anonymous device ID")
        console.print()
        console.print("What we NEVER collect:")
        console.print("  ✗ Code, commits, diffs")
        console.print("  ✗ Paths, filenames")
        console.print("  ✗ Usernames, emails, PII")
        console.print()
        console.print(f"[{BRAND_MUTED}]Disable anytime: repr privacy telemetry disable[/]")
    
    elif action == "disable":
        disable_telemetry()
        print_success("Telemetry disabled")
        console.print("No data will be collected.")
    
    else:
        print_error(f"Unknown action: {action}")
        print_info("Valid actions: status, enable, disable")


@privacy_app.command("explain")
def privacy_explain():
    """
    One-screen summary of privacy guarantees.
    
    Example:
        repr privacy explain
    """
    from .privacy import get_privacy_explanation
    
    explanation = get_privacy_explanation()
    
    console.print("[bold]repr Privacy Guarantees[/]")
    console.print("━" * 50)
    console.print()
    
    console.print("[bold]ARCHITECTURE:[/]")
    console.print(f"  ✓ {explanation['architecture']['guarantee']}")
    console.print("  ✓ No background daemons or silent uploads")
    console.print("  ✓ All network calls are foreground, user-initiated")
    console.print("  ✓ No telemetry by default (opt-in only)")
    console.print()
    
    console.print("[bold]CURRENT SETTINGS:[/]")
    state = explanation["current_state"]
    console.print(f"  Auth: {'signed in' if state['authenticated'] else 'not signed in'}")
    console.print(f"  Mode: {state['mode']}")
    console.print(f"  Privacy lock: {'enabled' if state['privacy_lock'] else 'disabled'}")
    console.print(f"  Telemetry: {'enabled' if state['telemetry_enabled'] else 'disabled'}")
    console.print()
    
    console.print("[bold]LOCAL MODE NETWORK POLICY:[/]")
    console.print("  Allowed: 127.0.0.1, localhost, ::1 (loopback only)")
    console.print("  Blocked: All external network, DNS, HTTP(S) to internet")
    console.print()
    
    console.print("[bold]CLOUD MODE SETTINGS:[/]")
    cloud = explanation["cloud_mode_settings"]
    console.print(f"  Path redaction: {'enabled' if cloud['path_redaction_enabled'] else 'disabled'}")
    console.print(f"  Diffs: {'disabled' if cloud['diffs_disabled'] else 'enabled'}")
    console.print(f"  Email redaction: {'enabled' if cloud['email_redaction_enabled'] else 'disabled'}")
    console.print()
    
    console.print(f"[{BRAND_MUTED}]Run `repr privacy audit` to see all data sent[/]")
    console.print(f"[{BRAND_MUTED}]Run `repr privacy lock-local` to disable cloud permanently[/]")


@privacy_app.command("audit")
def privacy_audit(
    days: int = typer.Option(30, "--days", help="Number of days to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show what data was sent to cloud.
    
    Example:
        repr privacy audit
    """
    from .privacy import get_audit_summary, get_data_sent_history
    
    summary = get_audit_summary(days=days)
    
    if json_output:
        print(json.dumps(summary, indent=2, default=str))
        return
    
    console.print("[bold]Privacy Audit[/]")
    console.print()
    console.print(f"Last {days} days:")
    console.print()
    
    if summary["total_operations"] == 0:
        if is_authenticated():
            console.print(f"  [{BRAND_MUTED}]No data sent to cloud[/]")
        else:
            console.print(f"  [{BRAND_MUTED}]None (not signed in)[/]")
        console.print()
        console.print("No data has been sent to repr.dev.")
        return
    
    for op_name, op_data in summary["by_operation"].items():
        console.print(f"[bold]{op_name}[/] ({op_data['count']} times):")
        for entry in op_data["recent"]:
            payload = entry.get("payload_summary", {})
            console.print(f"  • {entry.get('timestamp', '')[:10]}: {payload}")
        console.print()
    
    console.print(f"Total data sent: ~{format_bytes(summary['total_bytes_sent'])}")
    console.print(f"Destinations: {', '.join(summary['destinations'])}")


@privacy_app.command("lock-local")
def privacy_lock_local(
    permanent: bool = typer.Option(False, "--permanent", help="Make lock irreversible"),
):
    """
    Disable cloud features (even after login).
    
    Example:
        repr privacy lock-local
        repr privacy lock-local --permanent
    """
    if permanent:
        console.print(f"[{BRAND_WARNING}]⚠ This will PERMANENTLY disable cloud features.[/]")
        console.print("  You will not be able to unlock cloud mode.")
        console.print("  Local-only mode will be enforced forever.")
        console.print()
        
        if not confirm("Continue?"):
            print_info("Cancelled")
            raise typer.Exit()
    
    lock_local_only(permanent=permanent)
    
    if permanent:
        print_success("Local-only mode PERMANENTLY enabled")
    else:
        print_success("Local-only mode enabled")
        console.print(f"  [{BRAND_MUTED}]To unlock: repr privacy unlock-local[/]")


@privacy_app.command("unlock-local")
def privacy_unlock_local():
    """
    Unlock from local-only mode.
    
    Example:
        repr privacy unlock-local
    """
    if unlock_local_only():
        print_success("Local-only mode disabled")
        print_info("Cloud features are now available")
    else:
        print_error("Cannot unlock: local-only mode is permanently locked")


# =============================================================================
# CONFIG
# =============================================================================

@config_app.command("show")
def config_show(
    key: Optional[str] = typer.Argument(None, help="Specific key (dot notation)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Display configuration.
    
    Examples:
        repr config show
        repr config show llm.default
    """
    if key:
        value = get_config_value(key)
        if json_output:
            print(json.dumps(value, indent=2, default=str))
        else:
            console.print(f"{key} = {value}")
    else:
        config = load_config()
        # Remove sensitive data
        if config.get("auth"):
            config["auth"] = {"signed_in": True, "email": config["auth"].get("email")}
        
        if json_output:
            print(json.dumps(config, indent=2, default=str))
        else:
            console.print("[bold]Configuration[/]")
            console.print()
            console.print(json.dumps(config, indent=2, default=str))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Key (dot notation)"),
    value: str = typer.Argument(..., help="Value"),
):
    """
    Set a configuration value.
    
    Examples:
        repr config set llm.default local
        repr config set generation.batch_size 10
    """
    # Parse value type
    if value.lower() == "true":
        parsed_value = True
    elif value.lower() == "false":
        parsed_value = False
    elif value.isdigit():
        parsed_value = int(value)
    else:
        try:
            parsed_value = float(value)
        except ValueError:
            parsed_value = value
    
    set_config_value(key, parsed_value)
    print_success(f"Set {key} = {parsed_value}")


@config_app.command("edit")
def config_edit():
    """
    Open config file in $EDITOR.
    
    Example:
        repr config edit
    """
    import subprocess
    
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(CONFIG_FILE)])
    print_success("Config file updated")


# =============================================================================
# DATA
# =============================================================================

@data_app.callback(invoke_without_command=True)
def data_default(ctx: typer.Context):
    """Show local data storage info."""
    if ctx.invoked_subcommand is None:
        stats = get_storage_stats()
        
        console.print("[bold]Local Data[/]")
        console.print()
        console.print(f"Stories: {stats['stories']['count']} files ({format_bytes(stats['stories']['size_bytes'])})")
        console.print(f"Profiles: {stats['profiles']['count']} files ({format_bytes(stats['profiles']['size_bytes'])})")
        console.print(f"Cache: {format_bytes(stats['cache']['size_bytes'])}")
        console.print(f"Config: {format_bytes(stats['config']['size_bytes'])}")
        console.print()
        console.print(f"Total: {format_bytes(stats['total_size_bytes'])}")
        console.print()
        console.print(f"[{BRAND_MUTED}]Location: {stats['stories']['path']}[/]")


@data_app.command("backup")
def data_backup(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
):
    """
    Backup all local data to JSON.
    
    Example:
        repr data backup > backup.json
        repr data backup --output backup.json
    """
    backup_data = backup_all_data()
    json_str = json.dumps(backup_data, indent=2, default=str)
    
    if output:
        output.write_text(json_str)
        print_success(f"Backup saved to {output}")
        console.print(f"  Stories: {len(backup_data['stories'])}")
        console.print(f"  Profiles: {len(backup_data['profiles'])}")
    else:
        print(json_str)


@data_app.command("restore")
def data_restore(
    input_file: Path = typer.Argument(..., help="Backup file to restore"),
    merge: bool = typer.Option(True, "--merge/--replace", help="Merge with existing data"),
):
    """
    Restore from backup.
    
    Example:
        repr data restore backup.json
    """
    if not input_file.exists():
        print_error(f"File not found: {input_file}")
        raise typer.Exit(1)
    
    try:
        backup_data = json.loads(input_file.read_text())
    except json.JSONDecodeError:
        print_error("Invalid JSON file")
        raise typer.Exit(1)
    
    console.print("This will restore:")
    console.print(f"  • {len(backup_data.get('stories', []))} stories")
    console.print(f"  • {len(backup_data.get('profiles', []))} profiles")
    console.print(f"  • Configuration settings")
    console.print()
    console.print(f"Mode: {'merge' if merge else 'replace'}")
    
    if not confirm("Continue?"):
        print_info("Cancelled")
        raise typer.Exit()
    
    result = restore_from_backup(backup_data, merge=merge)
    
    print_success("Restore complete")
    console.print(f"  Stories: {result['stories']}")
    console.print(f"  Profiles: {result['profiles']}")


@data_app.command("clear-cache")
def data_clear_cache():
    """
    Clear local cache.
    
    Example:
        repr data clear-cache
    """
    from .config import clear_cache, get_cache_size
    
    size = get_cache_size()
    clear_cache()
    print_success(f"Cache cleared ({format_bytes(size)} freed)")
    console.print("  Stories preserved")
    console.print("  Config preserved")


# =============================================================================
# PROFILE
# =============================================================================

@profile_app.callback(invoke_without_command=True)
def profile_default(ctx: typer.Context):
    """View profile in terminal."""
    if ctx.invoked_subcommand is None:
        profile_config = get_profile_config()
        story_list = list_stories(limit=5)
        
        console.print("[bold]Profile[/]")
        console.print()
        
        username = profile_config.get("username") or "Not set"
        console.print(f"Username: {username}")
        
        if profile_config.get("bio"):
            console.print(f"Bio: {profile_config['bio']}")
        if profile_config.get("location"):
            console.print(f"Location: {profile_config['location']}")
        
        console.print()
        console.print(f"[bold]Recent Stories ({len(story_list)}):[/]")
        for s in story_list:
            console.print(f"  • {s.get('summary', 'Untitled')[:60]}")
        
        if is_authenticated():
            console.print()
            # TODO: Get profile URL from API
            console.print(f"[{BRAND_MUTED}]Profile URL: https://repr.dev/@{username}[/]")


@profile_app.command("update")
def profile_update(
    preview: bool = typer.Option(False, "--preview", help="Show changes before publishing"),
    local_only: bool = typer.Option(False, "--local", help="Update locally only"),
):
    """
    Generate/update profile from stories.
    
    Example:
        repr profile update --preview
    """
    story_list = list_stories()
    
    if not story_list:
        print_warning("No stories to build profile from")
        print_info("Run `repr generate` first")
        raise typer.Exit(1)
    
    console.print(f"Building profile from {len(story_list)} stories...")
    
    # TODO: Implement actual profile generation
    print_info("Profile generation not yet fully implemented")
    print_info("Stories are available for manual profile creation")


@profile_app.command("set-bio")
def profile_set_bio(
    bio: str = typer.Argument(..., help="Bio text"),
):
    """Set profile bio."""
    set_profile_config(bio=bio)
    print_success("Bio updated")


@profile_app.command("set-location")
def profile_set_location(
    location: str = typer.Argument(..., help="Location"),
):
    """Set profile location."""
    set_profile_config(location=location)
    print_success("Location updated")


@profile_app.command("set-available")
def profile_set_available(
    available: bool = typer.Argument(..., help="Available for work (true/false)"),
):
    """Set availability status."""
    set_profile_config(available=available)
    print_success(f"Availability: {'available' if available else 'not available'}")


@profile_app.command("export")
def profile_export(
    format: str = typer.Option("md", "--format", "-f", help="Format: md, html, json, pdf"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    since: Optional[str] = typer.Option(None, "--since", help="Export only recent work (date filter)"),
):
    """
    Export profile to different formats.

    Example:
        repr profile export --format md > profile.md
        repr profile export --format json --output profile.json
        repr profile export --format html --output profile.html
    """
    story_list = list_stories()

    # Apply date filter if specified
    if since and isinstance(since, str):
        from datetime import datetime
        try:
            # Parse the date (support ISO format)
            since_date = datetime.fromisoformat(since)
            story_list = [
                s for s in story_list
                if s.get('created_at') and datetime.fromisoformat(s['created_at'][:10]) >= since_date
            ]
        except ValueError:
            print_error(f"Invalid date format: {since}")
            print_info("Use ISO format: YYYY-MM-DD")
            raise typer.Exit(1)

    profile_config = get_profile_config()

    if format == "json":
        data = {
            "profile": profile_config,
            "stories": story_list,
        }
        content = json.dumps(data, indent=2, default=str)
    elif format == "md":
        # Generate markdown
        lines = [f"# {profile_config.get('username', 'Developer Profile')}", ""]
        if profile_config.get("bio"):
            lines.extend([profile_config["bio"], ""])
        lines.extend(["## Stories", ""])
        for s in story_list:
            lines.append(f"### {s.get('summary', 'Untitled')}")
            lines.append(f"*{s.get('repo_name', 'unknown')} • {s.get('created_at', '')[:10]}*")
            lines.append("")
        content = "\n".join(lines)
    elif format == "html":
        # HTML export not yet implemented
        print_error("HTML export not yet implemented")
        print_info("Supported formats: md, json")
        print_info("HTML export is planned for a future release")
        raise typer.Exit(1)
    elif format == "pdf":
        # PDF export not yet implemented
        print_error("PDF export not yet implemented")
        print_info("Supported formats: md, json")
        print_info("PDF export is planned for a future release")
        raise typer.Exit(1)
    else:
        print_error(f"Unsupported format: {format}")
        print_info("Supported formats: md, json")
        raise typer.Exit(1)

    if output:
        output.write_text(content)
        print_success(f"Exported to {output}")
    else:
        print(content)


@profile_app.command("link")
def profile_link():
    """
    Get shareable profile link.
    
    Example:
        repr profile link
    """
    if not is_authenticated():
        print_error("Profile link requires sign-in")
        print_info("Run `repr login` first")
        raise typer.Exit(1)
    
    profile_config = get_profile_config()
    username = profile_config.get("username")
    
    if username:
        console.print(f"Your profile: https://repr.dev/@{username}")
    else:
        print_info("Username not set")
        print_info("Run `repr profile set-username <name>`")


# =============================================================================
# STATUS & INFO
# =============================================================================

@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show repr status and health.
    
    Example:
        repr status
    """
    authenticated = is_authenticated()
    user = get_current_user() if authenticated else None
    tracked = get_tracked_repos()
    story_count = get_story_count()
    unpushed = len(get_unpushed_stories())
    
    if json_output:
        print(json.dumps({
            "version": __version__,
            "authenticated": authenticated,
            "email": user.get("email") if user else None,
            "repos_tracked": len(tracked),
            "stories_total": story_count,
            "stories_unpushed": unpushed,
        }, indent=2))
        return
    
    print_header()
    
    # Auth status
    if authenticated:
        email = user.get("email", "unknown")
        console.print(f"Auth: [{BRAND_SUCCESS}]✓ Signed in as {email}[/]")
    else:
        console.print(f"Auth: [{BRAND_MUTED}]○ Not signed in[/]")
    
    console.print()
    
    # Stats
    console.print(f"Tracked repos: {len(tracked)}")
    console.print(f"Stories: {story_count} ({unpushed} unpushed)")
    
    console.print()
    
    # Next steps
    if not authenticated:
        print_info("Run `repr login` to enable cloud sync")
    elif unpushed > 0:
        print_info(f"Run `repr push` to publish {unpushed} stories")


@app.command()
def mode(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show current execution mode and settings.

    Example:
        repr mode
        repr mode --json
    """
    from .llm import get_llm_status

    authenticated = is_authenticated()
    privacy = get_privacy_settings()
    llm_status = get_llm_status()

    # Determine mode
    if privacy.get("lock_local_only"):
        if privacy.get("lock_permanent"):
            mode = "LOCAL-ONLY"
            locked = True
        else:
            mode = "LOCAL-ONLY"
            locked = True
    elif authenticated:
        mode = "CLOUD"
        locked = False
    else:
        mode = "LOCAL-ONLY"
        locked = False

    # Build LLM provider string
    if llm_status["local"]["available"]:
        llm_provider = f"{llm_status['local']['name']} ({llm_status['local']['model']})"
    else:
        llm_provider = "none"

    # Check cloud allowed
    cloud_allowed = authenticated and is_cloud_allowed()

    if json_output:
        import json
        output = {
            "mode": mode,
            "locked": locked,
            "llm_provider": llm_provider,
            "network_policy": "cloud-enabled" if authenticated else "local-only",
            "authenticated": authenticated,
            "cloud_generation_available": cloud_allowed,
            "sync_available": cloud_allowed,
            "publishing_available": cloud_allowed,
        }
        print(json.dumps(output, indent=2))
        return

    console.print("[bold]Mode[/]")
    console.print()

    if privacy.get("lock_local_only"):
        if privacy.get("lock_permanent"):
            console.print("Data boundary: local only (permanently locked)")
        else:
            console.print("Data boundary: local only (locked)")
    elif authenticated:
        console.print("Data boundary: cloud-enabled")
    else:
        console.print("Data boundary: local only")

    console.print(f"Default inference: {llm_status['default_mode']}")

    console.print()

    # LLM info
    if llm_status["local"]["available"]:
        console.print(f"Local LLM: {llm_status['local']['name']} ({llm_status['local']['model']})")
    else:
        console.print(f"[{BRAND_MUTED}]Local LLM: not detected[/]")

    console.print()

    console.print("Available:")
    console.print(f"  [{BRAND_SUCCESS}]✓[/] Local generation")
    if cloud_allowed:
        console.print(f"  [{BRAND_SUCCESS}]✓[/] Cloud generation")
        console.print(f"  [{BRAND_SUCCESS}]✓[/] Sync")
        console.print(f"  [{BRAND_SUCCESS}]✓[/] Publishing")
    else:
        reason = "requires login" if not authenticated else "locked"
        console.print(f"  [{BRAND_MUTED}]✗[/] Cloud generation ({reason})")
        console.print(f"  [{BRAND_MUTED}]✗[/] Sync ({reason})")
        console.print(f"  [{BRAND_MUTED}]✗[/] Publishing ({reason})")


@app.command()
def update(
    check: bool = typer.Option(False, "--check", "-c", help="Only check for updates, don't install"),
    force: bool = typer.Option(False, "--force", "-f", help="Force update even if already up to date"),
):
    """
    Update repr to the latest version.
    
    Automatically detects installation method (Homebrew, pip, or binary)
    and updates accordingly.
    
    Examples:
        repr update           # Update to latest version
        repr update --check   # Just check if update available
    """
    from .updater import check_for_update, perform_update
    
    if check:
        new_version = check_for_update()
        if new_version:
            print_info(f"New version available: v{new_version}")
            print_info("Run 'repr update' to install")
        else:
            print_success(f"Already up to date (v{__version__})")
    else:
        perform_update(force=force)


@app.command()
def doctor():
    """
    Health check and diagnostics.
    
    Example:
        repr doctor
    """
    from .doctor import run_all_checks
    
    console.print("Checking repr health...")
    console.print()
    
    report = run_all_checks()
    
    for check in report.checks:
        if check.status == "ok":
            icon = f"[{BRAND_SUCCESS}]✓[/]"
        elif check.status == "warning":
            icon = f"[{BRAND_WARNING}]⚠[/]"
        else:
            icon = f"[{BRAND_ERROR}]✗[/]"
        
        console.print(f"{icon} {check.name}: {check.message}")
    
    console.print()
    
    if report.recommendations:
        console.print("[bold]Recommendations:[/]")
        for i, rec in enumerate(report.recommendations, 1):
            console.print(f"  {i}. {rec}")
        console.print()
    
    if report.overall_status == "healthy":
        print_success("All systems healthy")
    elif report.overall_status == "warnings":
        print_warning("Some items need attention")
    else:
        print_error("Issues found - see recommendations above")


# Entry point
if __name__ == "__main__":
    app()
