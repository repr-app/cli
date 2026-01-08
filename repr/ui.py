"""
Terminal UI utilities for repr CLI.

Simple, focused output helpers using Rich.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

# Brand colors
BRAND_PRIMARY = "#6366f1"  # Indigo
BRAND_SUCCESS = "#22c55e"  # Green
BRAND_WARNING = "#f59e0b"  # Amber
BRAND_ERROR = "#ef4444"    # Red
BRAND_MUTED = "#6b7280"    # Gray

# Console instance
console = Console()


def print_header() -> None:
    """Print the repr header/banner."""
    console.print()
    console.print(f"[bold {BRAND_PRIMARY}]repr[/] - understand what you've actually worked on")
    console.print()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[{BRAND_SUCCESS}]✓[/] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[{BRAND_ERROR}]✗[/] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[{BRAND_WARNING}]⚠[/] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[{BRAND_MUTED}]ℹ[/] {message}")


def print_next_steps(steps: list[str]) -> None:
    """Print next steps suggestions."""
    console.print()
    console.print("[bold]Next steps:[/]")
    for step in steps:
        console.print(f"  {step}")


def print_markdown(content: str) -> None:
    """Print markdown content."""
    md = Markdown(content)
    console.print(md)


def print_panel(title: str, content: str = "", border_color: str = BRAND_PRIMARY) -> None:
    """Print a bordered panel."""
    if content:
        console.print(Panel(content, title=title, border_style=border_color))
    else:
        console.print(Panel(title, border_style=border_color))


def print_auth_code(code: str) -> None:
    """Print an auth code prominently."""
    console.print()
    console.print(Panel(
        f"[bold white on {BRAND_PRIMARY}]  {code}  [/]",
        title="Enter this code",
        border_style=BRAND_PRIMARY,
        padding=(1, 4),
    ))
    console.print()


def create_spinner(message: str = "Working...") -> Progress:
    """Create a spinner progress indicator."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


def create_table(title: str, columns: list[str]) -> Table:
    """Create a styled table."""
    table = Table(title=title, border_style=BRAND_MUTED)
    for col in columns:
        table.add_column(col)
    return table


def format_bytes(size: int) -> str:
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_relative_time(iso_date: str) -> str:
    """Format ISO date as relative time."""
    from datetime import datetime
    
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        delta = now - dt
        
        if delta.days > 365:
            years = delta.days // 365
            return f"{years}y ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months}mo ago"
        elif delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds > 60:
            mins = delta.seconds // 60
            return f"{mins}m ago"
        else:
            return "just now"
    except (ValueError, TypeError):
        return iso_date[:10] if iso_date else "unknown"


def confirm(message: str, default: bool = False) -> bool:
    """Prompt for confirmation."""
    return Confirm.ask(message, default=default)






































