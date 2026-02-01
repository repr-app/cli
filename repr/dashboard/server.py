"""
HTTP server for repr story dashboard.
"""

import http.server
import json
import socketserver
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _get_stories_from_db() -> list[dict]:
    """Get stories from SQLite database."""
    from ..db import get_db

    db = get_db()
    # Create project mapping
    projects = db.list_projects()
    project_map = {p["id"]: p["name"] for p in projects}

    stories = db.list_stories(limit=500)

    result = []
    for story in stories:
        story_dict = story.model_dump()
        # Enrich with repo name
        story_dict["repo_name"] = project_map.get(story_dict.get("project_id"), "unknown")
        
        # Convert datetime objects to ISO strings
        for key in ["created_at", "updated_at", "started_at", "ended_at"]:
            if story_dict.get(key):
                story_dict[key] = story_dict[key].isoformat()
        result.append(story_dict)

    return result


def _get_stats_from_db() -> dict:
    """Get stats from SQLite database."""
    from ..db import get_db

    db = get_db()
    stats = db.get_stats()

    return {
        "count": stats["story_count"],
        "last_updated": None,
        "categories": stats["categories"],
        "files": stats["unique_files"],
        "repos": stats["project_count"],
    }


class TimelineHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for story dashboard."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_dashboard()
        elif self.path == "/api/stories":
            self.serve_stories()
        elif self.path == "/api/status":
            self.serve_status()
        else:
            self.send_error(404, "Not Found")

    def serve_dashboard(self):
        html = get_dashboard_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html.encode()))
        self.end_headers()
        self.wfile.write(html.encode())

    def serve_stories(self):
        try:
            stories = _get_stories_from_db()
            response = {"stories": stories}
            body = json.dumps(response)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_status(self):
        try:
            stats = _get_stats_from_db()
            body = json.dumps(stats)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception:
            self.send_error(500, "Error loading stats")


def run_server(port: int, host: str) -> None:
    """
    Start the dashboard HTTP server.

    Reads stories from central SQLite database at ~/.repr/stories.db.
    """
    handler = TimelineHandler

    with socketserver.TCPServer((host, port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


# Initialize Jinja2 environment
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)


def get_dashboard_html() -> str:
    """Render the dashboard HTML template."""
    template = _jinja_env.get_template("dashboard.html")
    return template.render()
