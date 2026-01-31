"""
Timeline web dashboard module.

Provides a local web server for exploring the unified timeline.
"""

from .server import run_server, get_dashboard_html

__all__ = ["run_server", "get_dashboard_html"]
