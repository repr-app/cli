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
    from ..tools import get_commits_by_shas

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
        print(f"DEBUG: Handling GET request for {self.path}")
        if self.path == "/" or self.path == "/index.html":
            self.serve_dashboard()
        elif self.path == "/api/stories":
            self.serve_stories()
        elif self.path.startswith("/api/diff"):
            print("DEBUG: Routing to serve_diff")
            self.serve_diff()
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

    def serve_diff(self):
        """Serve diff for a story."""
        from urllib.parse import urlparse, parse_qs
        from ..db import get_db
        from ..tools import get_commits_by_shas

        try:
            print(f"Received diff request for path: {self.path}")
            query = parse_qs(urlparse(self.path).query)
            story_id = query.get("story_id", [None])[0]
            print(f"Extracted story_id: {story_id}")

            if not story_id:
                self.send_error(400, "Missing story_id")
                return

            db = get_db()
            story = db.get_story(story_id)
            if not story:
                self.send_error(404, "Story not found")
                return
            
            # Get project path to access git repo
            project = db.get_project_by_id(story.project_id)
            if not project:
                self.send_error(404, "Project not found")
                return
            
            project_path = Path(project["path"])
            if not project_path.exists():
                self.send_error(404, "Repository path not found")
                return

            # Get commits with diffs
            commit_shas = story.commit_shas
            commits = get_commits_by_shas(project_path, commit_shas)

            body = json.dumps({"commits": commits}, default=str)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            print(f"Error serving diff: {e}")
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
