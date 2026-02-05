"""
CLI commands for social posts feature.

Usage:
    repr social generate           # Generate drafts from recent stories
    repr social list               # List drafts
    repr social post <draft_id>    # Post a draft
    repr social connect <platform> # Connect OAuth
    repr social status             # Show connection status
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

import typer
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from ..ui import (
    console,
    print_header,
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

from .models import SocialPlatform, DraftStatus
from .db import get_social_db
from .generator import generate_social_drafts, generate_from_recent_commits
from .oauth import (
    OAuthFlow,
    get_connection_status,
    get_all_connection_statuses,
    disconnect_platform,
)
from .posting import post_draft_sync, PostingError


social_app = typer.Typer(help="Generate and post social content from your stories")


@social_app.command("generate")
def generate_drafts(
    days: int = typer.Option(7, "--days", "-d", help="Look back this many days"),
    platforms: Optional[str] = typer.Option(
        None, "--platforms", "-p",
        help="Comma-separated platforms (twitter,linkedin,reddit,hackernews,indiehackers)"
    ),
    limit: int = typer.Option(5, "--limit", "-l", help="Max stories to process"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use template-only generation"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Generate social media drafts from recent stories.
    
    Examples:
        repr social generate                        # Generate for all platforms
        repr social generate -p twitter,linkedin    # Specific platforms
        repr social generate -d 30 -l 10            # Last 30 days, 10 stories
    """
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Generate Social Drafts[/]")
    console.print()
    
    # Parse platforms
    target_platforms = None
    if platforms:
        target_platforms = []
        for p in platforms.split(","):
            p = p.strip().lower()
            try:
                target_platforms.append(SocialPlatform(p))
            except ValueError:
                print_warning(f"Unknown platform: {p}")
    
    with create_spinner("Generating drafts from recent stories..."):
        try:
            drafts = generate_from_recent_commits(
                days=days,
                platforms=target_platforms,
                use_llm=not no_llm,
                limit=limit,
            )
        except Exception as e:
            print_error(f"Generation failed: {e}")
            raise typer.Exit(1)
    
    if not drafts:
        print_warning("No stories found in the specified time range")
        print_info("Run `repr generate` first to create stories from commits")
        raise typer.Exit(0)
    
    # Save drafts to database
    db = get_social_db()
    for draft in drafts:
        db.save_draft(draft)
    
    if output_json:
        output = [d.model_dump(mode="json") for d in drafts]
        console.print(json.dumps(output, indent=2))
    else:
        print_success(f"Generated {len(drafts)} drafts")
        console.print()
        
        # Group by platform
        by_platform = {}
        for draft in drafts:
            platform = draft.platform.value if isinstance(draft.platform, SocialPlatform) else draft.platform
            if platform not in by_platform:
                by_platform[platform] = []
            by_platform[platform].append(draft)
        
        for platform, platform_drafts in by_platform.items():
            console.print(f"[bold]{platform.upper()}[/] ({len(platform_drafts)} drafts)")
            for draft in platform_drafts[:2]:  # Show first 2
                preview = (draft.content or "")[:100]
                if len(draft.content or "") > 100:
                    preview += "..."
                console.print(f"  [{BRAND_MUTED}]{draft.id[:8]}[/] {preview}")
            if len(platform_drafts) > 2:
                console.print(f"  [{BRAND_MUTED}]... +{len(platform_drafts) - 2} more[/]")
            console.print()
        
        console.print(f"[{BRAND_MUTED}]View all: repr social list[/]")
        console.print(f"[{BRAND_MUTED}]Dashboard: repr dashboard[/]")


