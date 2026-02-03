"""
HTTP server for repr story dashboard.

Serves the Vue dashboard from either:
1. User-installed dashboard (~/.repr/dashboard/) - downloaded from GitHub
2. Bundled dashboard (repr/dashboard/dist/) - ships with CLI
"""

import http.server
import json
import mimetypes
import socketserver
from pathlib import Path

from .manager import get_dashboard_path, check_for_updates

# Dashboard directory - resolved at runtime
_dashboard_dir: Path | None = None


def _get_dashboard_dir() -> Path:
    """Get the dashboard directory, caching the result."""
    global _dashboard_dir
    if _dashboard_dir is None:
        _dashboard_dir = get_dashboard_path()
        if _dashboard_dir is None:
            raise RuntimeError("No dashboard available")
    return _dashboard_dir


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

        # author_name is already stored in the database, no git operations needed

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


def _get_config() -> dict:
    """Get current configuration."""
    from ..config import load_config
    return load_config()


def _save_config(config: dict) -> dict:
    """Save configuration."""
    from ..config import save_config
    save_config(config)
    return {"success": True}


def _get_git_origin(repo_path: Path) -> str | None:
    """Get git remote origin URL for a repository."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _extract_repo_name_from_origin(origin: str | None) -> str | None:
    """Extract username/repo from git origin URL, stripping .git suffix."""
    if not origin:
        return None
    # Handle SSH format: git@github.com:user/repo.git -> user/repo
    if origin.startswith("git@"):
        parts = origin.split(":")
        if len(parts) == 2:
            path = parts[1]
            return path.removesuffix(".git")
    # Handle HTTPS format: https://github.com/user/repo.git -> user/repo
    elif "://" in origin:
        # Split by / and get last two parts (user/repo)
        parts = origin.rstrip("/").split("/")
        if len(parts) >= 2:
            user_repo = "/".join(parts[-2:])
            return user_repo.removesuffix(".git")
    return None


def _get_tracked_repos() -> list[dict]:
    """Get tracked repositories with status, origin, and project info."""
    from ..config import get_tracked_repos
    from ..db import get_db

    repos = get_tracked_repos()
    db = get_db()

    result = []
    for repo in repos:
        repo_info = dict(repo)
        repo_path = Path(repo["path"])

        # Check if path exists
        repo_info["exists"] = repo_path.exists()

        # Get git origin URL
        origin = _get_git_origin(repo_path) if repo_info["exists"] else None
        repo_info["origin"] = origin

        # Extract repo name from origin (without .git)
        origin_name = _extract_repo_name_from_origin(origin)
        repo_info["origin_name"] = origin_name

        # Get associated project info from database
        project = db.get_project_by_path(repo_path)
        if project:
            repo_info["project"] = {
                "id": project["id"],
                "name": project["name"],
                "last_generated": project.get("last_generated"),
                "last_commit_sha": project.get("last_commit_sha"),
            }
        else:
            repo_info["project"] = None

        result.append(repo_info)
    return result


def _add_tracked_repo(path: str) -> dict:
    """Add a repository to tracking."""
    from ..config import add_tracked_repo
    repo_path = Path(path).expanduser().resolve()
    if not (repo_path / ".git").exists():
        return {"success": False, "error": "Not a git repository"}
    add_tracked_repo(str(repo_path))
    return {"success": True}


def _remove_tracked_repo(path: str) -> dict:
    """Remove a repository from tracking."""
    from ..config import remove_tracked_repo
    remove_tracked_repo(path)
    return {"success": True}


def _set_repo_paused(path: str, paused: bool) -> dict:
    """Pause or resume a repository."""
    from ..config import set_repo_paused
    set_repo_paused(path, paused)
    return {"success": True}


def _rename_repo_project(path: str, name: str) -> dict:
    """Rename a repository's project."""
    from pathlib import Path as PathlibPath
    from ..db import get_db

    if not name or not name.strip():
        return {"success": False, "error": "Name cannot be empty"}

    db = get_db()
    repo_path = PathlibPath(path).expanduser().resolve()
    db.register_project(repo_path, name.strip())
    return {"success": True}


def _get_cron_status() -> dict:
    """Get cron job status."""
    from ..config import load_config
    config = load_config()
    cron_config = config.get("cron", {})
    return {
        "installed": cron_config.get("installed", False),
        "paused": cron_config.get("paused", False),
        "interval_hours": cron_config.get("interval_hours"),
        "min_commits": cron_config.get("min_commits"),
    }


class TimelineHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for story dashboard."""

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self):
        if self.path.startswith("/api/"):
            if self.path == "/api/stories":
                self.serve_stories()
            elif self.path.startswith("/api/diff"):
                self.serve_diff()
            elif self.path == "/api/status":
                self.serve_status()
            elif self.path == "/api/config":
                self.serve_config()
            elif self.path == "/api/repos":
                self.serve_repos()
            elif self.path == "/api/cron":
                self.serve_cron()
            else:
                self.send_error(404, "API Endpoint Not Found")
        elif "." in self.path.split("/")[-1]:
            # Serve static files if path looks like a file
            self.serve_static()
        else:
            # SPA fallback - serve index.html for all other routes
            self.serve_dashboard()

    def do_PUT(self):
        if self.path == "/api/config":
            self.update_config()
        else:
            self.send_error(404, "API Endpoint Not Found")

    def do_POST(self):
        if self.path == "/api/repos/add":
            self.add_repo()
        elif self.path == "/api/repos/remove":
            self.remove_repo()
        elif self.path == "/api/repos/pause":
            self.pause_repo()
        elif self.path == "/api/repos/resume":
            self.resume_repo()
        elif self.path == "/api/repos/rename":
            self.rename_repo()
        elif self.path == "/api/generate":
            self.trigger_generation()
        else:
            self.send_error(404, "API Endpoint Not Found")

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def serve_dashboard(self):
        try:
            dashboard_dir = _get_dashboard_dir()
            index_path = dashboard_dir / "index.html"

            if index_path.exists():
                content = index_path.read_text(encoding="utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(content.encode("utf-8")))
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            else:
                self.send_error(404, f"Dashboard index.html not found at {index_path}")
        except Exception as e:
            self.send_error(500, str(e))

    def serve_static(self):
        """Serve static files from dashboard directory."""
        try:
            dashboard_dir = _get_dashboard_dir()
            clean_path = self.path.lstrip("/")
            file_path = (dashboard_dir / clean_path).resolve()

            # Security check: ensure path is within dashboard dir
            if not str(file_path).startswith(str(dashboard_dir.resolve())):
                self.send_error(403, "Access denied")
                return

            # Block sensitive files
            if file_path.suffix == ".py" or file_path.name.startswith("."):
                self.send_error(403, "Access denied")
                return

            if not file_path.exists() or not file_path.is_file():
                self.send_error(404, "File not found")
                return

            content_type, _ = mimetypes.guess_type(file_path)
            content_type = content_type or "application/octet-stream"

            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "max-age=31536000, immutable")  # Cache static assets
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

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
            query = parse_qs(urlparse(self.path).query)
            story_id = query.get("story_id", [None])[0]

            if not story_id:
                self.send_error(400, "Missing story_id")
                return

            db = get_db()
            story = db.get_story(story_id)
            if not story:
                self.send_error(404, "Story not found")
                return
            
            project = db.get_project_by_id(story.project_id)
            if not project:
                self.send_error(404, "Project not found")
                return
            
            project_path = Path(project["path"])
            if not project_path.exists():
                self.send_error(404, "Repository path not found")
                return

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

    def serve_config(self):
        """Serve current configuration."""
        try:
            config = _get_config()
            body = json.dumps(config)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def update_config(self):
        """Update configuration."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            new_config = json.loads(body.decode())
            result = _save_config(new_config)
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def serve_repos(self):
        """Serve tracked repositories."""
        try:
            repos = _get_tracked_repos()
            body = json.dumps({"repos": repos})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def add_repo(self):
        """Add a repository to tracking."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _add_tracked_repo(data.get("path", ""))
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def remove_repo(self):
        """Remove a repository from tracking."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _remove_tracked_repo(data.get("path", ""))
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def pause_repo(self):
        """Pause a repository."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _set_repo_paused(data.get("path", ""), True)
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def resume_repo(self):
        """Resume a repository."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _set_repo_paused(data.get("path", ""), False)
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def rename_repo(self):
        """Rename a repository's project."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _rename_repo_project(data.get("path", ""), data.get("name", ""))
            response = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_cron(self):
        """Serve cron status."""
        try:
            status = _get_cron_status()
            body = json.dumps(status)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def trigger_generation(self):
        """Trigger story generation background process."""
        import subprocess
        import sys
        
        try:
            # We use Popen to run it in background so we can return immediately
            # Using same python executable
            cmd = [sys.executable, "-m", "repr", "generate"]
            
            # Check config for cloud mode preferences, but default to safe (local) if unsure
            config = _get_config()
            # If default mode is cloud AND user is allowed, we could add --cloud
            # But safer to just let CLI logic handle defaults (it defaults to local if not auth)
            # Maybe add --batch-size from config?
            if config.get("generation", {}).get("batch_size"):
                cmd.extend(["--batch-size", str(config["generation"]["batch_size"])])

            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            response = json.dumps({"success": True, "message": "Generation started in background"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response.encode()))
            self.end_headers()
            self.wfile.write(response.encode())
        except Exception as e:
            self.send_error(500, str(e))


def run_server(port: int, host: str, skip_update_check: bool = False) -> None:
    """
    Start the dashboard HTTP server.

    Args:
        port: Port to listen on
        host: Host to bind to
        skip_update_check: If True, skip checking for dashboard updates
    """
    global _dashboard_dir

    # Check for updates (non-blocking, best-effort)
    if not skip_update_check:
        try:
            check_for_updates(quiet=True)
        except Exception:
            pass  # Don't fail startup if update check fails

    # Ensure dashboard is available
    from .manager import ensure_dashboard
    #_dashboard_dir = ensure_dashboard()

    handler = TimelineHandler
    with socketserver.TCPServer((host, port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass