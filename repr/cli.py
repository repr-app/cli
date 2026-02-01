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
from typing import Optional, List, Dict, Callable
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
    BatchProgress,
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
cron_app = typer.Typer(help="Scheduled story generation (every 4h)")
llm_app = typer.Typer(help="Configure LLM (local/cloud/BYOK)")
privacy_app = typer.Typer(help="Privacy audit and controls")
config_app = typer.Typer(help="View and modify configuration")
data_app = typer.Typer(help="Backup, restore, and manage data")
profile_app = typer.Typer(help="View and manage profile")
mcp_app = typer.Typer(help="MCP server for AI agent integration")
timeline_app = typer.Typer(help="Unified timeline of commits + AI sessions")

app.add_typer(hooks_app, name="hooks")
app.add_typer(cron_app, name="cron")
app.add_typer(llm_app, name="llm")
app.add_typer(privacy_app, name="privacy")
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(profile_app, name="profile")
app.add_typer(mcp_app, name="mcp")
app.add_typer(timeline_app, name="timeline")


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

    # Ask about automatic story generation
    console.print()
    console.print("[bold]Automatic Story Generation[/]")
    console.print()
    console.print("How should repr generate stories from your commits?")
    console.print()
    console.print(f"  [bold]1.[/] Scheduled (recommended) - Every 4 hours via cron")
    console.print(f"     [{BRAND_MUTED}]Predictable, batches work, never interrupts[/]")
    console.print()
    console.print(f"  [bold]2.[/] On commit - After every 5 commits via git hook")
    console.print(f"     [{BRAND_MUTED}]Real-time, but needs LLM running during commits[/]")
    console.print()
    console.print(f"  [bold]3.[/] Manual only - Run `repr generate` yourself")
    console.print(f"     [{BRAND_MUTED}]Full control, no automation[/]")
    console.print()

    schedule_choice = Prompt.ask(
        "Choose",
        choices=["1", "2", "3"],
        default="1",
    )

    from .hooks import install_hook
    from .cron import install_cron

    if schedule_choice == "1":
        # Scheduled via cron
        result = install_cron(interval_hours=4, min_commits=3)
        if result["success"]:
            print_success("Cron job installed (every 4h)")
            # Install hooks for queue tracking (but disable auto-generate)
            config = load_config()
            config["generation"]["auto_generate_on_hook"] = False
            save_config(config)
            for repo in repos:
                install_hook(Path(repo.path))
                set_repo_hook_status(str(repo.path), True)
        else:
            print_warning(f"Could not install cron: {result['message']}")
            print_info("You can set it up later with `repr cron install`")

    elif schedule_choice == "2":
        # On-commit via hooks
        config = load_config()
        config["generation"]["auto_generate_on_hook"] = True
        save_config(config)
        for repo in repos:
            install_hook(Path(repo.path))
            set_repo_hook_status(str(repo.path), True)
        print_success(f"Hooks installed in {len(repos)} repos (generates after 5 commits)")

    else:
        # Manual only - disable auto-generation
        config = load_config()
        config["generation"]["auto_generate_on_hook"] = False
        save_config(config)
        print_info("Manual mode - run `repr generate` when you want stories")

    console.print()
    print_next_steps([
        "repr week               See what you worked on this week",
        "repr generate --local   Save stories permanently",
        "repr login              Unlock cloud sync and publishing",
    ])


# =============================================================================
# GENERATE
# =============================================================================

# Technology detection from file extensions
_TECH_EXTENSIONS = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".scala": "Scala",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".graphql": "GraphQL",
    ".prisma": "Prisma",
}

# Special file name patterns that indicate technologies
_TECH_FILES = {
    "Dockerfile": "Docker",
    "docker-compose": "Docker",
    "package.json": "Node.js",
    "tsconfig.json": "TypeScript",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    ".eslintrc": "ESLint",
    "tailwind.config": "Tailwind CSS",
    "next.config": "Next.js",
    "vite.config": "Vite",
    "webpack.config": "Webpack",
}


def _detect_technologies_from_files(files: list[str]) -> list[str]:
    """
    Detect technologies from file paths/extensions.

    Args:
        files: List of file paths

    Returns:
        Sorted list of detected technology names
    """
    tech = set()

    for f in files:
        # Handle files as either dict with 'path' or string
        if isinstance(f, dict):
            f = f.get("path", "")

        # Check extensions
        for ext, name in _TECH_EXTENSIONS.items():
            if f.endswith(ext):
                tech.add(name)
                break

        # Check special file names
        for fname, name in _TECH_FILES.items():
            if fname in f:
                tech.add(name)

    return sorted(tech)


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
    import asyncio
    from .timeline import extract_commits_from_git, detect_project_root
    from .story_synthesis import synthesize_stories
    from .db import get_db
    from .privacy import check_cloud_permission, log_cloud_operation

    def synthesize_stories_sync(*args, **kwargs):
        return asyncio.run(synthesize_stories(*args, **kwargs))
    
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
        # Check config for default mode
        llm_config = get_llm_config()
        default_mode = llm_config.get("default", "local")

        if default_mode == "local":
            local = True
        elif default_mode == "cloud" and is_authenticated() and is_cloud_allowed():
            cloud = True
        else:
            # Fallback: local if not signed in or cloud not allowed
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
    
    all_generated_stories = []

    for repo_path in repo_paths:
        if not json_output:
            console.print(f"[bold]{repo_path.name}[/]")
            
        # Determine commit range
        repo_commits = []
        if commits:
             # Specific SHA list filtering
             repo_commits = extract_commits_from_git(repo_path, days=90)
             target_shas = [s.strip() for s in commits.split(",")]
             repo_commits = [c for c in repo_commits if any(c.sha.startswith(t) for t in target_shas)]
        elif since_date:
             # Parse date (rough approximation)
             filter_days = 30
             if "week" in since_date: filter_days = 14
             if "month" in since_date: filter_days = 30
             repo_commits = extract_commits_from_git(repo_path, days=filter_days)
        else:
             filter_days = days if days else 90
             repo_commits = extract_commits_from_git(repo_path, days=filter_days)
        
        if not repo_commits:
            if not json_output:
                console.print(f"  No matching commits found")
            continue
            
        if not json_output:
             console.print(f"  Analyzing {len(repo_commits)} commits...")

        # Progress callback
        def progress(current: int, total: int) -> None:
             if not json_output:
                 console.print(f"  Batch {current}/{total}")

        # Determine model based on mode
        if local:
            llm_config = get_llm_config()
            model = llm_config.get("local_model") or "llama3.2"
        else:
            model = None  # Use default cloud model

        try:
            # Run synthesis sync
            stories, index = synthesize_stories_sync(
                commits=repo_commits,
                model=model,
                batch_size=batch_size,
                progress_callback=progress,
            )

            # Generate public/internal posts for each story
            if stories and not dry_run:
                from .story_synthesis import transform_story_for_feed_sync, _build_fallback_post

                if not json_output:
                    console.print(f"  Generating build log posts...")

                for story in stories:
                    try:
                        # Generate Tripartite Codex content (internal includes all fields)
                        result = transform_story_for_feed_sync(story, mode="internal")

                        # Store structured fields
                        story.hook = result.hook
                        story.what = result.what
                        story.value = result.value
                        story.insight = result.insight
                        story.show = result.show

                        # Internal-specific fields
                        if hasattr(result, 'problem') and result.problem:
                            story.problem = result.problem
                        if hasattr(result, 'how') and result.how:
                            story.implementation_details = result.how

                        # Legacy fields for backward compatibility
                        story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
                        story.internal_post = story.public_post
                        story.public_show = result.show
                        story.internal_show = result.show
                    except Exception as e:
                        # Fallback: build from story data
                        from .story_synthesis import _build_fallback_codex
                        result = _build_fallback_codex(story, "internal")
                        story.hook = result.hook
                        story.what = result.what
                        story.value = result.value
                        story.insight = result.insight
                        story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
                        story.internal_post = story.public_post

            # Save to SQLite
            if not dry_run and stories:
                db = get_db()
                project_id = db.register_project(repo_path, repo_path.name)

                for story in stories:
                    db.save_story(story, project_id)

                # Update freshness with latest commit
                if repo_commits:
                    latest_commit = repo_commits[0]  # Already sorted by date desc
                    db.update_freshness(
                        project_id,
                        latest_commit.sha,
                        latest_commit.timestamp,
                    )

                if not json_output:
                    print_success(f"Saved {len(stories)} stories to SQLite")
            else:
                 if not json_output:
                     print_info("Dry run - not saved")

            all_generated_stories.extend(stories)

        except Exception as e:
            if not json_output:
                print_error(f"Failed to generate for {repo_path.name}: {e}")

    if json_output:
        print(json.dumps({
            "success": True, 
            "stories_count": len(all_generated_stories),
            "stories": [s.model_dump(mode="json") for s in all_generated_stories]
        }, default=str)) 
    elif all_generated_stories:
        console.print()
        print_success(f"Generated {len(all_generated_stories)} stories")
        print_info("Run `repr timeline serve` to view")


async def _generate_stories_async(
    commits: list[dict],
    repo_info,
    batch_size: int,
    local: bool,
    template: str = "resume",
    custom_prompt: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """Generate stories from commits using LLM (async implementation).
    
    Args:
        progress_callback: Optional callback with signature (batch_num, total_batches, status)
            where status is 'processing' or 'complete'
    """
    from .openai_analysis import get_openai_client, extract_commit_batch
    from .templates import build_generation_prompt, StoryOutput
    
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
            # Report progress - starting this batch
            if progress_callback:
                progress_callback(i + 1, len(batches), "processing")
            
            try:
                # Build prompt with template
                system_prompt, user_prompt = build_generation_prompt(
                    template_name=template,
                    repo_name=repo_info.name,
                    commits=batch,
                    custom_prompt=custom_prompt,
                )
                
                # Extract story from batch using structured output
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
                
                # Handle structured output - now returns list[StoryOutput]
                story_outputs: list[StoryOutput] = []
                if isinstance(result, list):
                    story_outputs = result
                elif isinstance(result, StoryOutput):
                    story_outputs = [result]
                else:
                    # Fallback for string response
                    content = result
                    if not content or content.startswith("[Batch"):
                        # Report progress - batch complete (even if empty)
                        if progress_callback:
                            progress_callback(i + 1, len(batches), "complete")
                        continue
                    lines = [l.strip() for l in content.split("\n") if l.strip()]
                    summary = lines[0] if lines else "Story"
                    summary = summary.lstrip("#-•* ").strip()
                    story_outputs = [StoryOutput(summary=summary, content=content)]

                # Build shared metadata for all stories from this batch
                commit_shas = [c["full_sha"] for c in batch]
                first_date = min(c["date"] for c in batch)
                last_date = max(c["date"] for c in batch)
                total_files = sum(len(c.get("files", [])) for c in batch)
                total_adds = sum(c.get("insertions", 0) for c in batch)
                total_dels = sum(c.get("deletions", 0) for c in batch)

                # Save each story from this batch
                for story_output in story_outputs:
                    content = story_output.content
                    summary = story_output.summary

                    if not content or content.startswith("[Batch"):
                        continue

                    # Get technologies from LLM output, fallback to file-based detection
                    technologies = story_output.technologies or []
                    if not technologies:
                        # Detect from files in this batch
                        all_files = []
                        for c in batch:
                            all_files.extend(c.get("files", []))
                        technologies = _detect_technologies_from_files(all_files)

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
                        # Technologies
                        "technologies": technologies,
                        # Categories
                        "category": story_output.category,
                        "scope": story_output.scope,
                        "stack": story_output.stack,
                        "initiative": story_output.initiative,
                        "complexity": story_output.complexity,
                    }

                    # Save story
                    story_id = save_story(content, metadata)
                    metadata["id"] = story_id
                    stories.append(metadata)
                
                # Report progress - batch complete
                if progress_callback:
                    progress_callback(i + 1, len(batches), "complete")
                
            except Exception as e:
                # Report progress even on failure
                if progress_callback:
                    progress_callback(i + 1, len(batches), "complete")
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
    custom_prompt: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """Generate stories from commits using LLM."""
    return asyncio.run(_generate_stories_async(
        commits=commits,
        repo_info=repo_info,
        batch_size=batch_size,
        local=local,
        template=template,
        custom_prompt=custom_prompt,
        progress_callback=progress_callback,
    ))


# =============================================================================
# STORIES MANAGEMENT
# =============================================================================

@app.command()
def stories(
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repository"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category (feature, bugfix, refactor, perf, infra, docs, test, chore)"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Filter by scope (user-facing, internal, platform, ops)"),
    stack: Optional[str] = typer.Option(None, "--stack", help="Filter by stack (frontend, backend, database, infra, mobile, fullstack)"),
    needs_review: bool = typer.Option(False, "--needs-review", help="Show only stories needing review"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List all stories.
    
    Example:
        repr stories
        repr stories --repo myproject
        repr stories --category feature
        repr stories --scope user-facing
        repr stories --stack backend
        repr stories --needs-review
    """
    story_list = list_stories(repo_name=repo, needs_review=needs_review)
    
    # Apply category filters (local filtering since storage doesn't support these yet)
    if category:
        story_list = [s for s in story_list if s.get("category") == category]
    if scope:
        story_list = [s for s in story_list if s.get("scope") == scope]
    if stack:
        story_list = [s for s in story_list if s.get("stack") == stack]
    
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
            
            # Category badge
            cat = story.get("category", "")
            cat_badge = f"[{BRAND_MUTED}][{cat}][/] " if cat else ""
            
            console.print(f"  {status} {cat_badge}{summary} [{BRAND_MUTED}]• {created}[/]")
        console.print()

    if len(story_list) > 20:
        console.print(f"[{BRAND_MUTED}]... and {len(story_list) - 20} more[/]")


@app.command()
def story(
    action: str = typer.Argument(..., help="Action: view, edit, delete, hide, feature, regenerate"),
    story_id: Optional[str] = typer.Argument(None, help="Story ID (ULID)"),
    all_stories: bool = typer.Option(False, "--all", help="Apply to all stories (for delete)"),
):
    """
    Manage a single story.
    
    Examples:
        repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV
        repr story delete 01ARYZ6S41TSV4RRFFQ69G5FAV
        repr story delete --all
    """
    # Handle --all flag for delete
    if all_stories:
        if action != "delete":
            print_error("--all flag only works with 'delete' action")
            raise typer.Exit(1)
        
        story_list = list_stories()
        if not story_list:
            print_info("No stories to delete")
            raise typer.Exit()
        
        console.print(f"This will delete [bold]{len(story_list)}[/] stories.")
        if confirm("Delete all stories?"):
            deleted = 0
            for s in story_list:
                try:
                    delete_story(s["id"])
                    deleted += 1
                except Exception:
                    pass
            print_success(f"Deleted {deleted} stories")
        else:
            print_info("Cancelled")
        raise typer.Exit()
    
    # Require story_id for single-story operations
    if not story_id:
        print_error("Story ID required (or use --all for delete)")
        raise typer.Exit(1)
    
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
        # Show categories if present
        cat = metadata.get("category")
        scope = metadata.get("scope")
        stack = metadata.get("stack")
        initiative = metadata.get("initiative")
        complexity = metadata.get("complexity")
        if cat or scope or stack:
            cats = [c for c in [cat, scope, stack, initiative, complexity] if c]
            console.print(f"[{BRAND_MUTED}]Categories: {', '.join(cats)}[/]")
    
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
    
    # Build batch payload
    from .api import push_stories_batch
    
    stories_payload = []
    for s in to_push:
        content, meta = load_story(s["id"])
        # Use local story ID as client_id for sync
        payload = {**meta, "content": content, "client_id": s["id"]}
        stories_payload.append(payload)
    
    # Push all stories in a single batch request
    try:
        result = asyncio.run(push_stories_batch(stories_payload))
        pushed = result.get("pushed", 0)
        results = result.get("results", [])
        
        # Mark successful stories as pushed and display results
        for i, story_result in enumerate(results):
            story_id_local = to_push[i]["id"]
            summary = to_push[i].get("summary", story_id_local)[:50]
            
            if story_result.get("success"):
                mark_story_pushed(story_id_local)
                console.print(f"  [{BRAND_SUCCESS}]✓[/] {summary}")
            else:
                error_msg = story_result.get("error", "Unknown error")
                console.print(f"  [{BRAND_ERROR}]✗[/] {summary}: {error_msg}")
        
    except (APIError, AuthError) as e:
        print_error(f"Batch push failed: {e}")
        raise typer.Exit(1)
    
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
                    payload = {**meta, "content": content, "client_id": s["id"]}
                    asyncio.run(api_push_story(payload))
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
# CRON SCHEDULING
# =============================================================================

@cron_app.command("install")
def cron_install(
    interval: int = typer.Option(4, "--interval", "-i", help="Hours between runs (default: 4)"),
    min_commits: int = typer.Option(3, "--min-commits", "-m", help="Minimum commits to trigger generation"),
):
    """
    Install cron job for automatic story generation.

    Runs every 4 hours by default, only generating if there are
    enough commits in the queue.

    Example:
        repr cron install
        repr cron install --interval 6 --min-commits 5
    """
    from .cron import install_cron

    result = install_cron(interval, min_commits)

    if result["success"]:
        if result["already_installed"]:
            print_success(result["message"])
        else:
            print_success(result["message"])
            console.print()
            console.print(f"[{BRAND_MUTED}]Stories will generate every {interval}h when queue has ≥{min_commits} commits[/]")
            console.print(f"[{BRAND_MUTED}]Logs: ~/.repr/logs/cron.log[/]")
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("remove")
def cron_remove():
    """
    Remove cron job for story generation.

    Example:
        repr cron remove
    """
    from .cron import remove_cron

    result = remove_cron()

    if result["success"]:
        print_success(result["message"])
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("pause")
def cron_pause():
    """
    Pause cron job without removing it.

    Example:
        repr cron pause
    """
    from .cron import pause_cron

    result = pause_cron()

    if result["success"]:
        print_success(result["message"])
        console.print(f"[{BRAND_MUTED}]Use `repr cron resume` to re-enable[/]")
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("resume")
def cron_resume():
    """
    Resume paused cron job.

    Example:
        repr cron resume
    """
    from .cron import resume_cron

    result = resume_cron()

    if result["success"]:
        print_success(result["message"])
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("status")
def cron_status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show cron job status.

    Example:
        repr cron status
    """
    from .cron import get_cron_status

    status = get_cron_status()

    if json_output:
        print(json.dumps(status, indent=2))
        return

    console.print("[bold]Cron Status[/]")
    console.print()

    if not status["installed"]:
        console.print(f"[{BRAND_MUTED}]○[/] Not installed")
        console.print()
        console.print(f"[{BRAND_MUTED}]Run `repr cron install` to enable scheduled generation[/]")
        return

    if status["paused"]:
        console.print(f"[{BRAND_WARNING}]⏸[/] Paused")
        console.print(f"  [{BRAND_MUTED}]Interval: every {status['interval_hours']}h[/]")
        console.print()
        console.print(f"[{BRAND_MUTED}]Run `repr cron resume` to re-enable[/]")
    else:
        console.print(f"[{BRAND_SUCCESS}]✓[/] Active")
        console.print(f"  [{BRAND_MUTED}]Interval: every {status['interval_hours']}h[/]")
        console.print(f"  [{BRAND_MUTED}]Logs: ~/.repr/logs/cron.log[/]")


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


@data_app.command("migrate-db")
def data_migrate_db(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be migrated"),
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Migrate specific project"),
):
    """
    Migrate store.json files to central SQLite database.

    This command imports existing .repr/store.json files into the central
    SQLite database at ~/.repr/stories.db for faster queries.

    Example:
        repr data migrate-db              # Migrate all tracked repos
        repr data migrate-db --dry-run    # Preview migration
        repr data migrate-db -p /path/to/repo
    """
    from .storage import migrate_stores_to_db, get_db_stats

    project_paths = [project] if project else None

    with create_spinner("Migrating stories to SQLite...") as progress:
        task = progress.add_task("migrating", total=None)

        if dry_run:
            console.print("[bold]Dry run mode - no changes will be made[/]\n")

        stats = migrate_stores_to_db(project_paths=project_paths, dry_run=dry_run)

        progress.update(task, completed=True)

    console.print()
    console.print(f"Projects scanned: {stats['projects_scanned']}")
    console.print(f"Projects migrated: {stats['projects_migrated']}")
    console.print(f"Stories imported: {stats['stories_imported']}")

    if stats['errors']:
        console.print()
        print_warning(f"{len(stats['errors'])} errors:")
        for error in stats['errors'][:5]:
            console.print(f"  • {error}")
        if len(stats['errors']) > 5:
            console.print(f"  ... and {len(stats['errors']) - 5} more")

    if not dry_run and stats['stories_imported'] > 0:
        console.print()
        db_stats = get_db_stats()
        console.print(f"Database: {db_stats['db_path']}")
        console.print(f"Total stories: {db_stats['story_count']}")
        console.print(f"Database size: {format_bytes(db_stats['db_size_bytes'])}")


@data_app.command("db-stats")
def data_db_stats():
    """
    Show SQLite database statistics.

    Example:
        repr data db-stats
    """
    from .storage import get_db_stats
    from .db import DB_PATH

    if not DB_PATH.exists():
        print_info("No SQLite database yet.")
        print_info("Run `repr data migrate-db` to create one.")
        return

    stats = get_db_stats()

    console.print("[bold]SQLite Database Stats[/]")
    console.print()
    console.print(f"Path: {stats['db_path']}")
    console.print(f"Size: {format_bytes(stats['db_size_bytes'])}")
    console.print()
    console.print(f"Stories: {stats['story_count']}")
    console.print(f"Projects: {stats['project_count']}")
    console.print(f"Unique files: {stats['unique_files']}")
    console.print(f"Unique commits: {stats['unique_commits']}")

    if stats['categories']:
        console.print()
        console.print("[bold]By Category:[/]")
        for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
            console.print(f"  {cat}: {count}")


@data_app.command("clear")
def data_clear(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Clear all stories from database and storage.

    This permanently deletes:
    - All stories from the SQLite database
    - All story files from ~/.repr/stories/

    Projects registry and config are preserved.

    Example:
        repr data clear           # With confirmation
        repr data clear --force   # Skip confirmation
    """
    from .db import DB_PATH
    from .storage import STORIES_DIR
    import shutil

    # Check what exists
    db_exists = DB_PATH.exists()
    stories_dir_exists = STORIES_DIR.exists()

    if not db_exists and not stories_dir_exists:
        print_info("Nothing to clear - no database or stories found.")
        return

    # Count what we're about to delete
    story_count = 0
    db_size = 0
    stories_file_count = 0

    if db_exists:
        from .storage import get_db_stats
        try:
            stats = get_db_stats()
            story_count = stats.get('story_count', 0)
            db_size = stats.get('db_size_bytes', 0)
        except Exception:
            db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    if stories_dir_exists:
        stories_file_count = len(list(STORIES_DIR.glob("*")))

    # Show what will be deleted
    console.print("[bold red]This will permanently delete:[/]")
    console.print()
    if db_exists:
        console.print(f"  • Database: {DB_PATH}")
        console.print(f"    {story_count} stories, {format_bytes(db_size)}")
    if stories_dir_exists and stories_file_count > 0:
        console.print(f"  • Story files: {STORIES_DIR}")
        console.print(f"    {stories_file_count} files")
    console.print()
    console.print("[dim]Projects registry and config will be preserved.[/]")
    console.print()

    if not force:
        if not confirm("Are you sure you want to delete all stories?"):
            print_info("Cancelled")
            raise typer.Exit()

    # Delete database
    if db_exists:
        try:
            # Also delete WAL and SHM files if they exist
            DB_PATH.unlink()
            wal_path = DB_PATH.with_suffix(".db-wal")
            shm_path = DB_PATH.with_suffix(".db-shm")
            if wal_path.exists():
                wal_path.unlink()
            if shm_path.exists():
                shm_path.unlink()
        except Exception as e:
            print_error(f"Failed to delete database: {e}")
            raise typer.Exit(1)

    # Delete stories directory contents (but keep the directory)
    if stories_dir_exists:
        try:
            shutil.rmtree(STORIES_DIR)
            STORIES_DIR.mkdir(exist_ok=True)
        except Exception as e:
            print_error(f"Failed to clear stories directory: {e}")
            raise typer.Exit(1)

    print_success("All stories cleared")
    if db_exists:
        console.print(f"  Deleted: {story_count} stories from database")
    if stories_file_count > 0:
        console.print(f"  Deleted: {stories_file_count} story files")


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
def changes(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to repository (default: current directory)",
        exists=True,
        resolve_path=True,
    ),
    explain: bool = typer.Option(False, "--explain", "-e", help="Use LLM to explain changes"),
    compact: bool = typer.Option(False, "--compact", "-c", help="Compact output (no diff previews)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show file changes across git states with diff details.

    Displays changes in three states:
    - Unstaged: Tracked files modified but not staged (with diff preview)
    - Staged: Changes ready to commit (with diff preview)
    - Unpushed: Commits not yet pushed to remote

    Example:
        repr changes              # Show changes with diffs
        repr changes --compact    # Just file names
        repr changes --explain    # LLM summary
        repr changes --json
    """
    from .change_synthesis import (
        get_change_report,
        ChangeState,
        explain_group,
    )

    target_path = path or Path.cwd()
    report = get_change_report(target_path)

    if not report:
        print_error(f"Not a git repository: {target_path}")
        raise typer.Exit(1)

    if json_output:
        data = {
            "repo_path": str(report.repo_path),
            "timestamp": report.timestamp.isoformat(),
            "unstaged": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                }
                for f in report.unstaged
            ],
            "staged": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                }
                for f in report.staged
            ],
            "unpushed": [
                {
                    "sha": c.sha,
                    "message": c.message,
                    "author": c.author,
                    "timestamp": c.timestamp.isoformat(),
                    "files": [{"path": f.path, "change_type": f.change_type} for f in c.files],
                }
                for c in report.unpushed
            ],
        }
        if report.summary:
            data["summary"] = {
                "hook": report.summary.hook,
                "what": report.summary.what,
                "value": report.summary.value,
                "problem": report.summary.problem,
                "insight": report.summary.insight,
                "show": report.summary.show,
            }
        print(json.dumps(data, indent=2))
        return

    if not report.has_changes:
        print_info("No changes detected.")
        console.print(f"[{BRAND_MUTED}]Working tree clean, nothing staged, up to date with remote.[/]")
        raise typer.Exit()

    # Get LLM client if explain mode
    client = None
    if explain:
        from .openai_analysis import get_openai_client
        client = get_openai_client()
        if not client:
            print_error("LLM not configured. Run `repr llm setup` first.")
            raise typer.Exit(1)

    # Header
    console.print(f"[bold]Changes in {report.repo_path.name}[/]")
    console.print()

    # Unstaged changes
    if report.unstaged:
        console.print(f"[bold][{BRAND_WARNING}]Unstaged[/][/] ({len(report.unstaged)} files)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining unstaged..."):
                explanation = asyncio.run(explain_group("unstaged", file_changes=report.unstaged, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for f in report.unstaged:
            type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
            stats = ""
            if f.insertions or f.deletions:
                stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
            full_path = report.repo_path / f.path
            console.print(f"  {type_icon} {full_path}{stats}")
            # Show diff preview unless compact mode
            if not compact and f.diff_preview:
                for line in f.diff_preview.split("\n")[:10]:
                    if line.startswith("+"):
                        console.print(f"    [{BRAND_SUCCESS}]{line}[/]")
                    elif line.startswith("-"):
                        console.print(f"    [{BRAND_ERROR}]{line}[/]")
        console.print()

    # Staged changes
    if report.staged:
        console.print(f"[bold][{BRAND_SUCCESS}]Staged[/][/] ({len(report.staged)} files)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining staged..."):
                explanation = asyncio.run(explain_group("staged", file_changes=report.staged, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for f in report.staged:
            type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
            stats = ""
            if f.insertions or f.deletions:
                stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
            full_path = report.repo_path / f.path
            console.print(f"  {type_icon} {full_path}{stats}")
            # Show diff preview unless compact mode
            if not compact and f.diff_preview:
                for line in f.diff_preview.split("\n")[:10]:
                    if line.startswith("+"):
                        console.print(f"    [{BRAND_SUCCESS}]{line}[/]")
                    elif line.startswith("-"):
                        console.print(f"    [{BRAND_ERROR}]{line}[/]")
        console.print()

    # Unpushed commits
    if report.unpushed:
        console.print(f"[bold][{BRAND_PRIMARY}]Unpushed[/][/] ({len(report.unpushed)} commits)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining unpushed..."):
                explanation = asyncio.run(explain_group("unpushed", commit_changes=report.unpushed, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for commit in report.unpushed:
            console.print(f"  [{BRAND_MUTED}]{commit.sha}[/] {commit.message}")
            # Show files changed in this commit
            for f in commit.files[:5]:
                type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
                full_path = report.repo_path / f.path
                console.print(f"    {type_icon} {full_path}")
            if len(commit.files) > 5:
                console.print(f"    [{BRAND_MUTED}]... +{len(commit.files) - 5} more[/]")
        console.print()


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


# =============================================================================
# MCP SERVER
# =============================================================================

@mcp_app.command("serve")
def mcp_serve(
    sse: bool = typer.Option(False, "--sse", help="Use SSE transport instead of stdio"),
    port: int = typer.Option(3001, "--port", "-p", help="Port for SSE mode"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host for SSE mode"),
):
    """
    Start the MCP server for AI agent integration.
    
    The MCP (Model Context Protocol) server exposes repr functionality
    to AI agents like Claude Code, Cursor, Windsurf, and Cline.
    
    Examples:
        repr mcp serve              # stdio mode (default)
        repr mcp serve --sse        # SSE mode for remote clients
        repr mcp serve --port 3001  # Custom port for SSE
    
    Configuration for Claude Code:
        claude mcp add repr -- repr mcp serve
    
    Configuration for Cursor/Windsurf (mcp.json):
        {
          "mcpServers": {
            "repr": {
              "command": "repr",
              "args": ["mcp", "serve"]
            }
          }
        }
    """
    from .mcp_server import run_server
    
    if not sse:
        # stdio mode - silent start, let MCP handle communication
        run_server(sse=False)
    else:
        console.print(f"Starting MCP server (SSE mode) on {host}:{port}...")
        run_server(sse=True, host=host, port=port)


@mcp_app.command("info")
def mcp_info():
    """
    Show MCP server configuration info.
    
    Example:
        repr mcp info
    """
    console.print("[bold]MCP Server Info[/]")
    console.print()
    console.print("The MCP server exposes repr to AI agents via the Model Context Protocol.")
    console.print()
    console.print("[bold]Available Tools:[/]")
    console.print("  • repr_generate    — Generate stories from commits")
    console.print("  • repr_stories_list — List existing stories")
    console.print("  • repr_week        — Weekly work summary")
    console.print("  • repr_standup     — Yesterday/today summary")
    console.print("  • repr_profile     — Get developer profile")
    console.print()
    console.print("[bold]Available Resources:[/]")
    console.print("  • repr://profile        — Current profile")
    console.print("  • repr://stories/recent — Recent stories")
    console.print()
    console.print("[bold]Usage:[/]")
    console.print("  repr mcp serve              # Start server (stdio)")
    console.print("  repr mcp serve --sse        # SSE mode")
    console.print()
    console.print("[bold]Claude Code setup:[/]")
    console.print("  claude mcp add repr -- repr mcp serve")


@mcp_app.command("install-skills")
def mcp_install_skills(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skill files"),
):
    """
    Install repr skills to Claude Code.

    Installs a skill that teaches Claude Code how and when to use repr commands
    (init, generate, timeline, changes).

    Example:
        repr mcp install-skills
        repr mcp install-skills --force  # Overwrite existing
    """
    plugin_dir = Path.home() / ".claude" / "plugins" / "local" / "repr"
    skill_dir = plugin_dir / "skills" / "repr"
    plugin_json_dir = plugin_dir / ".claude-plugin"

    # Check if already installed
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists() and not force:
        print_warning("repr skill already installed")
        console.print(f"  Location: {skill_file}")
        console.print()
        console.print("Use --force to overwrite")
        return

    # Create directories
    skill_dir.mkdir(parents=True, exist_ok=True)
    plugin_json_dir.mkdir(parents=True, exist_ok=True)

    # Write plugin.json
    plugin_json = {
        "name": "repr",
        "description": "Developer context layer - understand what you've actually worked on through git history and AI sessions.",
        "author": {"name": "repr.dev"}
    }
    (plugin_json_dir / "plugin.json").write_text(json.dumps(plugin_json, indent=2) + "\n")

    # Write skill file
    skill_content = '''---
name: repr
description: Use this skill when the user asks to "show my changes", "what did I work on", "generate a story", "initialize repr", "show timeline", "set up repr", or needs context about their recent development work.
version: 1.0.0
---

# repr - Developer Context Layer

repr helps developers understand what they've actually worked on by analyzing git history and AI sessions.

## When to Use repr

- User asks about their recent work or changes
- User wants to generate a story or summary from commits
- User needs to set up repr for a project
- User wants to see their development timeline
- User asks "what did I work on" or similar

## Commands

### Initialize repr

```bash
# First-time setup - scan for repositories
repr init

# Scan specific directory
repr init ~/projects
```

Use when: User is setting up repr for the first time or adding new repositories.

### Show Changes

```bash
# Show current changes (unstaged, staged, unpushed)
repr changes

# Compact view (just file names)
repr changes --compact

# With LLM explanation
repr changes --explain

# JSON output
repr changes --json
```

Use when: User asks "what are my changes", "show my work", "what's uncommitted", or needs to understand current git state.

### Generate Stories

```bash
# Generate stories from recent commits
repr generate

# Generate for specific date range
repr generate --since monday
repr generate --since "2 weeks ago"

# Use local LLM (Ollama)
repr generate --local

# Dry run (preview without saving)
repr generate --dry-run
```

Use when: User wants to create narratives from their commits, document their work, or generate content for standup/weekly reports.

### Timeline

```bash
# Initialize timeline for current project
repr timeline init

# Initialize with AI session ingestion
repr timeline init --with-sessions

# Show timeline entries
repr timeline show
repr timeline show --days 14

# Filter by type
repr timeline show --type commit
repr timeline show --type session

# Show timeline status
repr timeline status

# Refresh/update timeline
repr timeline refresh

# Serve timeline viewer in browser
repr timeline serve
```

Use when: User wants a unified view of commits and AI sessions, or needs to understand the full context of their development work.

## Output Interpretation

### Changes Output
- **Unstaged**: Modified files not yet staged (with diff preview)
- **Staged**: Changes ready to commit
- **Unpushed**: Commits not yet pushed to remote

### Timeline Entry Types
- **commit**: Regular git commits
- **session**: AI coding sessions (Claude Code, etc.)
- **merged**: Commits with associated AI session context

### Smart Git Workflow

```bash
# Stage files
repr add .py              # Stage *.py files
repr add .                # Stage all
repr add src/             # Stage directory

# Generate message and commit
repr commit               # AI generates message
repr commit -m "fix: x"   # Custom message
repr commit -r            # Regenerate message

# Push to remote
repr push
```

Use when: User wants to stage, commit with AI-generated message, or push.

## Tips

1. Run `repr changes` before committing to see what you're about to commit
2. Use `repr generate --dry-run` to preview stories before saving
3. Initialize timeline with `--with-sessions` to capture AI context
4. Use `repr timeline show --type session` to see AI-assisted work separately
5. Use `repr commit add` for quick commits with AI-generated messages
'''

    skill_file.write_text(skill_content)

    print_success("repr skill installed to Claude Code")
    console.print()
    console.print(f"  Plugin: {plugin_dir}")
    console.print(f"  Skill: {skill_file}")
    console.print()
    console.print("Claude Code will now recognize repr commands.")
    console.print("Try asking: 'show my changes' or 'what did I work on'")


# =============================================================================
# TIMELINE
# =============================================================================

@timeline_app.command("init")
def timeline_init(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project path (default: current directory)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    with_sessions: bool = typer.Option(
        False, "--with-sessions", "-s",
        help="Include AI session context (Claude Code, Clawdbot)",
    ),
    days: int = typer.Option(
        90, "--days", "-d",
        help="Number of days to look back",
    ),
    max_commits: int = typer.Option(
        500, "--max-commits",
        help="Maximum commits to include",
    ),
    model: str = typer.Option(
        "openai/gpt-4.1-mini", "--model", "-m",
        help="Model for session extraction (with --with-sessions)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing timeline",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Initialize a project timeline from git commits and AI sessions.
    
    Creates .repr/timeline.json with unified context from:
    - Git commits (always included)
    - AI session logs (with --with-sessions flag)
    
    Examples:
        repr timeline init                    # Commits only
        repr timeline init --with-sessions    # Include AI sessions
        repr timeline init --days 30          # Last 30 days
        repr timeline init ~/myproject        # Specific project
    """
    from .timeline import (
        detect_project_root,
        is_initialized,
        init_timeline_commits_only,
        init_timeline_with_sessions_sync,
        get_timeline_stats,
    )
    from .loaders import detect_session_source
    
    # Determine project path
    project_path = path or Path.cwd()
    
    # Check if in git repo
    repo_root = detect_project_root(project_path)
    if not repo_root:
        print_error(f"Not a git repository: {project_path}")
        print_info("Run this command inside a git repository")
        raise typer.Exit(1)
    
    project_path = repo_root
    
    # Check if already initialized
    if is_initialized(project_path) and not force:
        print_warning(f"Timeline already exists for {project_path}")
        print_info("Use --force to reinitialize")
        raise typer.Exit(1)
    
    if not json_output:
        print_header()
        console.print(f"Initializing timeline for [bold]{project_path.name}[/]")
        console.print()
    
    # Check for session sources if --with-sessions
    session_sources = []
    if with_sessions:
        session_sources = detect_session_source(project_path)
        if not session_sources:
            if not json_output:
                print_warning("No AI session sources found for this project")
                print_info("Supported: Claude Code (~/.claude/projects/), Clawdbot (~/.clawdbot/)")
                if not confirm("Continue with commits only?", default=True):
                    raise typer.Exit(0)
            with_sessions = False
        else:
            if not json_output:
                console.print(f"Session sources: {', '.join(session_sources)}")
    
    # Progress tracking
    progress_state = {"stage": "", "current": 0, "total": 0}
    
    def progress_callback(stage: str, current: int, total: int) -> None:
        progress_state["stage"] = stage
        progress_state["current"] = current
        progress_state["total"] = total
    
    try:
        if with_sessions:
            # Get API key for extraction
            # Priority: BYOK OpenAI > env OPENAI_API_KEY > LiteLLM (cloud)
            api_key = None
            byok_config = get_byok_config("openai")
            if byok_config:
                api_key = byok_config.get("api_key")
            
            if not api_key:
                # Try environment variable (direct OpenAI access)
                api_key = os.environ.get("OPENAI_API_KEY")
            
            if not api_key:
                # Try LiteLLM config (cloud mode - needs LiteLLM proxy URL)
                _, litellm_key = get_litellm_config()
                api_key = litellm_key
            
            if not api_key:
                if not json_output:
                    print_warning("No API key configured for session extraction")
                    print_info("Configure with: repr llm add openai")
                    print_info("Or set OPENAI_API_KEY environment variable")
                    if not confirm("Continue with commits only?", default=True):
                        raise typer.Exit(0)
                with_sessions = False
        
        if with_sessions:
            if not json_output:
                with create_spinner() as progress:
                    task = progress.add_task("Initializing...", total=None)
                    timeline = init_timeline_with_sessions_sync(
                        project_path,
                        days=days,
                        max_commits=max_commits,
                        session_sources=session_sources,
                        api_key=api_key,
                        model=model,
                        progress_callback=progress_callback,
                    )
            else:
                timeline = init_timeline_with_sessions_sync(
                    project_path,
                    days=days,
                    max_commits=max_commits,
                    session_sources=session_sources,
                    api_key=api_key,
                    model=model,
                )
        else:
            if not json_output:
                with create_spinner() as progress:
                    task = progress.add_task("Scanning commits...", total=None)
                    timeline = init_timeline_commits_only(
                        project_path,
                        days=days,
                        max_commits=max_commits,
                        progress_callback=progress_callback,
                    )
            else:
                timeline = init_timeline_commits_only(
                    project_path,
                    days=days,
                    max_commits=max_commits,
                )
        
        # Get stats
        stats = get_timeline_stats(timeline)
        
        if json_output:
            print(json.dumps({
                "success": True,
                "project": str(project_path),
                "timeline_path": str(project_path / ".repr" / "timeline.json"),
                "stats": stats,
            }, indent=2))
        else:
            console.print()
            print_success(f"Timeline initialized!")
            console.print()
            console.print(f"  Location: .repr/timeline.json")
            console.print(f"  Entries: {stats['total_entries']}")
            console.print(f"    Commits: {stats['commit_count']}")
            if stats['merged_count'] > 0:
                console.print(f"    Merged (commit + session): {stats['merged_count']}")
            if stats['session_count'] > 0:
                console.print(f"    Sessions only: {stats['session_count']}")
            if stats['date_range']['first']:
                console.print(f"  Date range: {stats['date_range']['first'][:10]} to {stats['date_range']['last'][:10]}")
            
            console.print()
            print_next_steps([
                "repr timeline status      View timeline status",
                "repr timeline show        Browse timeline entries",
            ])
    
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print_error(f"Failed to initialize timeline: {e}")
        raise typer.Exit(1)


@timeline_app.command("status")
def timeline_status(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project path (default: current directory)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Show timeline status for a project.
    
    Example:
        repr timeline status
    """
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        get_timeline_stats,
    )
    
    # Determine project path
    project_path = path or Path.cwd()
    repo_root = detect_project_root(project_path)
    
    if not repo_root:
        print_error(f"Not a git repository: {project_path}")
        raise typer.Exit(1)
    
    project_path = repo_root
    
    if not is_initialized(project_path):
        if json_output:
            print(json.dumps({"initialized": False, "project": str(project_path)}, indent=2))
        else:
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
        raise typer.Exit(1)
    
    timeline = load_timeline(project_path)
    if not timeline:
        print_error("Failed to load timeline")
        raise typer.Exit(1)
    
    stats = get_timeline_stats(timeline)
    
    if json_output:
        print(json.dumps({
            "initialized": True,
            "project": str(project_path),
            "stats": stats,
            "last_updated": timeline.last_updated.isoformat() if timeline.last_updated else None,
        }, indent=2))
    else:
        print_header()
        console.print(f"Timeline: [bold]{project_path.name}[/]")
        console.print()
        console.print(f"  Entries: {stats['total_entries']}")
        console.print(f"    Commits: {stats['commit_count']}")
        console.print(f"    Merged: {stats['merged_count']}")
        console.print(f"    Sessions: {stats['session_count']}")
        if stats['date_range']['first']:
            console.print(f"  Date range: {stats['date_range']['first'][:10]} to {stats['date_range']['last'][:10]}")
        if stats['session_sources']:
            console.print(f"  Session sources: {', '.join(stats['session_sources'])}")
        if timeline.last_updated:
            last_updated_str = timeline.last_updated.isoformat() if hasattr(timeline.last_updated, 'isoformat') else str(timeline.last_updated)
            console.print(f"  Last updated: {format_relative_time(last_updated_str)}")


@timeline_app.command("show")
def timeline_show(
    path: Optional[str] = typer.Argument(
        None,
        help="Project path (use '.' for current repo, omit for all repos)",
    ),
    days: int = typer.Option(
        7, "--days", "-d",
        help="Show entries from last N days",
    ),
    entry_type: Optional[str] = typer.Option(
        None, "--type", "-t",
        help="Filter by type: commit, session, merged",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n",
        help="Maximum entries to show",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
    public: bool = typer.Option(
        True, "--public/--no-public",
        help="Build-in-public feed format (default)",
    ),
    internal: bool = typer.Option(
        False, "--internal",
        help="Show technical details in feed",
    ),
    raw: bool = typer.Option(
        False, "--raw",
        help="Show raw timeline entries (commits/sessions)",
    ),
    all_repos: bool = typer.Option(
        False, "--all", "-a",
        help="Show stories from all tracked repos (default when no path given)",
    ),
    group: bool = typer.Option(
        False, "--group", "-g",
        help="Group stories by project (presentation view)",
    ),
):
    """
    Show timeline entries.

    Examples:
        repr timeline show                    # All tracked repos from database
        repr timeline show .                  # Current repo only
        repr timeline show /path/to/repo      # Specific repo
        repr timeline show --group            # All repos, grouped by project
        repr timeline show . --days 30        # Current repo, last 30 days
        repr timeline show --internal         # Feed format with tech details
    """
    from datetime import timezone
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        query_timeline,
    )
    from .models import TimelineEntryType
    from .db import get_db

    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Determine mode: all repos (no path) vs specific repo (path given)
    show_all_repos = path is None and not raw

    # If --all flag is given, always show all repos
    if all_repos:
        show_all_repos = True

    project_path = None
    timeline = None
    entries = []

    if not show_all_repos:
        # Specific repo mode - resolve path
        resolved_path = Path(path) if path else Path.cwd()
        if not resolved_path.is_absolute():
            resolved_path = Path.cwd() / resolved_path
        resolved_path = resolved_path.resolve()

        repo_root = detect_project_root(resolved_path)

        if not repo_root:
            print_error(f"Not a git repository: {resolved_path}")
            raise typer.Exit(1)

        project_path = repo_root

        if not is_initialized(project_path):
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
            raise typer.Exit(1)

        timeline = load_timeline(project_path)
        if not timeline:
            print_error("Failed to load timeline")
            raise typer.Exit(1)

        # Parse entry type filter
        entry_types = None
        if entry_type:
            try:
                entry_types = [TimelineEntryType(entry_type)]
            except ValueError:
                print_error(f"Invalid type: {entry_type}")
                print_info("Valid types: commit, session, merged")
                raise typer.Exit(1)

        # Query entries
        entries = query_timeline(timeline, since=since, entry_types=entry_types)
        entries = entries[-limit:]  # Take most recent

    if json_output:
        if show_all_repos:
            # JSON output for all repos
            stories = db.list_stories(since=since, limit=limit)
            print(json.dumps({
                "mode": "all_repos",
                "stories": [{"id": s.id, "title": s.title, "project_id": s.project_id} for s in stories],
            }, indent=2))
        else:
            from .timeline import _serialize_entry
            print(json.dumps({
                "project": str(project_path),
                "entries": [_serialize_entry(e) for e in entries],
            }, indent=2))
        return

    if not show_all_repos and not entries:
        print_info(f"No entries in the last {days} days")
        return

    # Feed format (default, unless --raw)
    if not raw:
        # Build project lookup
        projects = {p["id"]: p["name"] for p in db.list_projects()}

        if show_all_repos:
            # Show stories from all repos
            stories = db.list_stories(since=since, limit=limit)
            header_name = "all repos"
        else:
            # Show stories from current repo only
            project = db.get_project_by_path(project_path)

            if not project:
                print_info(f"No stories found. Run 'repr generate' first.")
                return

            stories = db.list_stories(project_id=project["id"], since=since, limit=limit)
            header_name = project_path.name

        if not stories:
            print_info(f"No stories in the last {days} days. Run 'repr generate' first.")
            return

        def format_rel_time(story_time):
            """Format timestamp as relative time."""
            local_time = story_time.astimezone()
            now = datetime.now(local_time.tzinfo)
            delta = now - local_time

            if delta.days == 0:
                if delta.seconds < 3600:
                    return f"{delta.seconds // 60}m ago"
                else:
                    return f"{delta.seconds // 3600}h ago"
            elif delta.days == 1:
                return "Yesterday"
            elif delta.days < 7:
                return f"{delta.days} days ago"
            else:
                return local_time.strftime("%b %d")

        def render_story(story, show_repo=False):
            """Render a single story entry using Tripartite Codex structure."""
            story_time = story.started_at or story.created_at
            rel_time = format_rel_time(story_time)
            repo_name = projects.get(story.project_id, "unknown")

            # Header with time and optional repo
            if show_repo:
                console.print(f"[{BRAND_PRIMARY}]{repo_name}[/] · [{BRAND_MUTED}]{rel_time}[/]")
            else:
                console.print(f"[{BRAND_MUTED}]{rel_time}[/]")

            # Use structured fields if available, fall back to legacy
            if story.hook:
                # New Tripartite Codex format
                console.print(f"[bold]{story.hook}[/]")
                console.print()
                what_text = story.what.rstrip(".")
                console.print(f"{what_text}. {story.value}")

                # Show block if present
                if story.show:
                    console.print()
                    console.print(f"```\n{story.show}\n```")

                # Internal mode: show problem and how
                if internal:
                    if story.problem:
                        console.print()
                        console.print(f"[{BRAND_MUTED}]Problem:[/] {story.problem}")

                    if story.implementation_details:
                        console.print()
                        console.print(f"[{BRAND_MUTED}]How:[/]")
                        for detail in story.implementation_details[:5]:
                            console.print(f"  [{BRAND_MUTED}]›[/] {detail}")

                # Insight
                if story.insight:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Insight:[/] {story.insight}")

            else:
                # Legacy format fallback
                post_text = story.public_post or story.title
                if internal:
                    post_text = story.internal_post or post_text
                console.print(post_text)

                show_block = story.show or story.public_show
                if internal:
                    show_block = show_block or story.internal_show
                if show_block:
                    console.print()
                    console.print(f"```\n{show_block}\n```")

                if internal and story.internal_details:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Implementation:[/]")
                    for detail in story.internal_details[:5]:
                        console.print(f"  [{BRAND_MUTED}]›[/] {detail}")

            # Recall data (internal mode only) - file changes and snippets
            if internal:
                # File changes summary
                if story.file_changes:
                    total_changes = f"+{story.total_insertions}/-{story.total_deletions}" if (story.total_insertions or story.total_deletions) else ""
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Files changed ({len(story.file_changes)})[/] [{BRAND_MUTED}]{total_changes}[/]")
                    for fc in story.file_changes[:8]:  # Show up to 8 files
                        change_indicator = {"added": "+", "deleted": "-", "modified": "~"}.get(fc.change_type, "~")
                        stats = f"[green]+{fc.insertions}[/][{BRAND_MUTED}]/[/][red]-{fc.deletions}[/]" if (fc.insertions or fc.deletions) else ""
                        console.print(f"  [{BRAND_MUTED}]{change_indicator}[/] {fc.file_path} {stats}")
                    if len(story.file_changes) > 8:
                        console.print(f"  [{BRAND_MUTED}]... and {len(story.file_changes) - 8} more files[/]")

                # Key code snippets
                if story.key_snippets:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Snippets:[/]")
                    for snippet in story.key_snippets[:2]:  # Show up to 2 snippets
                        lang = snippet.language or ""
                        console.print(f"  [{BRAND_MUTED}]{snippet.file_path}[/]")
                        console.print(f"```{lang}\n{snippet.content}\n```")

            console.print()
            console.print(f"[{BRAND_MUTED}]{'─' * 60}[/]")
            console.print()

        print_header()

        if group and all_repos:
            # Grouped view: organize by project
            console.print(f"[bold]@all repos[/] · build log [dim](grouped)[/]")
            console.print()

            # Group stories by project
            from collections import defaultdict
            stories_by_project = defaultdict(list)
            for story in stories:
                stories_by_project[story.project_id].append(story)

            # Render each project group
            for project_id, project_stories in stories_by_project.items():
                project_name = projects.get(project_id, "unknown")
                console.print(f"[bold]── {project_name} ──[/]")
                console.print()

                for story in project_stories:
                    render_story(story, show_repo=False)

        else:
            # Timeline view (default)
            console.print(f"[bold]@{header_name}[/] · build log")
            console.print()

            for story in stories:
                render_story(story, show_repo=all_repos)

        return

    # Default format (unchanged)
    print_header()
    console.print(f"Timeline: [bold]{project_path.name}[/] (last {days} days)")
    console.print()

    for entry in reversed(entries):  # Show newest first
        # Format timestamp (convert to local timezone)
        local_ts = entry.timestamp.astimezone()
        ts = local_ts.strftime("%Y-%m-%d %H:%M")

        # Entry type indicator
        if entry.type == TimelineEntryType.COMMIT:
            type_icon = "📝"
        elif entry.type == TimelineEntryType.SESSION:
            type_icon = "💬"
        else:  # MERGED
            type_icon = "🔗"

        # Build description
        if entry.commit:
            # Show first line of commit message
            msg = entry.commit.message.split("\n")[0][:60]
            if len(entry.commit.message.split("\n")[0]) > 60:
                msg += "..."
            desc = f"{msg}"
            sha = entry.commit.sha[:8]
            console.print(f"{type_icon} [{BRAND_MUTED}]{ts}[/] [{BRAND_PRIMARY}]{sha}[/] {desc}")
        elif entry.session_context:
            # Show problem from session
            problem = entry.session_context.problem[:60]
            if len(entry.session_context.problem) > 60:
                problem += "..."
            console.print(f"{type_icon} [{BRAND_MUTED}]{ts}[/] {problem}")

        # Show session context if merged
        if entry.type == TimelineEntryType.MERGED and entry.session_context:
            console.print(f"    [{BRAND_MUTED}]→ {entry.session_context.problem[:70]}[/]")

        console.print()


@timeline_app.command("refresh")
def timeline_refresh(
    path: Optional[str] = typer.Argument(
        None,
        help="Project path (use '.' for current repo, omit for all repos)",
    ),
    limit: int = typer.Option(
        50, "--limit", "-n",
        help="Maximum stories to refresh",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Regenerate posts for existing stories.

    This updates the public_post and internal_post fields without
    re-analyzing commits. Useful after prompt improvements.

    Examples:
        repr timeline refresh              # Refresh all repos
        repr timeline refresh .            # Refresh current repo only
        repr timeline refresh --limit 10   # Refresh last 10 stories
    """
    from .db import get_db
    from .story_synthesis import (
        transform_story_for_feed_sync,
        _build_fallback_post,
        extract_file_changes_from_commits,
        extract_key_snippets_from_commits,
    )

    db = get_db()

    # Determine scope
    if path is None:
        # All repos
        stories = db.list_stories(limit=limit)
        scope_name = "all repos"
    else:
        # Specific repo
        from .timeline import detect_project_root
        resolved_path = Path(path) if path else Path.cwd()
        if not resolved_path.is_absolute():
            resolved_path = Path.cwd() / resolved_path
        resolved_path = resolved_path.resolve()

        repo_root = detect_project_root(resolved_path)
        if not repo_root:
            print_error(f"Not a git repository: {resolved_path}")
            raise typer.Exit(1)

        project = db.get_project_by_path(repo_root)
        if not project:
            print_error(f"No stories found for {repo_root.name}")
            raise typer.Exit(1)

        stories = db.list_stories(project_id=project["id"], limit=limit)
        scope_name = repo_root.name

    if not stories:
        print_info("No stories to refresh")
        return

    print_header()
    console.print(f"Refreshing {len(stories)} stories from {scope_name}...")
    console.print()

    refreshed = 0
    failed = 0

    # Get project paths for file extraction
    project_paths = {}
    for p in db.list_projects():
        project_paths[p["id"]] = p["path"]

    for story in stories:
        try:
            # Extract file changes and snippets from git
            project_path = project_paths.get(story.project_id)
            if story.commit_shas and project_path:
                file_changes, total_ins, total_del = extract_file_changes_from_commits(
                    story.commit_shas, project_path
                )
                story.file_changes = file_changes
                story.total_insertions = total_ins
                story.total_deletions = total_del
                story.key_snippets = extract_key_snippets_from_commits(
                    story.commit_shas, project_path, max_snippets=3
                )

            # Regenerate Tripartite Codex content
            result = transform_story_for_feed_sync(story, mode="internal")

            # Store structured fields
            story.hook = result.hook
            story.what = result.what
            story.value = result.value
            story.insight = result.insight
            story.show = result.show

            # Internal-specific fields
            if hasattr(result, 'problem') and result.problem:
                story.problem = result.problem
            if hasattr(result, 'how') and result.how:
                story.implementation_details = result.how

            # Legacy fields for backward compatibility
            story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
            story.internal_post = story.public_post
            story.public_show = result.show
            story.internal_show = result.show

            # Update in database
            db.save_story(story, story.project_id)
            refreshed += 1

            if not json_output:
                console.print(f"  [green]✓[/] {story.title[:60]}")

        except Exception as e:
            # Use fallback
            fallback_post = _build_fallback_post(story)
            story.public_post = fallback_post
            story.internal_post = fallback_post
            db.save_story(story, story.project_id)
            failed += 1

            if not json_output:
                console.print(f"  [yellow]![/] {story.title[:60]} (fallback)")

    console.print()

    if json_output:
        print(json.dumps({"refreshed": refreshed, "failed": failed}))
    else:
        print_success(f"Refreshed {refreshed} stories" + (f" ({failed} used fallback)" if failed else ""))


@timeline_app.command("ingest-session")
def timeline_ingest_session(
    file: Path = typer.Option(
        ..., "--file", "-f",
        help="Path to session file (JSONL)",
        exists=True,
        file_okay=True,
        resolve_path=True,
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", "-p",
        help="Project path (default: detected from session cwd)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help="Session source: claude_code, clawdbot (default: auto-detect)",
    ),
    model: str = typer.Option(
        "openai/gpt-4.1-mini", "--model", "-m",
        help="Model for context extraction",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Ingest a completed AI session into the timeline.
    
    Called by SessionEnd hooks to capture context from AI coding sessions.
    
    Examples:
        repr timeline ingest-session --file ~/.claude/projects/.../session.jsonl
        repr timeline ingest-session --file /path/to/session.jsonl --project ~/myproject
    """
    from datetime import timezone
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
    
    # Determine source
    if source is None:
        if ".claude" in str(file):
            source = "claude_code"
        elif ".clawdbot" in str(file):
            source = "clawdbot"
        else:
            # Try both loaders
            source = "claude_code"
    
    # Load session
    if source == "claude_code":
        loader = ClaudeCodeLoader()
    elif source == "clawdbot":
        loader = ClawdbotLoader()
    else:
        print_error(f"Unknown source: {source}")
        raise typer.Exit(1)
    
    session = loader.load_session(file)
    if not session:
        if json_output:
            print(json.dumps({"success": False, "error": "Failed to load session"}))
        else:
            print_error(f"Failed to load session from {file}")
        raise typer.Exit(1)
    
    # Determine project path
    if project is None:
        if session.cwd:
            project = detect_project_root(Path(session.cwd))
        if project is None:
            if json_output:
                print(json.dumps({"success": False, "error": "Could not detect project path"}))
            else:
                print_error("Could not detect project path from session")
                print_info("Specify with --project /path/to/repo")
            raise typer.Exit(1)
    
    project_path = project
    
    # Check if timeline exists
    if not is_initialized(project_path):
        if json_output:
            print(json.dumps({"success": False, "error": f"Timeline not initialized for {project_path}"}))
        else:
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
        raise typer.Exit(1)
    
    # Load existing timeline
    timeline = load_timeline(project_path)
    if not timeline:
        print_error("Failed to load timeline")
        raise typer.Exit(1)
    
    # Check if session already ingested
    for entry in timeline.entries:
        if entry.session_context and entry.session_context.session_id == session.id:
            if json_output:
                print(json.dumps({"success": True, "skipped": True, "reason": "Session already ingested"}))
            else:
                print_info(f"Session {session.id[:8]} already ingested")
            return
    
    # Get API key for extraction
    api_key = None
    byok_config = get_byok_config("openai")
    if byok_config:
        api_key = byok_config.get("api_key")
    
    if not api_key:
        _, litellm_key = get_litellm_config()
        api_key = litellm_key
    
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        if json_output:
            print(json.dumps({"success": False, "error": "No API key for extraction"}))
        else:
            print_error("No API key configured for session extraction")
            print_info("Configure with: repr llm add openai")
        raise typer.Exit(1)
    
    # Extract context from session
    async def _extract():
        extractor = SessionExtractor(api_key=api_key, model=model)
        return await extractor.extract_context(session)
    
    if not json_output:
        with create_spinner() as progress:
            task = progress.add_task("Extracting context...", total=None)
            context = asyncio.run(_extract())
    else:
        context = asyncio.run(_extract())
    
    # Get recent commits to potentially link
    recent_commits = extract_commits_from_git(
        project_path,
        days=1,  # Just last day for linking
        max_commits=50,
    )
    
    # Match session to commits
    if recent_commits:
        matches = match_commits_to_sessions(recent_commits, [session])
        linked_commits = [m.commit_sha for m in matches if m.session_id == session.id]
        context.linked_commits = linked_commits
    
    # Create timeline entry
    entry_type = TimelineEntryType.SESSION
    if context.linked_commits:
        # Find and upgrade matching commit entries to MERGED
        for commit_sha in context.linked_commits:
            for entry in timeline.entries:
                if entry.commit and entry.commit.sha == commit_sha:
                    entry.session_context = context
                    entry.type = TimelineEntryType.MERGED
                    entry_type = None  # Don't create standalone entry
                    break
            if entry_type is None:
                break
    
    # Add standalone session entry if not merged
    if entry_type is not None:
        entry = TimelineEntry(
            timestamp=context.timestamp,
            type=entry_type,
            commit=None,
            session_context=context,
            story=None,
        )
        timeline.add_entry(entry)
    
    # Save timeline
    save_timeline(timeline, project_path)
    
    if json_output:
        print(json.dumps({
            "success": True,
            "session_id": session.id,
            "project": str(project_path),
            "problem": context.problem[:100],
            "linked_commits": context.linked_commits,
            "entry_type": entry_type.value if entry_type else "merged",
        }, indent=2))
    else:
        print_success(f"Session ingested!")
        console.print()
        console.print(f"  Session: {session.id[:8]}")
        console.print(f"  Problem: {context.problem[:60]}...")
        if context.linked_commits:
            console.print(f"  Linked to commits: {', '.join(c[:8] for c in context.linked_commits)}")
        console.print(f"  Entry type: {entry_type.value if entry_type else 'merged'}")


@timeline_app.command("serve")
def timeline_serve(
    port: int = typer.Option(
        3000, "--port", "-p",
        help="Port to serve on",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host",
        help="Host to bind to",
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open",
        help="Auto-open browser (default: enabled)",
    ),
):
    """
    Launch web dashboard for timeline exploration.

    Starts a local web server to browse and search through your
    timeline entries with rich context visualization.

    Works from any directory - reads from central SQLite database.

    Examples:
        repr timeline serve              # localhost:3000, auto-opens browser
        repr timeline serve --port 8080  # custom port
        repr timeline serve --no-open    # don't auto-open browser
    """
    import webbrowser
    from .dashboard import run_server
    from .db import DB_PATH, get_db

    # Check if SQLite database exists and has stories
    if not DB_PATH.exists():
        print_error("No stories database found")
        print_info("Run `repr generate` in a git repository first")
        raise typer.Exit(1)

    db = get_db()
    stats = db.get_stats()
    story_count = stats.get("story_count", 0)
    project_count = stats.get("project_count", 0)

    if story_count == 0:
        print_error("No stories in database")
        print_info("Run `repr generate` to create stories from commits")
        raise typer.Exit(1)

    console.print(f"Starting dashboard with [bold]{story_count} stories[/] from [bold]{project_count} repositories[/]")

    url = f"http://{host}:{port}"
    
    print_header()
    console.print(f"  URL: [bold blue]{url}[/]")
    console.print()
    console.print("[dim]Press Ctrl+C to stop[/]")
    console.print()
    
    if open_browser:
        webbrowser.open(url)
    
    try:
        run_server(port, host)
    except KeyboardInterrupt:
        console.print()
        print_info("Server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            print_error(f"Port {port} is already in use")
            print_info(f"Try: repr timeline serve --port {port + 1}")
        else:
            raise


# =============================================================================
# GIT WORKFLOW COMMANDS (add, commit, push)
# =============================================================================

# File-based cache for commit message (persists between commands)
_COMMIT_MSG_CACHE_FILE = Path.home() / ".repr" / ".commit_message_cache"


COMMIT_MESSAGE_SYSTEM = """You generate git commit messages and branch names. Given staged changes, output JSON with:

{
  "branch": "<type>/<short-description>",
  "message": "<type>: <description>"
}

Types: feat, fix, refactor, docs, style, test, chore

Rules:
- Branch: lowercase, hyphens, no spaces (e.g., feat/add-user-auth)
- Message: under 72 chars, imperative mood, no period at end

Output only valid JSON."""

COMMIT_MESSAGE_USER = """Generate branch name and commit message for these staged changes:

{changes}"""


def _get_cached_commit_info() -> Optional[dict]:
    """Get cached commit info (branch + message) if it exists."""
    if _COMMIT_MSG_CACHE_FILE.exists():
        try:
            return json.loads(_COMMIT_MSG_CACHE_FILE.read_text())
        except Exception:
            return None
    return None


def _set_cached_commit_info(branch: str, message: str):
    """Cache the commit info."""
    _COMMIT_MSG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COMMIT_MSG_CACHE_FILE.write_text(json.dumps({"branch": branch, "message": message}))


def _clear_cached_commit_info():
    """Clear the cached commit info."""
    if _COMMIT_MSG_CACHE_FILE.exists():
        _COMMIT_MSG_CACHE_FILE.unlink()


@app.command("clear")
def clear_cache():
    """
    Clear cached branch name and commit message.

    Examples:
        repr clear
    """
    cached = _get_cached_commit_info()
    if cached:
        console.print(f"[{BRAND_MUTED}]Clearing cached:[/]")
        if cached.get("branch"):
            console.print(f"  Branch: {cached['branch']}")
        if cached.get("message"):
            console.print(f"  Message: {cached['message']}")
        _clear_cached_commit_info()
        print_success("Cache cleared")
    else:
        print_info("No cached branch/message")


@app.command("add")
def add_files(
    pattern: str = typer.Argument(..., help="File pattern to stage (glob pattern)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force add ignored files"),
):
    """
    Stage files matching pattern.

    Run `repr commit` to generate a message and commit.

    Examples:
        repr add cli              # Stage files containing "cli"
        repr add .py              # Stage files containing ".py"
        repr add .                # Stage all
        repr add cli -f           # Force add ignored files
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Special case: "." means all
    if pattern == ".":
        try:
            cmd = ["git", "add", "."]
            if force:
                cmd.insert(2, "-f")
            result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print_error(f"Failed to stage files: {result.stderr}")
                raise typer.Exit(1)
        except Exception as e:
            print_error(f"Failed to stage files: {e}")
            raise typer.Exit(1)
    else:
        # Grep-style match: find files containing pattern
        # Get modified/untracked files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if status_result.returncode != 0:
            print_error(f"Failed to get status: {status_result.stderr}")
            raise typer.Exit(1)

        # Parse status output and filter by pattern (grep-style regex)
        import re
        matching_files = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to literal match if invalid regex
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for line in status_result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: XY filename or XY orig -> renamed (XY is 2 chars, then optional space)
            file_path = line[2:].lstrip().split(" -> ")[-1].strip()
            if regex.search(file_path):
                matching_files.append(file_path)

        if not matching_files:
            print_warning(f"No changed files matching '{pattern}'")
            raise typer.Exit(0)

        # Stage matching files
        try:
            cmd = ["git", "add"]
            if force:
                cmd.append("-f")
            cmd.extend(matching_files)
            result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print_error(f"Failed to stage files: {result.stderr}")
                raise typer.Exit(1)
        except Exception as e:
            print_error(f"Failed to stage files: {e}")
            raise typer.Exit(1)

    staged = get_staged_changes(repo)
    if not staged:
        print_warning("No files matched pattern or nothing to stage")
        raise typer.Exit(0)

    # Clear cached branch/message so next commit generates fresh
    _clear_cached_commit_info()

    # Show staged files
    console.print(f"[bold]Staged {len(staged)} files[/]")
    for f in staged:
        type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
        stats = ""
        if f.insertions or f.deletions:
            stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
        console.print(f"  {type_icon} {f.path}{stats}")
    console.print()

    # Suggest branch if on main/master, otherwise commit
    try:
        branch_name = repo.active_branch.name
        if branch_name in ("main", "master"):
            print_info("Run `repr branch` to create a feature branch")
        else:
            print_info("Run `repr commit` to generate message and commit")
    except Exception:
        print_info("Run `repr commit` to generate message and commit")


@app.command("branch")
def create_branch(
    name: Optional[str] = typer.Argument(None, help="Branch name (optional, AI generates if omitted)"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate branch name"),
):
    """
    Create and switch to a new branch.

    If no name given, generates one from staged or unpushed changes.

    Examples:
        repr branch                    # AI generates name
        repr branch feat/my-feature    # Use explicit name
        repr branch -r                 # Regenerate name
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes, get_unpushed_commits, format_file_changes, format_commit_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    branch_name = name

    if not branch_name:
        # Check cache first
        cached = _get_cached_commit_info()
        if cached and cached.get("branch") and not regenerate:
            branch_name = cached["branch"]
            console.print(f"[{BRAND_MUTED}](cached)[/]")
        else:
            # Generate from staged or unpushed changes
            staged = get_staged_changes(repo)
            unpushed = get_unpushed_commits(repo)

            if not staged and not unpushed:
                print_error("No staged or unpushed changes to generate branch name from")
                print_info("Run `repr add <pattern>` first, or provide a name")
                raise typer.Exit(1)

            from .openai_analysis import get_openai_client

            client = get_openai_client()
            if not client:
                print_error("LLM not configured. Run `repr llm setup` first, or provide a name")
                raise typer.Exit(1)

            # Build context from staged and/or unpushed
            changes_str = ""
            if staged:
                changes_str += "Staged changes:\n" + format_file_changes(staged) + "\n\n"
            if unpushed:
                changes_str += "Unpushed commits:\n" + format_commit_changes(unpushed)

            prompt = COMMIT_MESSAGE_USER.format(changes=changes_str)

            with create_spinner("Generating branch name..."):
                response = asyncio.run(client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": COMMIT_MESSAGE_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                ))
                data = json.loads(response.choices[0].message.content)
                branch_name = data.get("branch", "")
                commit_msg = data.get("message", "")

            # Cache both
            _set_cached_commit_info(branch_name, commit_msg)

    console.print(f"[bold]Branch:[/] {branch_name}")

    try:
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if "already exists" in result.stderr:
                # Switch to existing branch
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print_success(f"Switched to {branch_name}")
                    return
            print_error(f"Failed: {result.stderr}")
            raise typer.Exit(1)

        print_success(f"Created and switched to {branch_name}")

        # Check if there are staged changes and suggest next step
        from .change_synthesis import get_staged_changes
        staged = get_staged_changes(repo)
        if staged:
            print_info("Run `repr commit` to commit your staged changes")

    except Exception as e:
        print_error(f"Failed: {e}")
        raise typer.Exit(1)


@app.command("commit")
def commit_staged(
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Custom message (skip AI)"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate message"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation on main/master"),
):
    """
    Generate commit message and commit staged changes.

    Examples:
        repr commit                    # Generate and commit
        repr commit -m "fix: typo"     # Custom message
        repr commit -r                 # Regenerate message
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes, format_file_changes
    from .config import get_config_value, set_config_value

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Check if on main/master
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo.working_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if current_branch in ("main", "master") and not yes:
        allow_main = get_config_value("allow_commit_to_main")
        if allow_main is None:
            # Ask user
            print_warning(f"You're about to commit directly to {current_branch}")
            console.print()
            response = typer.prompt(
                "Allow commits to main/master? [y]es / [n]o / [a]lways / [never]",
                default="n",
            ).lower()

            if response in ("a", "always"):
                set_config_value("allow_commit_to_main", True)
                console.print(f"[{BRAND_MUTED}]Preference saved. Use `repr config set allow_commit_to_main false` to reset.[/]")
            elif response in ("never",):
                set_config_value("allow_commit_to_main", False)
                console.print(f"[{BRAND_MUTED}]Preference saved. Use `repr config set allow_commit_to_main true` to reset.[/]")
                print_info("Create a branch first: repr branch")
                raise typer.Exit(0)
            elif response not in ("y", "yes"):
                print_info("Create a branch first: repr branch")
                raise typer.Exit(0)
        elif allow_main is False:
            print_warning(f"Commits to {current_branch} are disabled")
            print_info("Create a branch first: repr branch")
            print_info("Or use: repr config set allow_commit_to_main true")
            raise typer.Exit(0)

    staged = get_staged_changes(repo)
    if not staged:
        print_warning("Nothing staged to commit")
        print_info("Run `repr add <pattern>` first")
        raise typer.Exit(0)

    # Show staged files
    console.print(f"[bold]Staged {len(staged)} files[/]")
    for f in staged:
        type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
        stats = ""
        if f.insertions or f.deletions:
            stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
        console.print(f"  {type_icon} {f.path}{stats}")
    console.print()

    # Get commit message
    commit_msg = None

    if message:
        commit_msg = message
    else:
        # Check cache
        cached = _get_cached_commit_info()
        if cached and cached.get("message") and not regenerate:
            commit_msg = cached["message"]
            console.print(f"[{BRAND_MUTED}](cached)[/]")
        else:
            # Generate with LLM
            from .openai_analysis import get_openai_client

            client = get_openai_client()
            if not client:
                print_error("LLM not configured. Run `repr llm setup` first, or use -m")
                raise typer.Exit(1)

            changes_str = format_file_changes(staged)
            prompt = COMMIT_MESSAGE_USER.format(changes=changes_str)

            with create_spinner("Generating commit message..."):
                response = asyncio.run(client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": COMMIT_MESSAGE_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                ))
                data = json.loads(response.choices[0].message.content)
                branch_name = data.get("branch", "")
                commit_msg = data.get("message", "")

            _set_cached_commit_info(branch_name, commit_msg)

    console.print(f"[bold]Message:[/] {commit_msg}")
    console.print()

    try:
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_error(f"Commit failed: {result.stderr}")
            raise typer.Exit(1)

        _clear_cached_commit_info()
        print_success("Committed")

        sha_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if sha_result.returncode == 0:
            console.print(f"  [{BRAND_MUTED}]{sha_result.stdout.strip()}[/]")

    except Exception as e:
        print_error(f"Commit failed: {e}")
        raise typer.Exit(1)


@app.command("push")
def push_commits():
    """
    Push commits to remote.

    Examples:
        repr push
    """
    import subprocess
    from .change_synthesis import get_repo

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Check for unpushed commits
    try:
        result = subprocess.run(
            ["git", "log", "@{u}..", "--oneline"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # No upstream, just push
            pass
        elif not result.stdout.strip():
            print_info("Nothing to push")
            raise typer.Exit(0)
        else:
            commits = result.stdout.strip().split("\n")
            console.print(f"[bold]Pushing {len(commits)} commits[/]")
            for c in commits[:5]:
                console.print(f"  [{BRAND_MUTED}]{c}[/]")
            if len(commits) > 5:
                console.print(f"  [{BRAND_MUTED}]... +{len(commits) - 5} more[/]")
            console.print()
    except Exception:
        pass

    try:
        with create_spinner("Pushing..."):
            result = subprocess.run(
                ["git", "push"],
                cwd=repo.working_dir,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            if "no upstream branch" in result.stderr:
                # Try push with -u
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                with create_spinner(f"Setting upstream and pushing {branch}..."):
                    result = subprocess.run(
                        ["git", "push", "-u", "origin", branch],
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                    )
                if result.returncode != 0:
                    print_error(f"Push failed: {result.stderr}")
                    raise typer.Exit(1)
            else:
                print_error(f"Push failed: {result.stderr}")
                raise typer.Exit(1)

        print_success("Pushed")

    except Exception as e:
        print_error(f"Push failed: {e}")
        raise typer.Exit(1)


# Entry point
if __name__ == "__main__":
    app()
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
from typing import Optional, List, Dict, Callable
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
    BatchProgress,
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
cron_app = typer.Typer(help="Scheduled story generation (every 4h)")
llm_app = typer.Typer(help="Configure LLM (local/cloud/BYOK)")
privacy_app = typer.Typer(help="Privacy audit and controls")
config_app = typer.Typer(help="View and modify configuration")
data_app = typer.Typer(help="Backup, restore, and manage data")
profile_app = typer.Typer(help="View and manage profile")
mcp_app = typer.Typer(help="MCP server for AI agent integration")
timeline_app = typer.Typer(help="Unified timeline of commits + AI sessions")

app.add_typer(hooks_app, name="hooks")
app.add_typer(cron_app, name="cron")
app.add_typer(llm_app, name="llm")
app.add_typer(privacy_app, name="privacy")
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(profile_app, name="profile")
app.add_typer(mcp_app, name="mcp")
app.add_typer(timeline_app, name="timeline")


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

    # Ask about automatic story generation
    console.print()
    console.print("[bold]Automatic Story Generation[/]")
    console.print()
    console.print("How should repr generate stories from your commits?")
    console.print()
    console.print(f"  [bold]1.[/] Scheduled (recommended) - Every 4 hours via cron")
    console.print(f"     [{BRAND_MUTED}]Predictable, batches work, never interrupts[/]")
    console.print()
    console.print(f"  [bold]2.[/] On commit - After every 5 commits via git hook")
    console.print(f"     [{BRAND_MUTED}]Real-time, but needs LLM running during commits[/]")
    console.print()
    console.print(f"  [bold]3.[/] Manual only - Run `repr generate` yourself")
    console.print(f"     [{BRAND_MUTED}]Full control, no automation[/]")
    console.print()

    schedule_choice = Prompt.ask(
        "Choose",
        choices=["1", "2", "3"],
        default="1",
    )

    from .hooks import install_hook
    from .cron import install_cron

    if schedule_choice == "1":
        # Scheduled via cron
        result = install_cron(interval_hours=4, min_commits=3)
        if result["success"]:
            print_success("Cron job installed (every 4h)")
            # Install hooks for queue tracking (but disable auto-generate)
            config = load_config()
            config["generation"]["auto_generate_on_hook"] = False
            save_config(config)
            for repo in repos:
                install_hook(Path(repo.path))
                set_repo_hook_status(str(repo.path), True)
        else:
            print_warning(f"Could not install cron: {result['message']}")
            print_info("You can set it up later with `repr cron install`")

    elif schedule_choice == "2":
        # On-commit via hooks
        config = load_config()
        config["generation"]["auto_generate_on_hook"] = True
        save_config(config)
        for repo in repos:
            install_hook(Path(repo.path))
            set_repo_hook_status(str(repo.path), True)
        print_success(f"Hooks installed in {len(repos)} repos (generates after 5 commits)")

    else:
        # Manual only - disable auto-generation
        config = load_config()
        config["generation"]["auto_generate_on_hook"] = False
        save_config(config)
        print_info("Manual mode - run `repr generate` when you want stories")

    console.print()
    print_next_steps([
        "repr week               See what you worked on this week",
        "repr generate --local   Save stories permanently",
        "repr login              Unlock cloud sync and publishing",
    ])


# =============================================================================
# GENERATE
# =============================================================================

# Technology detection from file extensions
_TECH_EXTENSIONS = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".scala": "Scala",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".graphql": "GraphQL",
    ".prisma": "Prisma",
}

# Special file name patterns that indicate technologies
_TECH_FILES = {
    "Dockerfile": "Docker",
    "docker-compose": "Docker",
    "package.json": "Node.js",
    "tsconfig.json": "TypeScript",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    ".eslintrc": "ESLint",
    "tailwind.config": "Tailwind CSS",
    "next.config": "Next.js",
    "vite.config": "Vite",
    "webpack.config": "Webpack",
}


def _detect_technologies_from_files(files: list[str]) -> list[str]:
    """
    Detect technologies from file paths/extensions.

    Args:
        files: List of file paths

    Returns:
        Sorted list of detected technology names
    """
    tech = set()

    for f in files:
        # Handle files as either dict with 'path' or string
        if isinstance(f, dict):
            f = f.get("path", "")

        # Check extensions
        for ext, name in _TECH_EXTENSIONS.items():
            if f.endswith(ext):
                tech.add(name)
                break

        # Check special file names
        for fname, name in _TECH_FILES.items():
            if fname in f:
                tech.add(name)

    return sorted(tech)


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
    import asyncio
    from .timeline import extract_commits_from_git, detect_project_root
    from .story_synthesis import synthesize_stories
    from .db import get_db
    from .privacy import check_cloud_permission, log_cloud_operation

    def synthesize_stories_sync(*args, **kwargs):
        return asyncio.run(synthesize_stories(*args, **kwargs))
    
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
        # Check config for default mode
        llm_config = get_llm_config()
        default_mode = llm_config.get("default", "local")

        if default_mode == "local":
            local = True
        elif default_mode == "cloud" and is_authenticated() and is_cloud_allowed():
            cloud = True
        else:
            # Fallback: local if not signed in or cloud not allowed
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
    
    all_generated_stories = []

    for repo_path in repo_paths:
        if not json_output:
            console.print(f"[bold]{repo_path.name}[/]")
            
        # Determine commit range
        repo_commits = []
        if commits:
             # Specific SHA list filtering
             repo_commits = extract_commits_from_git(repo_path, days=90)
             target_shas = [s.strip() for s in commits.split(",")]
             repo_commits = [c for c in repo_commits if any(c.sha.startswith(t) for t in target_shas)]
        elif since_date:
             # Parse date (rough approximation)
             filter_days = 30
             if "week" in since_date: filter_days = 14
             if "month" in since_date: filter_days = 30
             repo_commits = extract_commits_from_git(repo_path, days=filter_days)
        else:
             filter_days = days if days else 90
             repo_commits = extract_commits_from_git(repo_path, days=filter_days)
        
        if not repo_commits:
            if not json_output:
                console.print(f"  No matching commits found")
            continue
            
        if not json_output:
             console.print(f"  Analyzing {len(repo_commits)} commits...")

        # Progress callback
        def progress(current: int, total: int) -> None:
             if not json_output:
                 console.print(f"  Batch {current}/{total}")

        # Determine model based on mode
        if local:
            llm_config = get_llm_config()
            model = llm_config.get("local_model") or "llama3.2"
        else:
            model = None  # Use default cloud model

        try:
            # Run synthesis sync
            stories, index = synthesize_stories_sync(
                commits=repo_commits,
                model=model,
                batch_size=batch_size,
                progress_callback=progress,
            )

            # Generate public/internal posts for each story
            if stories and not dry_run:
                from .story_synthesis import transform_story_for_feed_sync, _build_fallback_post

                if not json_output:
                    console.print(f"  Generating build log posts...")

                for story in stories:
                    try:
                        # Generate Tripartite Codex content (internal includes all fields)
                        result = transform_story_for_feed_sync(story, mode="internal")

                        # Store structured fields
                        story.hook = result.hook
                        story.what = result.what
                        story.value = result.value
                        story.insight = result.insight
                        story.show = result.show

                        # Internal-specific fields
                        if hasattr(result, 'problem') and result.problem:
                            story.problem = result.problem
                        if hasattr(result, 'how') and result.how:
                            story.implementation_details = result.how

                        # Legacy fields for backward compatibility
                        story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
                        story.internal_post = story.public_post
                        story.public_show = result.show
                        story.internal_show = result.show
                    except Exception as e:
                        # Fallback: build from story data
                        from .story_synthesis import _build_fallback_codex
                        result = _build_fallback_codex(story, "internal")
                        story.hook = result.hook
                        story.what = result.what
                        story.value = result.value
                        story.insight = result.insight
                        story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
                        story.internal_post = story.public_post

            # Save to SQLite
            if not dry_run and stories:
                db = get_db()
                project_id = db.register_project(repo_path, repo_path.name)

                for story in stories:
                    db.save_story(story, project_id)

                # Update freshness with latest commit
                if repo_commits:
                    latest_commit = repo_commits[0]  # Already sorted by date desc
                    db.update_freshness(
                        project_id,
                        latest_commit.sha,
                        latest_commit.timestamp,
                    )

                if not json_output:
                    print_success(f"Saved {len(stories)} stories to SQLite")
            else:
                 if not json_output:
                     print_info("Dry run - not saved")

            all_generated_stories.extend(stories)

        except Exception as e:
            if not json_output:
                print_error(f"Failed to generate for {repo_path.name}: {e}")

    if json_output:
        print(json.dumps({
            "success": True, 
            "stories_count": len(all_generated_stories),
            "stories": [s.model_dump(mode="json") for s in all_generated_stories]
        }, default=str)) 
    elif all_generated_stories:
        console.print()
        print_success(f"Generated {len(all_generated_stories)} stories")
        print_info("Run `repr timeline serve` to view")


async def _generate_stories_async(
    commits: list[dict],
    repo_info,
    batch_size: int,
    local: bool,
    template: str = "resume",
    custom_prompt: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """Generate stories from commits using LLM (async implementation).
    
    Args:
        progress_callback: Optional callback with signature (batch_num, total_batches, status)
            where status is 'processing' or 'complete'
    """
    from .openai_analysis import get_openai_client, extract_commit_batch
    from .templates import build_generation_prompt, StoryOutput
    
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
            # Report progress - starting this batch
            if progress_callback:
                progress_callback(i + 1, len(batches), "processing")
            
            try:
                # Build prompt with template
                system_prompt, user_prompt = build_generation_prompt(
                    template_name=template,
                    repo_name=repo_info.name,
                    commits=batch,
                    custom_prompt=custom_prompt,
                )
                
                # Extract story from batch using structured output
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
                
                # Handle structured output - now returns list[StoryOutput]
                story_outputs: list[StoryOutput] = []
                if isinstance(result, list):
                    story_outputs = result
                elif isinstance(result, StoryOutput):
                    story_outputs = [result]
                else:
                    # Fallback for string response
                    content = result
                    if not content or content.startswith("[Batch"):
                        # Report progress - batch complete (even if empty)
                        if progress_callback:
                            progress_callback(i + 1, len(batches), "complete")
                        continue
                    lines = [l.strip() for l in content.split("\n") if l.strip()]
                    summary = lines[0] if lines else "Story"
                    summary = summary.lstrip("#-•* ").strip()
                    story_outputs = [StoryOutput(summary=summary, content=content)]

                # Build shared metadata for all stories from this batch
                commit_shas = [c["full_sha"] for c in batch]
                first_date = min(c["date"] for c in batch)
                last_date = max(c["date"] for c in batch)
                total_files = sum(len(c.get("files", [])) for c in batch)
                total_adds = sum(c.get("insertions", 0) for c in batch)
                total_dels = sum(c.get("deletions", 0) for c in batch)

                # Save each story from this batch
                for story_output in story_outputs:
                    content = story_output.content
                    summary = story_output.summary

                    if not content or content.startswith("[Batch"):
                        continue

                    # Get technologies from LLM output, fallback to file-based detection
                    technologies = story_output.technologies or []
                    if not technologies:
                        # Detect from files in this batch
                        all_files = []
                        for c in batch:
                            all_files.extend(c.get("files", []))
                        technologies = _detect_technologies_from_files(all_files)

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
                        # Technologies
                        "technologies": technologies,
                        # Categories
                        "category": story_output.category,
                        "scope": story_output.scope,
                        "stack": story_output.stack,
                        "initiative": story_output.initiative,
                        "complexity": story_output.complexity,
                    }

                    # Save story
                    story_id = save_story(content, metadata)
                    metadata["id"] = story_id
                    stories.append(metadata)
                
                # Report progress - batch complete
                if progress_callback:
                    progress_callback(i + 1, len(batches), "complete")
                
            except Exception as e:
                # Report progress even on failure
                if progress_callback:
                    progress_callback(i + 1, len(batches), "complete")
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
    custom_prompt: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """Generate stories from commits using LLM."""
    return asyncio.run(_generate_stories_async(
        commits=commits,
        repo_info=repo_info,
        batch_size=batch_size,
        local=local,
        template=template,
        custom_prompt=custom_prompt,
        progress_callback=progress_callback,
    ))


# =============================================================================
# STORIES MANAGEMENT
# =============================================================================

@app.command()
def stories(
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repository"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category (feature, bugfix, refactor, perf, infra, docs, test, chore)"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Filter by scope (user-facing, internal, platform, ops)"),
    stack: Optional[str] = typer.Option(None, "--stack", help="Filter by stack (frontend, backend, database, infra, mobile, fullstack)"),
    needs_review: bool = typer.Option(False, "--needs-review", help="Show only stories needing review"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List all stories.
    
    Example:
        repr stories
        repr stories --repo myproject
        repr stories --category feature
        repr stories --scope user-facing
        repr stories --stack backend
        repr stories --needs-review
    """
    story_list = list_stories(repo_name=repo, needs_review=needs_review)
    
    # Apply category filters (local filtering since storage doesn't support these yet)
    if category:
        story_list = [s for s in story_list if s.get("category") == category]
    if scope:
        story_list = [s for s in story_list if s.get("scope") == scope]
    if stack:
        story_list = [s for s in story_list if s.get("stack") == stack]
    
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
            
            # Category badge
            cat = story.get("category", "")
            cat_badge = f"[{BRAND_MUTED}][{cat}][/] " if cat else ""
            
            console.print(f"  {status} {cat_badge}{summary} [{BRAND_MUTED}]• {created}[/]")
        console.print()

    if len(story_list) > 20:
        console.print(f"[{BRAND_MUTED}]... and {len(story_list) - 20} more[/]")


@app.command()
def story(
    action: str = typer.Argument(..., help="Action: view, edit, delete, hide, feature, regenerate"),
    story_id: Optional[str] = typer.Argument(None, help="Story ID (ULID)"),
    all_stories: bool = typer.Option(False, "--all", help="Apply to all stories (for delete)"),
):
    """
    Manage a single story.
    
    Examples:
        repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV
        repr story delete 01ARYZ6S41TSV4RRFFQ69G5FAV
        repr story delete --all
    """
    # Handle --all flag for delete
    if all_stories:
        if action != "delete":
            print_error("--all flag only works with 'delete' action")
            raise typer.Exit(1)
        
        story_list = list_stories()
        if not story_list:
            print_info("No stories to delete")
            raise typer.Exit()
        
        console.print(f"This will delete [bold]{len(story_list)}[/] stories.")
        if confirm("Delete all stories?"):
            deleted = 0
            for s in story_list:
                try:
                    delete_story(s["id"])
                    deleted += 1
                except Exception:
                    pass
            print_success(f"Deleted {deleted} stories")
        else:
            print_info("Cancelled")
        raise typer.Exit()
    
    # Require story_id for single-story operations
    if not story_id:
        print_error("Story ID required (or use --all for delete)")
        raise typer.Exit(1)
    
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
        # Show categories if present
        cat = metadata.get("category")
        scope = metadata.get("scope")
        stack = metadata.get("stack")
        initiative = metadata.get("initiative")
        complexity = metadata.get("complexity")
        if cat or scope or stack:
            cats = [c for c in [cat, scope, stack, initiative, complexity] if c]
            console.print(f"[{BRAND_MUTED}]Categories: {', '.join(cats)}[/]")
    
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
    
    # Build batch payload
    from .api import push_stories_batch
    
    stories_payload = []
    for s in to_push:
        content, meta = load_story(s["id"])
        # Use local story ID as client_id for sync
        payload = {**meta, "content": content, "client_id": s["id"]}
        stories_payload.append(payload)
    
    # Push all stories in a single batch request
    try:
        result = asyncio.run(push_stories_batch(stories_payload))
        pushed = result.get("pushed", 0)
        results = result.get("results", [])
        
        # Mark successful stories as pushed and display results
        for i, story_result in enumerate(results):
            story_id_local = to_push[i]["id"]
            summary = to_push[i].get("summary", story_id_local)[:50]
            
            if story_result.get("success"):
                mark_story_pushed(story_id_local)
                console.print(f"  [{BRAND_SUCCESS}]✓[/] {summary}")
            else:
                error_msg = story_result.get("error", "Unknown error")
                console.print(f"  [{BRAND_ERROR}]✗[/] {summary}: {error_msg}")
        
    except (APIError, AuthError) as e:
        print_error(f"Batch push failed: {e}")
        raise typer.Exit(1)
    
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
                    payload = {**meta, "content": content, "client_id": s["id"]}
                    asyncio.run(api_push_story(payload))
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
# CRON SCHEDULING
# =============================================================================

@cron_app.command("install")
def cron_install(
    interval: int = typer.Option(4, "--interval", "-i", help="Hours between runs (default: 4)"),
    min_commits: int = typer.Option(3, "--min-commits", "-m", help="Minimum commits to trigger generation"),
):
    """
    Install cron job for automatic story generation.

    Runs every 4 hours by default, only generating if there are
    enough commits in the queue.

    Example:
        repr cron install
        repr cron install --interval 6 --min-commits 5
    """
    from .cron import install_cron

    result = install_cron(interval, min_commits)

    if result["success"]:
        if result["already_installed"]:
            print_success(result["message"])
        else:
            print_success(result["message"])
            console.print()
            console.print(f"[{BRAND_MUTED}]Stories will generate every {interval}h when queue has ≥{min_commits} commits[/]")
            console.print(f"[{BRAND_MUTED}]Logs: ~/.repr/logs/cron.log[/]")
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("remove")
def cron_remove():
    """
    Remove cron job for story generation.

    Example:
        repr cron remove
    """
    from .cron import remove_cron

    result = remove_cron()

    if result["success"]:
        print_success(result["message"])
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("pause")
def cron_pause():
    """
    Pause cron job without removing it.

    Example:
        repr cron pause
    """
    from .cron import pause_cron

    result = pause_cron()

    if result["success"]:
        print_success(result["message"])
        console.print(f"[{BRAND_MUTED}]Use `repr cron resume` to re-enable[/]")
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("resume")
def cron_resume():
    """
    Resume paused cron job.

    Example:
        repr cron resume
    """
    from .cron import resume_cron

    result = resume_cron()

    if result["success"]:
        print_success(result["message"])
    else:
        print_error(result["message"])
        raise typer.Exit(1)


@cron_app.command("status")
def cron_status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show cron job status.

    Example:
        repr cron status
    """
    from .cron import get_cron_status

    status = get_cron_status()

    if json_output:
        print(json.dumps(status, indent=2))
        return

    console.print("[bold]Cron Status[/]")
    console.print()

    if not status["installed"]:
        console.print(f"[{BRAND_MUTED}]○[/] Not installed")
        console.print()
        console.print(f"[{BRAND_MUTED}]Run `repr cron install` to enable scheduled generation[/]")
        return

    if status["paused"]:
        console.print(f"[{BRAND_WARNING}]⏸[/] Paused")
        console.print(f"  [{BRAND_MUTED}]Interval: every {status['interval_hours']}h[/]")
        console.print()
        console.print(f"[{BRAND_MUTED}]Run `repr cron resume` to re-enable[/]")
    else:
        console.print(f"[{BRAND_SUCCESS}]✓[/] Active")
        console.print(f"  [{BRAND_MUTED}]Interval: every {status['interval_hours']}h[/]")
        console.print(f"  [{BRAND_MUTED}]Logs: ~/.repr/logs/cron.log[/]")


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


@data_app.command("migrate-db")
def data_migrate_db(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be migrated"),
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Migrate specific project"),
):
    """
    Migrate store.json files to central SQLite database.

    This command imports existing .repr/store.json files into the central
    SQLite database at ~/.repr/stories.db for faster queries.

    Example:
        repr data migrate-db              # Migrate all tracked repos
        repr data migrate-db --dry-run    # Preview migration
        repr data migrate-db -p /path/to/repo
    """
    from .storage import migrate_stores_to_db, get_db_stats

    project_paths = [project] if project else None

    with create_spinner("Migrating stories to SQLite...") as progress:
        task = progress.add_task("migrating", total=None)

        if dry_run:
            console.print("[bold]Dry run mode - no changes will be made[/]\n")

        stats = migrate_stores_to_db(project_paths=project_paths, dry_run=dry_run)

        progress.update(task, completed=True)

    console.print()
    console.print(f"Projects scanned: {stats['projects_scanned']}")
    console.print(f"Projects migrated: {stats['projects_migrated']}")
    console.print(f"Stories imported: {stats['stories_imported']}")

    if stats['errors']:
        console.print()
        print_warning(f"{len(stats['errors'])} errors:")
        for error in stats['errors'][:5]:
            console.print(f"  • {error}")
        if len(stats['errors']) > 5:
            console.print(f"  ... and {len(stats['errors']) - 5} more")

    if not dry_run and stats['stories_imported'] > 0:
        console.print()
        db_stats = get_db_stats()
        console.print(f"Database: {db_stats['db_path']}")
        console.print(f"Total stories: {db_stats['story_count']}")
        console.print(f"Database size: {format_bytes(db_stats['db_size_bytes'])}")


@data_app.command("db-stats")
def data_db_stats():
    """
    Show SQLite database statistics.

    Example:
        repr data db-stats
    """
    from .storage import get_db_stats
    from .db import DB_PATH

    if not DB_PATH.exists():
        print_info("No SQLite database yet.")
        print_info("Run `repr data migrate-db` to create one.")
        return

    stats = get_db_stats()

    console.print("[bold]SQLite Database Stats[/]")
    console.print()
    console.print(f"Path: {stats['db_path']}")
    console.print(f"Size: {format_bytes(stats['db_size_bytes'])}")
    console.print()
    console.print(f"Stories: {stats['story_count']}")
    console.print(f"Projects: {stats['project_count']}")
    console.print(f"Unique files: {stats['unique_files']}")
    console.print(f"Unique commits: {stats['unique_commits']}")

    if stats['categories']:
        console.print()
        console.print("[bold]By Category:[/]")
        for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
            console.print(f"  {cat}: {count}")


@data_app.command("clear")
def data_clear(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Clear all stories from database and storage.

    This permanently deletes:
    - All stories from the SQLite database
    - All story files from ~/.repr/stories/

    Projects registry and config are preserved.

    Example:
        repr data clear           # With confirmation
        repr data clear --force   # Skip confirmation
    """
    from .db import DB_PATH
    from .storage import STORIES_DIR
    import shutil

    # Check what exists
    db_exists = DB_PATH.exists()
    stories_dir_exists = STORIES_DIR.exists()

    if not db_exists and not stories_dir_exists:
        print_info("Nothing to clear - no database or stories found.")
        return

    # Count what we're about to delete
    story_count = 0
    db_size = 0
    stories_file_count = 0

    if db_exists:
        from .storage import get_db_stats
        try:
            stats = get_db_stats()
            story_count = stats.get('story_count', 0)
            db_size = stats.get('db_size_bytes', 0)
        except Exception:
            db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    if stories_dir_exists:
        stories_file_count = len(list(STORIES_DIR.glob("*")))

    # Show what will be deleted
    console.print("[bold red]This will permanently delete:[/]")
    console.print()
    if db_exists:
        console.print(f"  • Database: {DB_PATH}")
        console.print(f"    {story_count} stories, {format_bytes(db_size)}")
    if stories_dir_exists and stories_file_count > 0:
        console.print(f"  • Story files: {STORIES_DIR}")
        console.print(f"    {stories_file_count} files")
    console.print()
    console.print("[dim]Projects registry and config will be preserved.[/]")
    console.print()

    if not force:
        if not confirm("Are you sure you want to delete all stories?"):
            print_info("Cancelled")
            raise typer.Exit()

    # Delete database
    if db_exists:
        try:
            # Also delete WAL and SHM files if they exist
            DB_PATH.unlink()
            wal_path = DB_PATH.with_suffix(".db-wal")
            shm_path = DB_PATH.with_suffix(".db-shm")
            if wal_path.exists():
                wal_path.unlink()
            if shm_path.exists():
                shm_path.unlink()
        except Exception as e:
            print_error(f"Failed to delete database: {e}")
            raise typer.Exit(1)

    # Delete stories directory contents (but keep the directory)
    if stories_dir_exists:
        try:
            shutil.rmtree(STORIES_DIR)
            STORIES_DIR.mkdir(exist_ok=True)
        except Exception as e:
            print_error(f"Failed to clear stories directory: {e}")
            raise typer.Exit(1)

    print_success("All stories cleared")
    if db_exists:
        console.print(f"  Deleted: {story_count} stories from database")
    if stories_file_count > 0:
        console.print(f"  Deleted: {stories_file_count} story files")


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
def changes(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to repository (default: current directory)",
        exists=True,
        resolve_path=True,
    ),
    explain: bool = typer.Option(False, "--explain", "-e", help="Use LLM to explain changes"),
    compact: bool = typer.Option(False, "--compact", "-c", help="Compact output (no diff previews)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show file changes across git states with diff details.

    Displays changes in three states:
    - Unstaged: Tracked files modified but not staged (with diff preview)
    - Staged: Changes ready to commit (with diff preview)
    - Unpushed: Commits not yet pushed to remote

    Example:
        repr changes              # Show changes with diffs
        repr changes --compact    # Just file names
        repr changes --explain    # LLM summary
        repr changes --json
    """
    from .change_synthesis import (
        get_change_report,
        ChangeState,
        explain_group,
    )

    target_path = path or Path.cwd()
    report = get_change_report(target_path)

    if not report:
        print_error(f"Not a git repository: {target_path}")
        raise typer.Exit(1)

    if json_output:
        data = {
            "repo_path": str(report.repo_path),
            "timestamp": report.timestamp.isoformat(),
            "unstaged": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                }
                for f in report.unstaged
            ],
            "staged": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                }
                for f in report.staged
            ],
            "unpushed": [
                {
                    "sha": c.sha,
                    "message": c.message,
                    "author": c.author,
                    "timestamp": c.timestamp.isoformat(),
                    "files": [{"path": f.path, "change_type": f.change_type} for f in c.files],
                }
                for c in report.unpushed
            ],
        }
        if report.summary:
            data["summary"] = {
                "hook": report.summary.hook,
                "what": report.summary.what,
                "value": report.summary.value,
                "problem": report.summary.problem,
                "insight": report.summary.insight,
                "show": report.summary.show,
            }
        print(json.dumps(data, indent=2))
        return

    if not report.has_changes:
        print_info("No changes detected.")
        console.print(f"[{BRAND_MUTED}]Working tree clean, nothing staged, up to date with remote.[/]")
        raise typer.Exit()

    # Get LLM client if explain mode
    client = None
    if explain:
        from .openai_analysis import get_openai_client
        client = get_openai_client()
        if not client:
            print_error("LLM not configured. Run `repr llm setup` first.")
            raise typer.Exit(1)

    # Header
    console.print(f"[bold]Changes in {report.repo_path.name}[/]")
    console.print()

    # Unstaged changes
    if report.unstaged:
        console.print(f"[bold][{BRAND_WARNING}]Unstaged[/][/] ({len(report.unstaged)} files)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining unstaged..."):
                explanation = asyncio.run(explain_group("unstaged", file_changes=report.unstaged, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for f in report.unstaged:
            type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
            stats = ""
            if f.insertions or f.deletions:
                stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
            full_path = report.repo_path / f.path
            console.print(f"  {type_icon} {full_path}{stats}")
            # Show diff preview unless compact mode
            if not compact and f.diff_preview:
                for line in f.diff_preview.split("\n")[:10]:
                    if line.startswith("+"):
                        console.print(f"    [{BRAND_SUCCESS}]{line}[/]")
                    elif line.startswith("-"):
                        console.print(f"    [{BRAND_ERROR}]{line}[/]")
        console.print()

    # Staged changes
    if report.staged:
        console.print(f"[bold][{BRAND_SUCCESS}]Staged[/][/] ({len(report.staged)} files)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining staged..."):
                explanation = asyncio.run(explain_group("staged", file_changes=report.staged, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for f in report.staged:
            type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
            stats = ""
            if f.insertions or f.deletions:
                stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
            full_path = report.repo_path / f.path
            console.print(f"  {type_icon} {full_path}{stats}")
            # Show diff preview unless compact mode
            if not compact and f.diff_preview:
                for line in f.diff_preview.split("\n")[:10]:
                    if line.startswith("+"):
                        console.print(f"    [{BRAND_SUCCESS}]{line}[/]")
                    elif line.startswith("-"):
                        console.print(f"    [{BRAND_ERROR}]{line}[/]")
        console.print()

    # Unpushed commits
    if report.unpushed:
        console.print(f"[bold][{BRAND_PRIMARY}]Unpushed[/][/] ({len(report.unpushed)} commits)")
        # Explain this group right after header
        if client:
            with create_spinner("Explaining unpushed..."):
                explanation = asyncio.run(explain_group("unpushed", commit_changes=report.unpushed, client=client))
            console.print()
            console.print(f"[{BRAND_MUTED}]{explanation}[/]")
            console.print()
        for commit in report.unpushed:
            console.print(f"  [{BRAND_MUTED}]{commit.sha}[/] {commit.message}")
            # Show files changed in this commit
            for f in commit.files[:5]:
                type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
                full_path = report.repo_path / f.path
                console.print(f"    {type_icon} {full_path}")
            if len(commit.files) > 5:
                console.print(f"    [{BRAND_MUTED}]... +{len(commit.files) - 5} more[/]")
        console.print()


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


# =============================================================================
# MCP SERVER
# =============================================================================

@mcp_app.command("serve")
def mcp_serve(
    sse: bool = typer.Option(False, "--sse", help="Use SSE transport instead of stdio"),
    port: int = typer.Option(3001, "--port", "-p", help="Port for SSE mode"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host for SSE mode"),
):
    """
    Start the MCP server for AI agent integration.
    
    The MCP (Model Context Protocol) server exposes repr functionality
    to AI agents like Claude Code, Cursor, Windsurf, and Cline.
    
    Examples:
        repr mcp serve              # stdio mode (default)
        repr mcp serve --sse        # SSE mode for remote clients
        repr mcp serve --port 3001  # Custom port for SSE
    
    Configuration for Claude Code:
        claude mcp add repr -- repr mcp serve
    
    Configuration for Cursor/Windsurf (mcp.json):
        {
          "mcpServers": {
            "repr": {
              "command": "repr",
              "args": ["mcp", "serve"]
            }
          }
        }
    """
    from .mcp_server import run_server
    
    if not sse:
        # stdio mode - silent start, let MCP handle communication
        run_server(sse=False)
    else:
        console.print(f"Starting MCP server (SSE mode) on {host}:{port}...")
        run_server(sse=True, host=host, port=port)


@mcp_app.command("info")
def mcp_info():
    """
    Show MCP server configuration info.
    
    Example:
        repr mcp info
    """
    console.print("[bold]MCP Server Info[/]")
    console.print()
    console.print("The MCP server exposes repr to AI agents via the Model Context Protocol.")
    console.print()
    console.print("[bold]Available Tools:[/]")
    console.print("  • repr_generate    — Generate stories from commits")
    console.print("  • repr_stories_list — List existing stories")
    console.print("  • repr_week        — Weekly work summary")
    console.print("  • repr_standup     — Yesterday/today summary")
    console.print("  • repr_profile     — Get developer profile")
    console.print()
    console.print("[bold]Available Resources:[/]")
    console.print("  • repr://profile        — Current profile")
    console.print("  • repr://stories/recent — Recent stories")
    console.print()
    console.print("[bold]Usage:[/]")
    console.print("  repr mcp serve              # Start server (stdio)")
    console.print("  repr mcp serve --sse        # SSE mode")
    console.print()
    console.print("[bold]Claude Code setup:[/]")
    console.print("  claude mcp add repr -- repr mcp serve")


@mcp_app.command("install-skills")
def mcp_install_skills(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skill files"),
):
    """
    Install repr skills to Claude Code.

    Installs a skill that teaches Claude Code how and when to use repr commands
    (init, generate, timeline, changes).

    Example:
        repr mcp install-skills
        repr mcp install-skills --force  # Overwrite existing
    """
    plugin_dir = Path.home() / ".claude" / "plugins" / "local" / "repr"
    skill_dir = plugin_dir / "skills" / "repr"
    plugin_json_dir = plugin_dir / ".claude-plugin"

    # Check if already installed
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists() and not force:
        print_warning("repr skill already installed")
        console.print(f"  Location: {skill_file}")
        console.print()
        console.print("Use --force to overwrite")
        return

    # Create directories
    skill_dir.mkdir(parents=True, exist_ok=True)
    plugin_json_dir.mkdir(parents=True, exist_ok=True)

    # Write plugin.json
    plugin_json = {
        "name": "repr",
        "description": "Developer context layer - understand what you've actually worked on through git history and AI sessions.",
        "author": {"name": "repr.dev"}
    }
    (plugin_json_dir / "plugin.json").write_text(json.dumps(plugin_json, indent=2) + "\n")

    # Write skill file
    skill_content = '''---
name: repr
description: Use this skill when the user asks to "show my changes", "what did I work on", "generate a story", "initialize repr", "show timeline", "set up repr", "commit", "create branch", "create PR", "push", or needs context about their recent development work.
version: 1.0.0
---

# repr - Developer Context Layer

repr helps developers understand what they've actually worked on by analyzing git history and AI sessions.

## When to Use repr

- User asks about their recent work or changes
- User wants to generate a story or summary from commits
- User needs to set up repr for a project
- User wants to see their development timeline
- User asks "what did I work on" or similar

## Commands

### Initialize repr

```bash
# First-time setup - scan for repositories
repr init

# Scan specific directory
repr init ~/projects
```

Use when: User is setting up repr for the first time or adding new repositories.

### Show Changes

```bash
# Show current changes (unstaged, staged, unpushed)
repr changes

# Compact view (just file names)
repr changes --compact

# With LLM explanation
repr changes --explain

# JSON output
repr changes --json
```

Use when: User asks "what are my changes", "show my work", "what's uncommitted", or needs to understand current git state.

### Generate Stories

```bash
# Generate stories from recent commits
repr generate

# Generate for specific date range
repr generate --since monday
repr generate --since "2 weeks ago"

# Use local LLM (Ollama)
repr generate --local

# Dry run (preview without saving)
repr generate --dry-run
```

Use when: User wants to create narratives from their commits, document their work, or generate content for standup/weekly reports.

### Timeline

```bash
# Initialize timeline for current project
repr timeline init

# Initialize with AI session ingestion
repr timeline init --with-sessions

# Show timeline entries
repr timeline show
repr timeline show --days 14

# Filter by type
repr timeline show --type commit
repr timeline show --type session

# Show timeline status
repr timeline status

# Refresh/update timeline
repr timeline refresh

# Serve timeline viewer in browser
repr timeline serve
```

Use when: User wants a unified view of commits and AI sessions, or needs to understand the full context of their development work.

## Output Interpretation

### Changes Output
- **Unstaged**: Modified files not yet staged (with diff preview)
- **Staged**: Changes ready to commit
- **Unpushed**: Commits not yet pushed to remote

### Timeline Entry Types
- **commit**: Regular git commits
- **session**: AI coding sessions (Claude Code, etc.)
- **merged**: Commits with associated AI session context

### Smart Git Workflow

```bash
# Stage files
repr add cli              # Stage files matching "cli"
repr add .                # Stage all

# Create branch (AI generates name)
repr branch               # AI generates name
repr branch feat/my-feat  # Explicit name

# Commit (AI generates message)
repr commit               # AI generates message
repr commit -m "fix: x"   # Custom message

# Push and create PR
repr push                 # Push to remote
repr pr                   # Create PR (AI generates title/body)
repr pr --draft           # Create draft PR
```

Use when: User wants to stage, branch, commit, push, or create PR.

## Tips

1. Run `repr changes` before committing to see what you're about to commit
2. Use `repr generate --dry-run` to preview stories before saving
3. Initialize timeline with `--with-sessions` to capture AI context
4. Use `repr timeline show --type session` to see AI-assisted work separately
5. Use `repr add` + `repr commit` for quick commits with AI-generated messages
6. Use `repr clear` to reset cached branch/commit message
'''

    skill_file.write_text(skill_content)

    print_success("repr skill installed to Claude Code")
    console.print()
    console.print(f"  Plugin: {plugin_dir}")
    console.print(f"  Skill: {skill_file}")
    console.print()
    console.print("Claude Code will now recognize repr commands.")
    console.print("Try asking: 'show my changes' or 'what did I work on'")


# =============================================================================
# TIMELINE
# =============================================================================

@timeline_app.command("init")
def timeline_init(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project path (default: current directory)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    with_sessions: bool = typer.Option(
        False, "--with-sessions", "-s",
        help="Include AI session context (Claude Code, Clawdbot)",
    ),
    days: int = typer.Option(
        90, "--days", "-d",
        help="Number of days to look back",
    ),
    max_commits: int = typer.Option(
        500, "--max-commits",
        help="Maximum commits to include",
    ),
    model: str = typer.Option(
        "openai/gpt-4.1-mini", "--model", "-m",
        help="Model for session extraction (with --with-sessions)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing timeline",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Initialize a project timeline from git commits and AI sessions.
    
    Creates .repr/timeline.json with unified context from:
    - Git commits (always included)
    - AI session logs (with --with-sessions flag)
    
    Examples:
        repr timeline init                    # Commits only
        repr timeline init --with-sessions    # Include AI sessions
        repr timeline init --days 30          # Last 30 days
        repr timeline init ~/myproject        # Specific project
    """
    from .timeline import (
        detect_project_root,
        is_initialized,
        init_timeline_commits_only,
        init_timeline_with_sessions_sync,
        get_timeline_stats,
    )
    from .loaders import detect_session_source
    
    # Determine project path
    project_path = path or Path.cwd()
    
    # Check if in git repo
    repo_root = detect_project_root(project_path)
    if not repo_root:
        print_error(f"Not a git repository: {project_path}")
        print_info("Run this command inside a git repository")
        raise typer.Exit(1)
    
    project_path = repo_root
    
    # Check if already initialized
    if is_initialized(project_path) and not force:
        print_warning(f"Timeline already exists for {project_path}")
        print_info("Use --force to reinitialize")
        raise typer.Exit(1)
    
    if not json_output:
        print_header()
        console.print(f"Initializing timeline for [bold]{project_path.name}[/]")
        console.print()
    
    # Check for session sources if --with-sessions
    session_sources = []
    if with_sessions:
        session_sources = detect_session_source(project_path)
        if not session_sources:
            if not json_output:
                print_warning("No AI session sources found for this project")
                print_info("Supported: Claude Code (~/.claude/projects/), Clawdbot (~/.clawdbot/)")
                if not confirm("Continue with commits only?", default=True):
                    raise typer.Exit(0)
            with_sessions = False
        else:
            if not json_output:
                console.print(f"Session sources: {', '.join(session_sources)}")
    
    # Progress tracking
    progress_state = {"stage": "", "current": 0, "total": 0}
    
    def progress_callback(stage: str, current: int, total: int) -> None:
        progress_state["stage"] = stage
        progress_state["current"] = current
        progress_state["total"] = total
    
    try:
        if with_sessions:
            # Get API key for extraction
            # Priority: BYOK OpenAI > env OPENAI_API_KEY > LiteLLM (cloud)
            api_key = None
            byok_config = get_byok_config("openai")
            if byok_config:
                api_key = byok_config.get("api_key")
            
            if not api_key:
                # Try environment variable (direct OpenAI access)
                api_key = os.environ.get("OPENAI_API_KEY")
            
            if not api_key:
                # Try LiteLLM config (cloud mode - needs LiteLLM proxy URL)
                _, litellm_key = get_litellm_config()
                api_key = litellm_key
            
            if not api_key:
                if not json_output:
                    print_warning("No API key configured for session extraction")
                    print_info("Configure with: repr llm add openai")
                    print_info("Or set OPENAI_API_KEY environment variable")
                    if not confirm("Continue with commits only?", default=True):
                        raise typer.Exit(0)
                with_sessions = False
        
        if with_sessions:
            if not json_output:
                with create_spinner() as progress:
                    task = progress.add_task("Initializing...", total=None)
                    timeline = init_timeline_with_sessions_sync(
                        project_path,
                        days=days,
                        max_commits=max_commits,
                        session_sources=session_sources,
                        api_key=api_key,
                        model=model,
                        progress_callback=progress_callback,
                    )
            else:
                timeline = init_timeline_with_sessions_sync(
                    project_path,
                    days=days,
                    max_commits=max_commits,
                    session_sources=session_sources,
                    api_key=api_key,
                    model=model,
                )
        else:
            if not json_output:
                with create_spinner() as progress:
                    task = progress.add_task("Scanning commits...", total=None)
                    timeline = init_timeline_commits_only(
                        project_path,
                        days=days,
                        max_commits=max_commits,
                        progress_callback=progress_callback,
                    )
            else:
                timeline = init_timeline_commits_only(
                    project_path,
                    days=days,
                    max_commits=max_commits,
                )
        
        # Get stats
        stats = get_timeline_stats(timeline)
        
        if json_output:
            print(json.dumps({
                "success": True,
                "project": str(project_path),
                "timeline_path": str(project_path / ".repr" / "timeline.json"),
                "stats": stats,
            }, indent=2))
        else:
            console.print()
            print_success(f"Timeline initialized!")
            console.print()
            console.print(f"  Location: .repr/timeline.json")
            console.print(f"  Entries: {stats['total_entries']}")
            console.print(f"    Commits: {stats['commit_count']}")
            if stats['merged_count'] > 0:
                console.print(f"    Merged (commit + session): {stats['merged_count']}")
            if stats['session_count'] > 0:
                console.print(f"    Sessions only: {stats['session_count']}")
            if stats['date_range']['first']:
                console.print(f"  Date range: {stats['date_range']['first'][:10]} to {stats['date_range']['last'][:10]}")
            
            console.print()
            print_next_steps([
                "repr timeline status      View timeline status",
                "repr timeline show        Browse timeline entries",
            ])
    
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print_error(f"Failed to initialize timeline: {e}")
        raise typer.Exit(1)


@timeline_app.command("status")
def timeline_status(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project path (default: current directory)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Show timeline status for a project.
    
    Example:
        repr timeline status
    """
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        get_timeline_stats,
    )
    
    # Determine project path
    project_path = path or Path.cwd()
    repo_root = detect_project_root(project_path)
    
    if not repo_root:
        print_error(f"Not a git repository: {project_path}")
        raise typer.Exit(1)
    
    project_path = repo_root
    
    if not is_initialized(project_path):
        if json_output:
            print(json.dumps({"initialized": False, "project": str(project_path)}, indent=2))
        else:
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
        raise typer.Exit(1)
    
    timeline = load_timeline(project_path)
    if not timeline:
        print_error("Failed to load timeline")
        raise typer.Exit(1)
    
    stats = get_timeline_stats(timeline)
    
    if json_output:
        print(json.dumps({
            "initialized": True,
            "project": str(project_path),
            "stats": stats,
            "last_updated": timeline.last_updated.isoformat() if timeline.last_updated else None,
        }, indent=2))
    else:
        print_header()
        console.print(f"Timeline: [bold]{project_path.name}[/]")
        console.print()
        console.print(f"  Entries: {stats['total_entries']}")
        console.print(f"    Commits: {stats['commit_count']}")
        console.print(f"    Merged: {stats['merged_count']}")
        console.print(f"    Sessions: {stats['session_count']}")
        if stats['date_range']['first']:
            console.print(f"  Date range: {stats['date_range']['first'][:10]} to {stats['date_range']['last'][:10]}")
        if stats['session_sources']:
            console.print(f"  Session sources: {', '.join(stats['session_sources'])}")
        if timeline.last_updated:
            last_updated_str = timeline.last_updated.isoformat() if hasattr(timeline.last_updated, 'isoformat') else str(timeline.last_updated)
            console.print(f"  Last updated: {format_relative_time(last_updated_str)}")


@timeline_app.command("show")
def timeline_show(
    path: Optional[str] = typer.Argument(
        None,
        help="Project path (use '.' for current repo, omit for all repos)",
    ),
    days: int = typer.Option(
        7, "--days", "-d",
        help="Show entries from last N days",
    ),
    entry_type: Optional[str] = typer.Option(
        None, "--type", "-t",
        help="Filter by type: commit, session, merged",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n",
        help="Maximum entries to show",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
    public: bool = typer.Option(
        True, "--public/--no-public",
        help="Build-in-public feed format (default)",
    ),
    internal: bool = typer.Option(
        False, "--internal",
        help="Show technical details in feed",
    ),
    raw: bool = typer.Option(
        False, "--raw",
        help="Show raw timeline entries (commits/sessions)",
    ),
    all_repos: bool = typer.Option(
        False, "--all", "-a",
        help="Show stories from all tracked repos (default when no path given)",
    ),
    group: bool = typer.Option(
        False, "--group", "-g",
        help="Group stories by project (presentation view)",
    ),
):
    """
    Show timeline entries.

    Examples:
        repr timeline show                    # All tracked repos from database
        repr timeline show .                  # Current repo only
        repr timeline show /path/to/repo      # Specific repo
        repr timeline show --group            # All repos, grouped by project
        repr timeline show . --days 30        # Current repo, last 30 days
        repr timeline show --internal         # Feed format with tech details
    """
    from datetime import timezone
    from .timeline import (
        detect_project_root,
        is_initialized,
        load_timeline,
        query_timeline,
    )
    from .models import TimelineEntryType
    from .db import get_db

    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Determine mode: all repos (no path) vs specific repo (path given)
    show_all_repos = path is None and not raw

    # If --all flag is given, always show all repos
    if all_repos:
        show_all_repos = True

    project_path = None
    timeline = None
    entries = []

    if not show_all_repos:
        # Specific repo mode - resolve path
        resolved_path = Path(path) if path else Path.cwd()
        if not resolved_path.is_absolute():
            resolved_path = Path.cwd() / resolved_path
        resolved_path = resolved_path.resolve()

        repo_root = detect_project_root(resolved_path)

        if not repo_root:
            print_error(f"Not a git repository: {resolved_path}")
            raise typer.Exit(1)

        project_path = repo_root

        if not is_initialized(project_path):
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
            raise typer.Exit(1)

        timeline = load_timeline(project_path)
        if not timeline:
            print_error("Failed to load timeline")
            raise typer.Exit(1)

        # Parse entry type filter
        entry_types = None
        if entry_type:
            try:
                entry_types = [TimelineEntryType(entry_type)]
            except ValueError:
                print_error(f"Invalid type: {entry_type}")
                print_info("Valid types: commit, session, merged")
                raise typer.Exit(1)

        # Query entries
        entries = query_timeline(timeline, since=since, entry_types=entry_types)
        entries = entries[-limit:]  # Take most recent

    if json_output:
        if show_all_repos:
            # JSON output for all repos
            stories = db.list_stories(since=since, limit=limit)
            print(json.dumps({
                "mode": "all_repos",
                "stories": [{"id": s.id, "title": s.title, "project_id": s.project_id} for s in stories],
            }, indent=2))
        else:
            from .timeline import _serialize_entry
            print(json.dumps({
                "project": str(project_path),
                "entries": [_serialize_entry(e) for e in entries],
            }, indent=2))
        return

    if not show_all_repos and not entries:
        print_info(f"No entries in the last {days} days")
        return

    # Feed format (default, unless --raw)
    if not raw:
        # Build project lookup
        projects = {p["id"]: p["name"] for p in db.list_projects()}

        if show_all_repos:
            # Show stories from all repos
            stories = db.list_stories(since=since, limit=limit)
            header_name = "all repos"
        else:
            # Show stories from current repo only
            project = db.get_project_by_path(project_path)

            if not project:
                print_info(f"No stories found. Run 'repr generate' first.")
                return

            stories = db.list_stories(project_id=project["id"], since=since, limit=limit)
            header_name = project_path.name

        if not stories:
            print_info(f"No stories in the last {days} days. Run 'repr generate' first.")
            return

        def format_rel_time(story_time):
            """Format timestamp as relative time."""
            local_time = story_time.astimezone()
            now = datetime.now(local_time.tzinfo)
            delta = now - local_time

            if delta.days == 0:
                if delta.seconds < 3600:
                    return f"{delta.seconds // 60}m ago"
                else:
                    return f"{delta.seconds // 3600}h ago"
            elif delta.days == 1:
                return "Yesterday"
            elif delta.days < 7:
                return f"{delta.days} days ago"
            else:
                return local_time.strftime("%b %d")

        def render_story(story, show_repo=False):
            """Render a single story entry using Tripartite Codex structure."""
            story_time = story.started_at or story.created_at
            rel_time = format_rel_time(story_time)
            repo_name = projects.get(story.project_id, "unknown")

            # Header with time and optional repo
            if show_repo:
                console.print(f"[{BRAND_PRIMARY}]{repo_name}[/] · [{BRAND_MUTED}]{rel_time}[/]")
            else:
                console.print(f"[{BRAND_MUTED}]{rel_time}[/]")

            # Use structured fields if available, fall back to legacy
            if story.hook:
                # New Tripartite Codex format
                console.print(f"[bold]{story.hook}[/]")
                console.print()
                what_text = story.what.rstrip(".")
                console.print(f"{what_text}. {story.value}")

                # Show block if present
                if story.show:
                    console.print()
                    console.print(f"```\n{story.show}\n```")

                # Internal mode: show problem and how
                if internal:
                    if story.problem:
                        console.print()
                        console.print(f"[{BRAND_MUTED}]Problem:[/] {story.problem}")

                    if story.implementation_details:
                        console.print()
                        console.print(f"[{BRAND_MUTED}]How:[/]")
                        for detail in story.implementation_details[:5]:
                            console.print(f"  [{BRAND_MUTED}]›[/] {detail}")

                # Insight
                if story.insight:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Insight:[/] {story.insight}")

            else:
                # Legacy format fallback
                post_text = story.public_post or story.title
                if internal:
                    post_text = story.internal_post or post_text
                console.print(post_text)

                show_block = story.show or story.public_show
                if internal:
                    show_block = show_block or story.internal_show
                if show_block:
                    console.print()
                    console.print(f"```\n{show_block}\n```")

                if internal and story.internal_details:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Implementation:[/]")
                    for detail in story.internal_details[:5]:
                        console.print(f"  [{BRAND_MUTED}]›[/] {detail}")

            # Recall data (internal mode only) - file changes and snippets
            if internal:
                # File changes summary
                if story.file_changes:
                    total_changes = f"+{story.total_insertions}/-{story.total_deletions}" if (story.total_insertions or story.total_deletions) else ""
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Files changed ({len(story.file_changes)})[/] [{BRAND_MUTED}]{total_changes}[/]")
                    for fc in story.file_changes[:8]:  # Show up to 8 files
                        change_indicator = {"added": "+", "deleted": "-", "modified": "~"}.get(fc.change_type, "~")
                        stats = f"[green]+{fc.insertions}[/][{BRAND_MUTED}]/[/][red]-{fc.deletions}[/]" if (fc.insertions or fc.deletions) else ""
                        console.print(f"  [{BRAND_MUTED}]{change_indicator}[/] {fc.file_path} {stats}")
                    if len(story.file_changes) > 8:
                        console.print(f"  [{BRAND_MUTED}]... and {len(story.file_changes) - 8} more files[/]")

                # Key code snippets
                if story.key_snippets:
                    console.print()
                    console.print(f"[{BRAND_MUTED}]Snippets:[/]")
                    for snippet in story.key_snippets[:2]:  # Show up to 2 snippets
                        lang = snippet.language or ""
                        console.print(f"  [{BRAND_MUTED}]{snippet.file_path}[/]")
                        console.print(f"```{lang}\n{snippet.content}\n```")

            console.print()
            console.print(f"[{BRAND_MUTED}]{'─' * 60}[/]")
            console.print()

        print_header()

        if group and all_repos:
            # Grouped view: organize by project
            console.print(f"[bold]@all repos[/] · build log [dim](grouped)[/]")
            console.print()

            # Group stories by project
            from collections import defaultdict
            stories_by_project = defaultdict(list)
            for story in stories:
                stories_by_project[story.project_id].append(story)

            # Render each project group
            for project_id, project_stories in stories_by_project.items():
                project_name = projects.get(project_id, "unknown")
                console.print(f"[bold]── {project_name} ──[/]")
                console.print()

                for story in project_stories:
                    render_story(story, show_repo=False)

        else:
            # Timeline view (default)
            console.print(f"[bold]@{header_name}[/] · build log")
            console.print()

            for story in stories:
                render_story(story, show_repo=all_repos)

        return

    # Default format (unchanged)
    print_header()
    console.print(f"Timeline: [bold]{project_path.name}[/] (last {days} days)")
    console.print()

    for entry in reversed(entries):  # Show newest first
        # Format timestamp (convert to local timezone)
        local_ts = entry.timestamp.astimezone()
        ts = local_ts.strftime("%Y-%m-%d %H:%M")

        # Entry type indicator
        if entry.type == TimelineEntryType.COMMIT:
            type_icon = "📝"
        elif entry.type == TimelineEntryType.SESSION:
            type_icon = "💬"
        else:  # MERGED
            type_icon = "🔗"

        # Build description
        if entry.commit:
            # Show first line of commit message
            msg = entry.commit.message.split("\n")[0][:60]
            if len(entry.commit.message.split("\n")[0]) > 60:
                msg += "..."
            desc = f"{msg}"
            sha = entry.commit.sha[:8]
            console.print(f"{type_icon} [{BRAND_MUTED}]{ts}[/] [{BRAND_PRIMARY}]{sha}[/] {desc}")
        elif entry.session_context:
            # Show problem from session
            problem = entry.session_context.problem[:60]
            if len(entry.session_context.problem) > 60:
                problem += "..."
            console.print(f"{type_icon} [{BRAND_MUTED}]{ts}[/] {problem}")

        # Show session context if merged
        if entry.type == TimelineEntryType.MERGED and entry.session_context:
            console.print(f"    [{BRAND_MUTED}]→ {entry.session_context.problem[:70]}[/]")

        console.print()


@timeline_app.command("refresh")
def timeline_refresh(
    path: Optional[str] = typer.Argument(
        None,
        help="Project path (use '.' for current repo, omit for all repos)",
    ),
    limit: int = typer.Option(
        50, "--limit", "-n",
        help="Maximum stories to refresh",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Regenerate posts for existing stories.

    This updates the public_post and internal_post fields without
    re-analyzing commits. Useful after prompt improvements.

    Examples:
        repr timeline refresh              # Refresh all repos
        repr timeline refresh .            # Refresh current repo only
        repr timeline refresh --limit 10   # Refresh last 10 stories
    """
    from .db import get_db
    from .story_synthesis import (
        transform_story_for_feed_sync,
        _build_fallback_post,
        extract_file_changes_from_commits,
        extract_key_snippets_from_commits,
    )

    db = get_db()

    # Determine scope
    if path is None:
        # All repos
        stories = db.list_stories(limit=limit)
        scope_name = "all repos"
    else:
        # Specific repo
        from .timeline import detect_project_root
        resolved_path = Path(path) if path else Path.cwd()
        if not resolved_path.is_absolute():
            resolved_path = Path.cwd() / resolved_path
        resolved_path = resolved_path.resolve()

        repo_root = detect_project_root(resolved_path)
        if not repo_root:
            print_error(f"Not a git repository: {resolved_path}")
            raise typer.Exit(1)

        project = db.get_project_by_path(repo_root)
        if not project:
            print_error(f"No stories found for {repo_root.name}")
            raise typer.Exit(1)

        stories = db.list_stories(project_id=project["id"], limit=limit)
        scope_name = repo_root.name

    if not stories:
        print_info("No stories to refresh")
        return

    print_header()
    console.print(f"Refreshing {len(stories)} stories from {scope_name}...")
    console.print()

    refreshed = 0
    failed = 0

    # Get project paths for file extraction
    project_paths = {}
    for p in db.list_projects():
        project_paths[p["id"]] = p["path"]

    for story in stories:
        try:
            # Extract file changes and snippets from git
            project_path = project_paths.get(story.project_id)
            if story.commit_shas and project_path:
                file_changes, total_ins, total_del = extract_file_changes_from_commits(
                    story.commit_shas, project_path
                )
                story.file_changes = file_changes
                story.total_insertions = total_ins
                story.total_deletions = total_del
                story.key_snippets = extract_key_snippets_from_commits(
                    story.commit_shas, project_path, max_snippets=3
                )

            # Regenerate Tripartite Codex content
            result = transform_story_for_feed_sync(story, mode="internal")

            # Store structured fields
            story.hook = result.hook
            story.what = result.what
            story.value = result.value
            story.insight = result.insight
            story.show = result.show

            # Internal-specific fields
            if hasattr(result, 'problem') and result.problem:
                story.problem = result.problem
            if hasattr(result, 'how') and result.how:
                story.implementation_details = result.how

            # Legacy fields for backward compatibility
            story.public_post = f"{result.hook}\n\n{result.what}. {result.value}\n\nInsight: {result.insight}"
            story.internal_post = story.public_post
            story.public_show = result.show
            story.internal_show = result.show

            # Update in database
            db.save_story(story, story.project_id)
            refreshed += 1

            if not json_output:
                console.print(f"  [green]✓[/] {story.title[:60]}")

        except Exception as e:
            # Use fallback
            fallback_post = _build_fallback_post(story)
            story.public_post = fallback_post
            story.internal_post = fallback_post
            db.save_story(story, story.project_id)
            failed += 1

            if not json_output:
                console.print(f"  [yellow]![/] {story.title[:60]} (fallback)")

    console.print()

    if json_output:
        print(json.dumps({"refreshed": refreshed, "failed": failed}))
    else:
        print_success(f"Refreshed {refreshed} stories" + (f" ({failed} used fallback)" if failed else ""))


@timeline_app.command("ingest-session")
def timeline_ingest_session(
    file: Path = typer.Option(
        ..., "--file", "-f",
        help="Path to session file (JSONL)",
        exists=True,
        file_okay=True,
        resolve_path=True,
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", "-p",
        help="Project path (default: detected from session cwd)",
        exists=True,
        dir_okay=True,
        resolve_path=True,
    ),
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help="Session source: claude_code, clawdbot (default: auto-detect)",
    ),
    model: str = typer.Option(
        "openai/gpt-4.1-mini", "--model", "-m",
        help="Model for context extraction",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
):
    """
    Ingest a completed AI session into the timeline.
    
    Called by SessionEnd hooks to capture context from AI coding sessions.
    
    Examples:
        repr timeline ingest-session --file ~/.claude/projects/.../session.jsonl
        repr timeline ingest-session --file /path/to/session.jsonl --project ~/myproject
    """
    from datetime import timezone
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
    
    # Determine source
    if source is None:
        if ".claude" in str(file):
            source = "claude_code"
        elif ".clawdbot" in str(file):
            source = "clawdbot"
        else:
            # Try both loaders
            source = "claude_code"
    
    # Load session
    if source == "claude_code":
        loader = ClaudeCodeLoader()
    elif source == "clawdbot":
        loader = ClawdbotLoader()
    else:
        print_error(f"Unknown source: {source}")
        raise typer.Exit(1)
    
    session = loader.load_session(file)
    if not session:
        if json_output:
            print(json.dumps({"success": False, "error": "Failed to load session"}))
        else:
            print_error(f"Failed to load session from {file}")
        raise typer.Exit(1)
    
    # Determine project path
    if project is None:
        if session.cwd:
            project = detect_project_root(Path(session.cwd))
        if project is None:
            if json_output:
                print(json.dumps({"success": False, "error": "Could not detect project path"}))
            else:
                print_error("Could not detect project path from session")
                print_info("Specify with --project /path/to/repo")
            raise typer.Exit(1)
    
    project_path = project
    
    # Check if timeline exists
    if not is_initialized(project_path):
        if json_output:
            print(json.dumps({"success": False, "error": f"Timeline not initialized for {project_path}"}))
        else:
            print_warning(f"Timeline not initialized for {project_path.name}")
            print_info("Run: repr timeline init")
        raise typer.Exit(1)
    
    # Load existing timeline
    timeline = load_timeline(project_path)
    if not timeline:
        print_error("Failed to load timeline")
        raise typer.Exit(1)
    
    # Check if session already ingested
    for entry in timeline.entries:
        if entry.session_context and entry.session_context.session_id == session.id:
            if json_output:
                print(json.dumps({"success": True, "skipped": True, "reason": "Session already ingested"}))
            else:
                print_info(f"Session {session.id[:8]} already ingested")
            return
    
    # Get API key for extraction
    api_key = None
    byok_config = get_byok_config("openai")
    if byok_config:
        api_key = byok_config.get("api_key")
    
    if not api_key:
        _, litellm_key = get_litellm_config()
        api_key = litellm_key
    
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        if json_output:
            print(json.dumps({"success": False, "error": "No API key for extraction"}))
        else:
            print_error("No API key configured for session extraction")
            print_info("Configure with: repr llm add openai")
        raise typer.Exit(1)
    
    # Extract context from session
    async def _extract():
        extractor = SessionExtractor(api_key=api_key, model=model)
        return await extractor.extract_context(session)
    
    if not json_output:
        with create_spinner() as progress:
            task = progress.add_task("Extracting context...", total=None)
            context = asyncio.run(_extract())
    else:
        context = asyncio.run(_extract())
    
    # Get recent commits to potentially link
    recent_commits = extract_commits_from_git(
        project_path,
        days=1,  # Just last day for linking
        max_commits=50,
    )
    
    # Match session to commits
    if recent_commits:
        matches = match_commits_to_sessions(recent_commits, [session])
        linked_commits = [m.commit_sha for m in matches if m.session_id == session.id]
        context.linked_commits = linked_commits
    
    # Create timeline entry
    entry_type = TimelineEntryType.SESSION
    if context.linked_commits:
        # Find and upgrade matching commit entries to MERGED
        for commit_sha in context.linked_commits:
            for entry in timeline.entries:
                if entry.commit and entry.commit.sha == commit_sha:
                    entry.session_context = context
                    entry.type = TimelineEntryType.MERGED
                    entry_type = None  # Don't create standalone entry
                    break
            if entry_type is None:
                break
    
    # Add standalone session entry if not merged
    if entry_type is not None:
        entry = TimelineEntry(
            timestamp=context.timestamp,
            type=entry_type,
            commit=None,
            session_context=context,
            story=None,
        )
        timeline.add_entry(entry)
    
    # Save timeline
    save_timeline(timeline, project_path)
    
    if json_output:
        print(json.dumps({
            "success": True,
            "session_id": session.id,
            "project": str(project_path),
            "problem": context.problem[:100],
            "linked_commits": context.linked_commits,
            "entry_type": entry_type.value if entry_type else "merged",
        }, indent=2))
    else:
        print_success(f"Session ingested!")
        console.print()
        console.print(f"  Session: {session.id[:8]}")
        console.print(f"  Problem: {context.problem[:60]}...")
        if context.linked_commits:
            console.print(f"  Linked to commits: {', '.join(c[:8] for c in context.linked_commits)}")
        console.print(f"  Entry type: {entry_type.value if entry_type else 'merged'}")


@timeline_app.command("serve")
def timeline_serve(
    port: int = typer.Option(
        3000, "--port", "-p",
        help="Port to serve on",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host",
        help="Host to bind to",
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open",
        help="Auto-open browser (default: enabled)",
    ),
):
    """
    Launch web dashboard for timeline exploration.

    Starts a local web server to browse and search through your
    timeline entries with rich context visualization.

    Works from any directory - reads from central SQLite database.

    Examples:
        repr timeline serve              # localhost:3000, auto-opens browser
        repr timeline serve --port 8080  # custom port
        repr timeline serve --no-open    # don't auto-open browser
    """
    import webbrowser
    from .dashboard import run_server
    from .db import DB_PATH, get_db

    # Check if SQLite database exists and has stories
    if not DB_PATH.exists():
        print_error("No stories database found")
        print_info("Run `repr generate` in a git repository first")
        raise typer.Exit(1)

    db = get_db()
    stats = db.get_stats()
    story_count = stats.get("story_count", 0)
    project_count = stats.get("project_count", 0)

    if story_count == 0:
        print_error("No stories in database")
        print_info("Run `repr generate` to create stories from commits")
        raise typer.Exit(1)

    console.print(f"Starting dashboard with [bold]{story_count} stories[/] from [bold]{project_count} repositories[/]")

    url = f"http://{host}:{port}"
    
    print_header()
    console.print(f"  URL: [bold blue]{url}[/]")
    console.print()
    console.print("[dim]Press Ctrl+C to stop[/]")
    console.print()
    
    if open_browser:
        webbrowser.open(url)
    
    try:
        run_server(port, host)
    except KeyboardInterrupt:
        console.print()
        print_info("Server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            print_error(f"Port {port} is already in use")
            print_info(f"Try: repr timeline serve --port {port + 1}")
        else:
            raise


# =============================================================================
# GIT WORKFLOW COMMANDS (add, commit, push)
# =============================================================================

# File-based cache for commit message (persists between commands)
_COMMIT_MSG_CACHE_FILE = Path.home() / ".repr" / ".commit_message_cache"


COMMIT_MESSAGE_SYSTEM = """You generate git commit messages and branch names. Given staged changes, output JSON with:

{
  "branch": "<type>/<short-description>",
  "message": "<type>: <description>"
}

Types: feat, fix, refactor, docs, style, test, chore

Rules:
- Branch: lowercase, hyphens, no spaces (e.g., feat/add-user-auth)
- Message: under 72 chars, imperative mood, no period at end

Output only valid JSON."""

COMMIT_MESSAGE_USER = """Generate branch name and commit message for these staged changes:

{changes}"""


def _get_cached_commit_info() -> Optional[dict]:
    """Get cached commit info (branch + message) if it exists."""
    if _COMMIT_MSG_CACHE_FILE.exists():
        try:
            return json.loads(_COMMIT_MSG_CACHE_FILE.read_text())
        except Exception:
            return None
    return None


def _set_cached_commit_info(branch: str, message: str):
    """Cache the commit info."""
    _COMMIT_MSG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COMMIT_MSG_CACHE_FILE.write_text(json.dumps({"branch": branch, "message": message}))


def _clear_cached_commit_info():
    """Clear the cached commit info."""
    if _COMMIT_MSG_CACHE_FILE.exists():
        _COMMIT_MSG_CACHE_FILE.unlink()


@app.command("clear")
def clear_cache():
    """
    Clear cached branch name and commit message.

    Examples:
        repr clear
    """
    cached = _get_cached_commit_info()
    if cached:
        console.print(f"[{BRAND_MUTED}]Clearing cached:[/]")
        if cached.get("branch"):
            console.print(f"  Branch: {cached['branch']}")
        if cached.get("message"):
            console.print(f"  Message: {cached['message']}")
        _clear_cached_commit_info()
        print_success("Cache cleared")
    else:
        print_info("No cached branch/message")


@app.command("add")
def add_files(
    pattern: str = typer.Argument(..., help="File pattern to stage (glob pattern)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force add ignored files"),
):
    """
    Stage files matching pattern.

    Run `repr commit` to generate a message and commit.

    Examples:
        repr add cli              # Stage files containing "cli"
        repr add .py              # Stage files containing ".py"
        repr add .                # Stage all
        repr add cli -f           # Force add ignored files
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Special case: "." means all
    if pattern == ".":
        try:
            cmd = ["git", "add", "."]
            if force:
                cmd.insert(2, "-f")
            result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print_error(f"Failed to stage files: {result.stderr}")
                raise typer.Exit(1)
        except Exception as e:
            print_error(f"Failed to stage files: {e}")
            raise typer.Exit(1)
    else:
        # Grep-style match: find files containing pattern
        # Get modified/untracked files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if status_result.returncode != 0:
            print_error(f"Failed to get status: {status_result.stderr}")
            raise typer.Exit(1)

        # Parse status output and filter by pattern (grep-style regex)
        import re
        matching_files = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to literal match if invalid regex
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for line in status_result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: XY filename or XY orig -> renamed (XY is 2 chars, then optional space)
            file_path = line[2:].lstrip().split(" -> ")[-1].strip()
            if regex.search(file_path):
                matching_files.append(file_path)

        if not matching_files:
            print_warning(f"No changed files matching '{pattern}'")
            raise typer.Exit(0)

        # Stage matching files
        try:
            cmd = ["git", "add"]
            if force:
                cmd.append("-f")
            cmd.extend(matching_files)
            result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print_error(f"Failed to stage files: {result.stderr}")
                raise typer.Exit(1)
        except Exception as e:
            print_error(f"Failed to stage files: {e}")
            raise typer.Exit(1)

    staged = get_staged_changes(repo)
    if not staged:
        print_warning("No files matched pattern or nothing to stage")
        raise typer.Exit(0)

    # Clear cached branch/message so next commit generates fresh
    _clear_cached_commit_info()

    # Show staged files
    console.print(f"[bold]Staged {len(staged)} files[/]")
    for f in staged:
        type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
        stats = ""
        if f.insertions or f.deletions:
            stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
        console.print(f"  {type_icon} {f.path}{stats}")
    console.print()

    # Suggest branch if on main/master, otherwise commit
    try:
        branch_name = repo.active_branch.name
        if branch_name in ("main", "master"):
            print_info("Run `repr branch` to create a feature branch")
        else:
            print_info("Run `repr commit` to generate message and commit")
    except Exception:
        print_info("Run `repr commit` to generate message and commit")


@app.command("unstage")
def unstage_files(
    pattern: str = typer.Argument(..., help="File pattern to unstage (grep-style match)"),
):
    """
    Unstage files matching pattern.

    Examples:
        repr unstage cli           # Unstage files containing "cli"
        repr unstage .py           # Unstage files containing ".py"
        repr unstage .             # Unstage all staged files
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Get currently staged files
    staged = get_staged_changes(repo)
    if not staged:
        print_warning("No staged files")
        raise typer.Exit(0)

    # Special case: "." means all
    if pattern == ".":
        matching_files = [f.path for f in staged]
    else:
        # Grep-style match: find staged files containing pattern
        matching_files = [f.path for f in staged if pattern.lower() in f.path.lower()]

    if not matching_files:
        print_warning(f"No staged files matching '{pattern}'")
        raise typer.Exit(0)

    # Unstage matching files
    try:
        cmd = ["git", "restore", "--staged"] + matching_files
        result = subprocess.run(cmd, cwd=repo.working_dir, capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"Failed to unstage files: {result.stderr}")
            raise typer.Exit(1)
    except Exception as e:
        print_error(f"Failed to unstage files: {e}")
        raise typer.Exit(1)

    # Show what was unstaged
    console.print(f"[bold]Unstaged {len(matching_files)} files[/]")
    for f in matching_files:
        console.print(f"  - {f}")


@app.command("branch")
def create_branch(
    name: Optional[str] = typer.Argument(None, help="Branch name (optional, AI generates if omitted)"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate branch name"),
):
    """
    Create and switch to a new branch.

    If no name given, generates one from staged or unpushed changes.

    Examples:
        repr branch                    # AI generates name
        repr branch feat/my-feature    # Use explicit name
        repr branch -r                 # Regenerate name
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes, get_unpushed_commits, format_file_changes, format_commit_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    branch_name = name

    if not branch_name:
        # Check cache first
        cached = _get_cached_commit_info()
        if cached and cached.get("branch") and not regenerate:
            branch_name = cached["branch"]
            console.print(f"[{BRAND_MUTED}](cached)[/]")
        else:
            # Generate from staged or unpushed changes
            staged = get_staged_changes(repo)
            unpushed = get_unpushed_commits(repo)

            if not staged and not unpushed:
                print_error("No staged or unpushed changes to generate branch name from")
                print_info("Run `repr add <pattern>` first, or provide a name")
                raise typer.Exit(1)

            from .openai_analysis import get_openai_client

            client = get_openai_client()
            if not client:
                print_error("LLM not configured. Run `repr llm setup` first, or provide a name")
                raise typer.Exit(1)

            # Build context from staged and/or unpushed
            changes_str = ""
            if staged:
                changes_str += "Staged changes:\n" + format_file_changes(staged) + "\n\n"
            if unpushed:
                changes_str += "Unpushed commits:\n" + format_commit_changes(unpushed)

            prompt = COMMIT_MESSAGE_USER.format(changes=changes_str)

            with create_spinner("Generating branch name..."):
                response = asyncio.run(client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": COMMIT_MESSAGE_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                ))
                data = json.loads(response.choices[0].message.content)
                branch_name = data.get("branch", "")
                commit_msg = data.get("message", "")

            # Cache both
            _set_cached_commit_info(branch_name, commit_msg)

    console.print(f"[bold]Branch:[/] {branch_name}")

    try:
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if "already exists" in result.stderr:
                # Switch to existing branch
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print_success(f"Switched to {branch_name}")
                    return
            print_error(f"Failed: {result.stderr}")
            raise typer.Exit(1)

        print_success(f"Created and switched to {branch_name}")

        # Check if there are staged changes and suggest next step
        from .change_synthesis import get_staged_changes
        staged = get_staged_changes(repo)
        if staged:
            print_info("Run `repr commit` to commit your staged changes")

    except Exception as e:
        print_error(f"Failed: {e}")
        raise typer.Exit(1)


@app.command("commit")
def commit_staged(
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Custom message (skip AI)"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate message"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation on main/master"),
):
    """
    Generate commit message and commit staged changes.

    Examples:
        repr commit                    # Generate and commit
        repr commit -m "fix: typo"     # Custom message
        repr commit -r                 # Regenerate message
    """
    import subprocess
    from .change_synthesis import get_repo, get_staged_changes, format_file_changes
    from .config import get_config_value, set_config_value

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Check if on main/master
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo.working_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if current_branch in ("main", "master") and not yes:
        allow_main = get_config_value("allow_commit_to_main")
        if allow_main is None:
            # Ask user
            print_warning(f"You're about to commit directly to {current_branch}")
            console.print()
            response = typer.prompt(
                "Allow commits to main/master? [y]es / [n]o / [a]lways / [never]",
                default="n",
            ).lower()

            if response in ("a", "always"):
                set_config_value("allow_commit_to_main", True)
                console.print(f"[{BRAND_MUTED}]Preference saved. Use `repr config set allow_commit_to_main false` to reset.[/]")
            elif response in ("never",):
                set_config_value("allow_commit_to_main", False)
                console.print(f"[{BRAND_MUTED}]Preference saved. Use `repr config set allow_commit_to_main true` to reset.[/]")
                print_info("Create a branch first: repr branch")
                raise typer.Exit(0)
            elif response not in ("y", "yes"):
                print_info("Create a branch first: repr branch")
                raise typer.Exit(0)
        elif allow_main is False:
            print_warning(f"Commits to {current_branch} are disabled")
            print_info("Create a branch first: repr branch")
            print_info("Or use: repr config set allow_commit_to_main true")
            raise typer.Exit(0)

    staged = get_staged_changes(repo)
    if not staged:
        print_warning("Nothing staged to commit")
        print_info("Run `repr add <pattern>` first")
        raise typer.Exit(0)

    # Show staged files
    console.print(f"[bold]Staged {len(staged)} files[/]")
    for f in staged:
        type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
        stats = ""
        if f.insertions or f.deletions:
            stats = f" [{BRAND_SUCCESS}]+{f.insertions}[/][{BRAND_ERROR}]-{f.deletions}[/]"
        console.print(f"  {type_icon} {f.path}{stats}")
    console.print()

    # Get commit message
    commit_msg = None

    if message:
        commit_msg = message
    else:
        # Check cache
        cached = _get_cached_commit_info()
        if cached and cached.get("message") and not regenerate:
            commit_msg = cached["message"]
            console.print(f"[{BRAND_MUTED}](cached)[/]")
        else:
            # Generate with LLM
            from .openai_analysis import get_openai_client

            client = get_openai_client()
            if not client:
                print_error("LLM not configured. Run `repr llm setup` first, or use -m")
                raise typer.Exit(1)

            changes_str = format_file_changes(staged)
            prompt = COMMIT_MESSAGE_USER.format(changes=changes_str)

            with create_spinner("Generating commit message..."):
                response = asyncio.run(client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": COMMIT_MESSAGE_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                ))
                data = json.loads(response.choices[0].message.content)
                branch_name = data.get("branch", "")
                commit_msg = data.get("message", "")

            _set_cached_commit_info(branch_name, commit_msg)

    console.print(f"[bold]Message:[/] {commit_msg}")
    console.print()

    try:
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_error(f"Commit failed: {result.stderr}")
            raise typer.Exit(1)

        _clear_cached_commit_info()
        print_success("Committed")

        sha_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if sha_result.returncode == 0:
            console.print(f"  [{BRAND_MUTED}]{sha_result.stdout.strip()}[/]")

    except Exception as e:
        print_error(f"Commit failed: {e}")
        raise typer.Exit(1)


@app.command("push")
def push_commits():
    """
    Push commits to remote.

    Examples:
        repr push
    """
    import subprocess
    from .change_synthesis import get_repo

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Check for unpushed commits
    try:
        result = subprocess.run(
            ["git", "log", "@{u}..", "--oneline"],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # No upstream, just push
            pass
        elif not result.stdout.strip():
            print_info("Nothing to push")
            raise typer.Exit(0)
        else:
            commits = result.stdout.strip().split("\n")
            console.print(f"[bold]Pushing {len(commits)} commits[/]")
            for c in commits[:5]:
                console.print(f"  [{BRAND_MUTED}]{c}[/]")
            if len(commits) > 5:
                console.print(f"  [{BRAND_MUTED}]... +{len(commits) - 5} more[/]")
            console.print()
    except Exception:
        pass

    try:
        with create_spinner("Pushing..."):
            result = subprocess.run(
                ["git", "push"],
                cwd=repo.working_dir,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            if "no upstream branch" in result.stderr:
                # Try push with -u
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=repo.working_dir,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                with create_spinner(f"Setting upstream and pushing {branch}..."):
                    result = subprocess.run(
                        ["git", "push", "-u", "origin", branch],
                        cwd=repo.working_dir,
                        capture_output=True,
                        text=True,
                    )
                if result.returncode != 0:
                    print_error(f"Push failed: {result.stderr}")
                    raise typer.Exit(1)
            else:
                print_error(f"Push failed: {result.stderr}")
                raise typer.Exit(1)

        print_success("Pushed")

    except Exception as e:
        print_error(f"Push failed: {e}")
        raise typer.Exit(1)


PR_SYSTEM = """You generate GitHub PR titles and descriptions. Given the commits, output JSON:

{
  "title": "<type>: <short description>",
  "body": "## Summary\\n<bullet points>\\n\\n## Changes\\n<bullet points>"
}

Rules:
- Title: under 72 chars, conventional commit style
- Body: markdown, concise bullet points
- Focus on what and why, not how

Output only valid JSON."""

PR_USER = """Generate PR title and description for these commits:

{commits}"""


@app.command("pr")
def create_pr(
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Custom PR title"),
    draft: bool = typer.Option(False, "--draft", "-d", help="Create as draft PR"),
    regenerate: bool = typer.Option(False, "--regenerate", "-r", help="Regenerate title/body"),
):
    """
    Create a pull request with AI-generated title and description.

    Examples:
        repr pr                    # AI generates title/body
        repr pr -t "feat: add X"   # Custom title
        repr pr --draft            # Create draft PR
    """
    import subprocess
    from .change_synthesis import get_repo, get_unpushed_commits, format_commit_changes

    repo = get_repo(Path.cwd())
    if not repo:
        print_error("Not a git repository")
        raise typer.Exit(1)

    # Check gh is installed
    gh_check = subprocess.run(["which", "gh"], capture_output=True)
    if gh_check.returncode != 0:
        print_error("GitHub CLI (gh) not installed")
        print_info("Install: brew install gh")
        raise typer.Exit(1)

    # Get current branch
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo.working_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if current_branch in ("main", "master"):
        print_error(f"Cannot create PR from {current_branch}")
        print_info("Create a branch first: repr branch")
        raise typer.Exit(1)

    # Check for unpushed commits
    unpushed = get_unpushed_commits(repo)

    # Get commits for this branch vs main/master
    base_branch = "main"
    check_main = subprocess.run(
        ["git", "rev-parse", "--verify", "main"],
        cwd=repo.working_dir,
        capture_output=True,
    )
    if check_main.returncode != 0:
        base_branch = "master"

    log_result = subprocess.run(
        ["git", "log", f"{base_branch}..HEAD", "--oneline"],
        cwd=repo.working_dir,
        capture_output=True,
        text=True,
    )
    commits_text = log_result.stdout.strip()

    if not commits_text:
        print_warning("No commits to create PR from")
        raise typer.Exit(0)

    commits_list = commits_text.split("\n")
    console.print(f"[bold]PR for {len(commits_list)} commits[/]")
    for c in commits_list[:5]:
        console.print(f"  [{BRAND_MUTED}]{c}[/]")
    if len(commits_list) > 5:
        console.print(f"  [{BRAND_MUTED}]... +{len(commits_list) - 5} more[/]")
    console.print()

    # Push if needed
    if unpushed:
        console.print(f"[{BRAND_MUTED}]Pushing {len(unpushed)} unpushed commits...[/]")
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", current_branch],
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if push_result.returncode != 0:
            print_error(f"Push failed: {push_result.stderr}")
            raise typer.Exit(1)

    # Generate or use provided title/body
    pr_title = title
    pr_body = None

    if not pr_title:
        from .openai_analysis import get_openai_client

        client = get_openai_client()
        if not client:
            print_error("LLM not configured. Run `repr llm setup` first, or use -t")
            raise typer.Exit(1)

        prompt = PR_USER.format(commits=commits_text)

        with create_spinner("Generating PR..."):
            response = asyncio.run(client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": PR_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            ))
            data = json.loads(response.choices[0].message.content)
            pr_title = data.get("title", current_branch)
            pr_body = data.get("body", "")

    console.print(f"[bold]Title:[/] {pr_title}")
    if pr_body:
        console.print(f"[bold]Body:[/]")
        for line in pr_body.split("\n")[:5]:
            console.print(f"  [{BRAND_MUTED}]{line}[/]")
    console.print()

    # Create PR
    cmd = ["gh", "pr", "create", "--title", pr_title, "--base", base_branch]
    if pr_body:
        cmd.extend(["--body", pr_body])
    if draft:
        cmd.append("--draft")

    try:
        result = subprocess.run(
            cmd,
            cwd=repo.working_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_error(f"PR creation failed: {result.stderr}")
            raise typer.Exit(1)

        pr_url = result.stdout.strip()
        print_success("PR created")
        console.print(f"  {pr_url}")

    except Exception as e:
        print_error(f"PR creation failed: {e}")
        raise typer.Exit(1)


# Entry point
if __name__ == "__main__":
    app()