@social_app.command("list")
def list_drafts(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Filter by platform"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (draft/posted/failed)"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max drafts to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List social media drafts.
    
    Examples:
        repr social list                      # List all drafts
        repr social list -p twitter           # Twitter drafts only
        repr social list -s draft             # Unpublished drafts
    """
    db = get_social_db()
    
    target_platform = None
    if platform:
        try:
            target_platform = SocialPlatform(platform.lower())
        except ValueError:
            print_error(f"Unknown platform: {platform}")
            raise typer.Exit(1)
    
    target_status = None
    if status:
        try:
            target_status = DraftStatus(status.lower())
        except ValueError:
            print_error(f"Unknown status: {status}")
            raise typer.Exit(1)
    
    drafts = db.list_drafts(
        platform=target_platform,
        status=target_status,
        limit=limit,
    )
    
    if output_json:
        output = [d.model_dump(mode="json") for d in drafts]
        console.print(json.dumps(output, indent=2))
        return
    
    if not drafts:
        print_info("No drafts found")
        print_info("Generate drafts with: repr social generate")
        return
    
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Social Drafts[/] ({len(drafts)} total)")
    console.print()
    
    table = Table(show_header=True, header_style=f"bold {BRAND_PRIMARY}")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Platform", width=12)
    table.add_column("Status", width=10)
    table.add_column("Preview", width=50)
    table.add_column("Created", width=12)
    
    status_colors = {
        "draft": BRAND_PRIMARY,
        "posted": BRAND_SUCCESS,
        "failed": BRAND_ERROR,
        "scheduled": BRAND_WARNING,
    }
    
    for draft in drafts:
        status_str = draft.status.value if isinstance(draft.status, DraftStatus) else draft.status
        status_color = status_colors.get(status_str, BRAND_MUTED)
        
        preview = ""
        if draft.title:
            preview = draft.title[:40]
        elif draft.content:
            preview = draft.content[:40]
        if len(preview) == 40:
            preview += "..."
        
        created = draft.created_at.strftime("%Y-%m-%d") if draft.created_at else "?"
        
        table.add_row(
            draft.id[:10],
            draft.platform.value if isinstance(draft.platform, SocialPlatform) else draft.platform,
            f"[{status_color}]{status_str}[/]",
            preview,
            created,
        )
    
    console.print(table)
    console.print()
    console.print(f"[{BRAND_MUTED}]View draft: repr social show <id>[/]")
    console.print(f"[{BRAND_MUTED}]Post draft: repr social post <id>[/]")


@social_app.command("show")
def show_draft(
    draft_id: str = typer.Argument(..., help="Draft ID (partial match supported)"),
):
    """
    Show full content of a draft.
    """
    db = get_social_db()
    
    # Try exact match first, then partial
    draft = db.get_draft(draft_id)
    if not draft:
        # Try partial match
        all_drafts = db.list_drafts(limit=100)
        matches = [d for d in all_drafts if d.id.startswith(draft_id)]
        if len(matches) == 1:
            draft = matches[0]
        elif len(matches) > 1:
            print_error(f"Multiple drafts match '{draft_id}':")
            for m in matches[:5]:
                console.print(f"  {m.id}")
            raise typer.Exit(1)
        else:
            print_error(f"Draft not found: {draft_id}")
            raise typer.Exit(1)
    
    console.print()
    platform = draft.platform.value if isinstance(draft.platform, SocialPlatform) else draft.platform
    status = draft.status.value if isinstance(draft.status, DraftStatus) else draft.status
    
    console.print(f"[bold {BRAND_PRIMARY}]{platform.upper()}[/] [{BRAND_MUTED}]{status}[/]")
    console.print(f"[{BRAND_MUTED}]ID: {draft.id}[/]")
    console.print()
    
    if draft.title:
        console.print(f"[bold]Title:[/] {draft.title}")
        console.print()
    
    console.print(f"[bold]Content:[/]")
    console.print(Panel(draft.content or "(empty)", border_style=BRAND_MUTED))
    
    if draft.thread_parts:
        console.print(f"\n[bold]Thread ({len(draft.thread_parts)} parts):[/]")
        for i, part in enumerate(draft.thread_parts, 1):
            console.print(f"\n[{BRAND_MUTED}]Part {i + 1}:[/]")
            console.print(Panel(part, border_style=BRAND_MUTED))
    
    if draft.subreddit:
        console.print(f"\n[bold]Subreddit:[/] r/{draft.subreddit}")
    
    if draft.url:
        console.print(f"[bold]URL:[/] {draft.url}")
    
    if draft.post_url:
        console.print(f"\n[{BRAND_SUCCESS}]Posted:[/] {draft.post_url}")
    
    if draft.error_message:
        console.print(f"\n[{BRAND_ERROR}]Error:[/] {draft.error_message}")
    
    console.print()


@social_app.command("post")
def post_single(
    draft_id: str = typer.Argument(..., help="Draft ID to post"),
    force: bool = typer.Option(False, "--force", "-f", help="Post even if already posted"),
):
    """
    Post a draft to its platform.
    
    Requires OAuth connection for the platform.
    """
    db = get_social_db()
    draft = db.get_draft(draft_id)
    
    if not draft:
        # Try partial match
        all_drafts = db.list_drafts(limit=100)
        matches = [d for d in all_drafts if d.id.startswith(draft_id)]
        if len(matches) == 1:
            draft = matches[0]
        else:
            print_error(f"Draft not found: {draft_id}")
            raise typer.Exit(1)
    
    platform = draft.platform.value if isinstance(draft.platform, SocialPlatform) else draft.platform
    
    # Check if already posted
    if draft.status == DraftStatus.POSTED and not force:
        print_warning(f"Draft already posted to {platform}")
        if draft.post_url:
            console.print(f"  {draft.post_url}")
        console.print(f"[{BRAND_MUTED}]Use --force to re-post[/]")
        raise typer.Exit(0)
    
    # Check connection for platforms that support API posting
    if draft.platform in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]:
        conn = get_connection_status(draft.platform)
        if not conn.get("connected"):
            print_error(f"Not connected to {platform}")
            print_info(f"Connect with: repr social connect {platform}")
            raise typer.Exit(1)
    
    console.print()
    console.print(f"[bold]Posting to {platform}...[/]")
    
    try:
        if draft.platform in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]:
            result = post_draft_sync(draft.id)
            print_success("Posted successfully!")
            if result.get("post_url"):
                console.print(f"  {result['post_url']}")
        else:
            # For Reddit, HN, IndieHackers - copy to clipboard
            from .posting import copy_to_clipboard
            import subprocess
            
            text = asyncio.run(copy_to_clipboard(draft))
            
            # Try to copy to clipboard (macOS)
            try:
                process = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                )
                process.communicate(text.encode())
                print_success(f"Content copied to clipboard!")
                console.print(f"[{BRAND_MUTED}]Paste into {platform} manually[/]")
            except Exception:
                # Fallback: print content
                console.print(f"\n[bold]Copy this content:[/]")
                console.print(Panel(text, border_style=BRAND_PRIMARY))
            
            # Mark as "posted" (manual)
            db.update_draft_status(draft.id, DraftStatus.POSTED)
    
    except PostingError as e:
        print_error(f"Posting failed: {e}")
        raise typer.Exit(1)
    
    console.print()


@social_app.command("connect")
def connect_platform(
    platform: str = typer.Argument(..., help="Platform to connect (twitter, linkedin)"),
):
    """
    Connect to a social platform via OAuth.
    
    Opens browser for authorization.
    """
    import webbrowser
    import http.server
    import threading
    import urllib.parse
    
    try:
        target_platform = SocialPlatform(platform.lower())
    except ValueError:
        print_error(f"Unknown platform: {platform}")
        print_info("Supported: twitter, linkedin")
        raise typer.Exit(1)
    
    if target_platform not in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]:
        print_warning(f"{platform} doesn't require OAuth (manual posting)")
        raise typer.Exit(0)
    
    # Check if already connected
    conn = get_connection_status(target_platform)
    if conn.get("connected"):
        print_info(f"Already connected to {platform} as @{conn.get('username')}")
        if not typer.confirm("Reconnect?"):
            raise typer.Exit(0)
    
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Connect to {platform.title()}[/]")
    console.print()
    
    # Create OAuth flow
    flow = OAuthFlow(target_platform)
    auth_url = flow.get_authorization_url()
    
    # Set up callback server
    callback_received = threading.Event()
    callback_data = {"code": None, "state": None, "error": None}
    
    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress logs
        
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            
            callback_data["code"] = params.get("code", [None])[0]
            callback_data["state"] = params.get("state", [None])[0]
            callback_data["error"] = params.get("error", [None])[0]
            
            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            
            if callback_data["error"]:
                self.wfile.write(b"<h1>Authorization Failed</h1><p>You can close this window.</p>")
            else:
                self.wfile.write(b"<h1>Success!</h1><p>You can close this window and return to the terminal.</p>")
            
            callback_received.set()
    
    # Start callback server
    server = http.server.HTTPServer(("localhost", 8765), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()
    
    # Open browser
    console.print(f"[{BRAND_MUTED}]Opening browser for authorization...[/]")
    console.print(f"[{BRAND_MUTED}]If browser doesn't open, visit:[/]")
    console.print(f"  {auth_url[:80]}...")
    console.print()
    
    webbrowser.open(auth_url)
    
    # Wait for callback
    with create_spinner("Waiting for authorization..."):
        callback_received.wait(timeout=300)  # 5 minute timeout
    
    server_thread.join(timeout=1)
    
    if callback_data["error"]:
        print_error(f"Authorization failed: {callback_data['error']}")
        raise typer.Exit(1)
    
    if not callback_data["code"]:
        print_error("Authorization timed out")
        raise typer.Exit(1)
    
    # Exchange code for token
    with create_spinner("Completing authorization..."):
        try:
            connection = asyncio.run(
                flow.exchange_code(callback_data["code"], callback_data["state"])
            )
        except Exception as e:
            print_error(f"Token exchange failed: {e}")
            raise typer.Exit(1)
    
    print_success(f"Connected to {platform}!")
    if connection.platform_username:
        console.print(f"  Logged in as: @{connection.platform_username}")
    console.print()


@social_app.command("disconnect")
def disconnect_platform_cmd(
    platform: str = typer.Argument(..., help="Platform to disconnect"),
):
    """
    Disconnect from a social platform.
    """
    try:
        target_platform = SocialPlatform(platform.lower())
    except ValueError:
        print_error(f"Unknown platform: {platform}")
        raise typer.Exit(1)
    
    disconnect_platform(target_platform)
    print_success(f"Disconnected from {platform}")


@social_app.command("status")
def show_status():
    """
    Show OAuth connection status for all platforms.
    """
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]Social Connections[/]")
    console.print()
    
    statuses = get_all_connection_statuses()
    db = get_social_db()
    stats = db.get_stats()
    
    table = Table(show_header=True, header_style=f"bold {BRAND_PRIMARY}")
    table.add_column("Platform", width=15)
    table.add_column("Status", width=15)
    table.add_column("Account", width=20)
    table.add_column("Drafts", width=10)
    
    platform_drafts = stats.get("drafts_by_platform", {})
    
    for platform in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]:
        status = statuses.get(platform.value, {})
        connected = status.get("connected", False)
        
        status_text = f"[{BRAND_SUCCESS}]Connected[/]" if connected else f"[{BRAND_MUTED}]Not connected[/]"
        account = f"@{status.get('username')}" if status.get("username") else "-"
        draft_count = platform_drafts.get(platform.value, 0)
        
        table.add_row(
            platform.value.title(),
            status_text,
            account,
            str(draft_count),
        )
    
    # Add non-OAuth platforms
    for platform in [SocialPlatform.REDDIT, SocialPlatform.HACKERNEWS, SocialPlatform.INDIEHACKERS]:
        draft_count = platform_drafts.get(platform.value, 0)
        table.add_row(
            platform.value.title(),
            f"[{BRAND_MUTED}]Manual[/]",
            "-",
            str(draft_count),
        )
    
    console.print(table)
    console.print()
    
    # Show draft summary
    total_drafts = stats.get("total_drafts", 0)
    total_posted = stats.get("total_posted", 0)
    
    if total_drafts > 0:
        console.print(f"[bold]Drafts:[/] {total_drafts} total, {total_posted} posted")
        console.print(f"[{BRAND_MUTED}]View with: repr social list[/]")
    else:
        console.print(f"[{BRAND_MUTED}]No drafts yet. Generate with: repr social generate[/]")
    
    console.print()


@social_app.command("delete")
def delete_draft(
    draft_id: str = typer.Argument(..., help="Draft ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    Delete a draft.
    """
    db = get_social_db()
    draft = db.get_draft(draft_id)
    
    if not draft:
        all_drafts = db.list_drafts(limit=100)
        matches = [d for d in all_drafts if d.id.startswith(draft_id)]
        if len(matches) == 1:
            draft = matches[0]
        else:
            print_error(f"Draft not found: {draft_id}")
            raise typer.Exit(1)
    
    if not force:
        preview = (draft.content or "")[:50]
        if not typer.confirm(f"Delete draft '{preview}...'?"):
            raise typer.Exit(0)
    
    db.delete_draft(draft.id)
    print_success("Draft deleted")
