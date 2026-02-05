"""
CLI commands for project management.

Usage:
    repr project list                           # List all configured projects
    repr project add <path>                     # Add a project interactively
    repr project set <name> <key> <value>       # Update project settings
    repr project remove <name>                  # Remove a project
    repr project default <name>                 # Set default project
    repr project detect                         # Auto-detect projects from repos
"""

import typer
from pathlib import Path
from typing import Optional, List

from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .ui import (
    console,
    print_success,
    print_error,
    print_warning,
    print_info,
    create_spinner,
    BRAND_PRIMARY,
    BRAND_SUCCESS,
    BRAND_WARNING,
    BRAND_ERROR,
    BRAND_MUTED,
)
from .projects import (
    list_projects,
    add_project,
    update_project,
    remove_project,
    get_project,
    set_default_project,
    get_default_project,
    auto_detect_projects,
    VALID_TIMEFRAMES,
)


project_app = typer.Typer(help="Manage projects for social post generation")


@project_app.command("list")
def list_projects_cmd(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List all configured projects.
    
    Shows name, path, platforms, timeframe, and default status.
    """
    import json
    
    projects = list_projects()
    
    if output_json:
        console.print(json.dumps(projects, indent=2, default=str))
        return
    
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Configured Projects[/]")
    console.print()
    
    if not projects:
        print_info("No projects configured yet.")
        print_info("Add a project: repr project add <path>")
        print_info("Auto-detect: repr project detect")
        return
    
    table = Table(show_header=True, header_style=f"bold {BRAND_PRIMARY}")
    table.add_column("Name", style="bold", width=15)
    table.add_column("Path", width=35)
    table.add_column("Platforms", width=20)
    table.add_column("Timeframe", width=10)
    table.add_column("Default", width=8)
    
    for p in projects:
        path = p.get("path", "")
        # Shorten path for display
        if len(path) > 35:
            path = "..." + path[-32:]
        
        platforms = ", ".join(p.get("platforms", [])[:3])
        if len(p.get("platforms", [])) > 3:
            platforms += "..."
        
        default = "★" if p.get("is_default") else ""
        
        table.add_row(
            p["name"],
            path,
            platforms,
            p.get("timeframe", "weekly"),
            f"[{BRAND_SUCCESS}]{default}[/]",
        )
    
    console.print(table)
    console.print()
    console.print(f"[{BRAND_MUTED}]Use 'repr project add <path>' to add a project[/]")


@project_app.command("add")
def add_project_cmd(
    path: str = typer.Argument(..., help="Path to git repository"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name (default: folder name)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Project description"),
    platforms: Optional[str] = typer.Option(None, "--platforms", "-p", help="Comma-separated platforms"),
    timeframe: Optional[str] = typer.Option(None, "--timeframe", "-t", help="Default timeframe (daily, weekly, monthly)"),
    set_default: bool = typer.Option(False, "--default", help="Set as default project"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i", help="Interactive mode"),
):
    """
    Add a project for social post generation.
    
    Examples:
        repr project add ~/code/myproject
        repr project add ~/code/myproject --name "My Project"
        repr project add ~/code/myproject -n myproj -d "A cool project" --default
    """
    # Resolve path
    resolved_path = Path(path).expanduser().resolve()
    
    if not resolved_path.exists():
        print_error(f"Path does not exist: {resolved_path}")
        raise typer.Exit(1)
    
    if not (resolved_path / ".git").exists():
        print_error(f"Not a git repository: {resolved_path}")
        raise typer.Exit(1)
    
    # Determine name
    if not name:
        name = resolved_path.name
        if interactive:
            name = Prompt.ask("Project name", default=name)
    
    # Check if already exists
    existing = get_project(name)
    if existing:
        print_error(f"Project already exists: {name}")
        print_info("Use 'repr project set' to update or 'repr project remove' first")
        raise typer.Exit(1)
    
    # Interactive prompts
    if interactive:
        if not description:
            description = Prompt.ask(
                "Description (optional, for post context)",
                default=""
            ) or None
        
        if not platforms:
            console.print(f"\n[{BRAND_MUTED}]Available platforms: twitter, linkedin, reddit, hackernews, indiehackers[/]")
            platforms_input = Prompt.ask(
                "Platforms (comma-separated, or Enter for all)",
                default=""
            )
            platforms = platforms_input if platforms_input else None
        
        if not timeframe:
            console.print(f"\n[{BRAND_MUTED}]Timeframes: daily, weekly, monthly, 7days, 14days, 30days[/]")
            timeframe = Prompt.ask(
                "Default timeframe",
                default="weekly"
            )
        
        if not set_default and len(list_projects()) == 0:
            set_default = True  # First project becomes default
        elif not set_default:
            set_default = Confirm.ask("Set as default project?", default=False)
    
    # Parse platforms
    platform_list = None
    if platforms:
        platform_list = [p.strip().lower() for p in platforms.split(",")]
    
    # Validate timeframe
    if timeframe and timeframe not in VALID_TIMEFRAMES:
        print_error(f"Invalid timeframe: {timeframe}")
        print_info(f"Valid options: {', '.join(VALID_TIMEFRAMES)}")
        raise typer.Exit(1)
    
    try:
        project = add_project(
            name=name,
            path=str(resolved_path),
            description=description,
            platforms=platform_list,
            timeframe=timeframe or "weekly",
            set_default=set_default,
        )
        
        console.print()
        print_success(f"Added project: {name}")
        console.print(f"  [{BRAND_MUTED}]Path:[/] {project['path']}")
        if project.get("description"):
            console.print(f"  [{BRAND_MUTED}]Description:[/] {project['description']}")
        console.print(f"  [{BRAND_MUTED}]Platforms:[/] {', '.join(project.get('platforms', []))}")
        console.print(f"  [{BRAND_MUTED}]Timeframe:[/] {project.get('timeframe')}")
        if set_default:
            console.print(f"  [{BRAND_SUCCESS}]★ Default project[/]")
        console.print()
        console.print(f"[{BRAND_MUTED}]Generate posts: repr social generate --project {name}[/]")
        
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@project_app.command("set")
def set_project_cmd(
    name: str = typer.Argument(..., help="Project name"),
    key: str = typer.Argument(..., help="Setting key (path, description, platforms, timeframe)"),
    value: str = typer.Argument(..., help="New value"),
):
    """
    Update a project setting.
    
    Keys:
        path        - Path to git repository
        description - Project description
        platforms   - Comma-separated platforms
        timeframe   - Default timeframe
    
    Examples:
        repr project set myproj description "My cool project"
        repr project set myproj platforms "twitter,linkedin"
        repr project set myproj timeframe daily
    """
    project = get_project(name)
    if not project:
        print_error(f"Project not found: {name}")
        raise typer.Exit(1)
    
    valid_keys = ["path", "description", "platforms", "timeframe"]
    if key not in valid_keys:
        print_error(f"Invalid key: {key}")
        print_info(f"Valid keys: {', '.join(valid_keys)}")
        raise typer.Exit(1)
    
    try:
        updates = {}
        
        if key == "platforms":
            updates["platforms"] = [p.strip().lower() for p in value.split(",")]
        else:
            updates[key] = value
        
        updated = update_project(name, **updates)
        
        print_success(f"Updated {name}.{key}")
        console.print(f"  [{BRAND_MUTED}]{key}:[/] {updated.get(key)}")
        
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@project_app.command("remove")
def remove_project_cmd(
    name: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Remove a project configuration.
    
    This only removes the project from repr's config.
    It does not delete any files or stories.
    """
    project = get_project(name)
    if not project:
        print_error(f"Project not found: {name}")
        raise typer.Exit(1)
    
    if not force:
        if not Confirm.ask(f"Remove project '{name}'?"):
            raise typer.Exit(0)
    
    if remove_project(name):
        print_success(f"Removed project: {name}")
    else:
        print_error(f"Failed to remove project: {name}")
        raise typer.Exit(1)


@project_app.command("default")
def set_default_cmd(
    name: str = typer.Argument(..., help="Project name to set as default"),
):
    """
    Set the default project.
    
    The default project is used when no --project flag is provided
    and interactive selection is skipped.
    """
    if not get_project(name):
        print_error(f"Project not found: {name}")
        raise typer.Exit(1)
    
    if set_default_project(name):
        print_success(f"Set default project: {name}")
    else:
        print_error(f"Failed to set default project")
        raise typer.Exit(1)


@project_app.command("detect")
def detect_projects_cmd(
    add_all: bool = typer.Option(False, "--add-all", "-a", help="Add all detected projects"),
):
    """
    Auto-detect projects from tracked repositories.
    
    Shows projects that are tracked but not yet configured for social posts.
    """
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Detecting Projects[/]")
    console.print()
    
    with create_spinner("Scanning tracked repositories..."):
        detected = auto_detect_projects()
    
    if not detected:
        print_info("No new projects detected.")
        print_info("All tracked repositories are already configured.")
        return
    
    console.print(f"Found {len(detected)} unconfigured project(s):\n")
    
    for i, p in enumerate(detected):
        console.print(f"  [{BRAND_PRIMARY}]{i + 1}[/] {p['name']}")
        console.print(f"      [{BRAND_MUTED}]{p['path']}[/]")
        console.print(f"      [{BRAND_MUTED}]Source: {p.get('source', 'unknown')}[/]")
        console.print()
    
    if add_all:
        for p in detected:
            try:
                add_project(
                    name=p["name"],
                    path=p["path"],
                )
                print_success(f"Added: {p['name']}")
            except Exception as e:
                print_warning(f"Failed to add {p['name']}: {e}")
    else:
        console.print(f"[{BRAND_MUTED}]Add a project: repr project add <path>[/]")
        console.print(f"[{BRAND_MUTED}]Add all: repr project detect --add-all[/]")


@project_app.command("show")
def show_project_cmd(
    name: str = typer.Argument(..., help="Project name"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show details for a specific project.
    """
    import json
    from .projects import get_project_git_info
    
    project = get_project(name)
    if not project:
        print_error(f"Project not found: {name}")
        raise typer.Exit(1)
    
    # Add git info
    git_info = get_project_git_info(project.get("path", ""))
    project.update(git_info)
    
    if output_json:
        console.print(json.dumps(project, indent=2, default=str))
        return
    
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]{name}[/]")
    console.print()
    
    console.print(f"  [{BRAND_MUTED}]Path:[/] {project.get('path')}")
    if project.get("description"):
        console.print(f"  [{BRAND_MUTED}]Description:[/] {project.get('description')}")
    console.print(f"  [{BRAND_MUTED}]Platforms:[/] {', '.join(project.get('platforms', []))}")
    console.print(f"  [{BRAND_MUTED}]Timeframe:[/] {project.get('timeframe', 'weekly')}")
    
    if git_info.get("remote_url"):
        console.print(f"  [{BRAND_MUTED}]Remote:[/] {git_info['remote_url']}")
    if git_info.get("branch"):
        console.print(f"  [{BRAND_MUTED}]Branch:[/] {git_info['branch']}")
    
    if project.get("is_default"):
        console.print(f"\n  [{BRAND_SUCCESS}]★ Default project[/]")
    
    console.print()
