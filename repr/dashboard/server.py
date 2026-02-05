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
import threading
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
    from ..tools import get_git_user_identity

    db = get_db()
    # Create project mapping
    projects = db.list_projects()
    project_map = {p["id"]: p["name"] for p in projects}
    # Create project path mapping for checking git user per repo
    project_path_map = {p["id"]: Path(p["path"]) for p in projects if p.get("path")}

    # Get current git user identity (global)
    current_user_email, current_user_name = get_git_user_identity()

    stories = db.list_stories(limit=500)

    result = []
    for story in stories:
        story_dict = story.model_dump()
        # Enrich with repo name
        story_dict["repo_name"] = project_map.get(story_dict.get("project_id"), "unknown")

        # author_name is already stored in the database, no git operations needed

        # Check if story is publishable (author matches current git user)
        story_author_email = story_dict.get("author_email", "")
        story_author_name = story_dict.get("author_name", "")
        is_publishable = False

        # Check email match (primary)
        if current_user_email and story_author_email:
            if current_user_email.lower() == story_author_email.lower():
                is_publishable = True

        # Check name match (fallback)
        if not is_publishable and current_user_name and story_author_name:
            if current_user_name.lower() == story_author_name.lower():
                is_publishable = True

        story_dict["is_publishable"] = is_publishable

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


# ============================================================================
# Auth API helpers
# ============================================================================

# Global state for active login flow (only one at a time per dashboard)
_active_login_flow: dict | None = None
_login_flow_lock = threading.Lock()


def _get_auth_status() -> dict:
    """Get current authentication status."""
    from ..config import get_auth, is_authenticated

    if not is_authenticated():
        return {
            "authenticated": False,
            "user": None,
            "token": None,
        }

    auth = get_auth()
    return {
        "authenticated": True,
        "user": {
            "user_id": auth.get("user_id"),
            "email": auth.get("email"),
            "username": auth.get("username"),
            "authenticated_at": auth.get("authenticated_at"),
        },
        "token": auth.get("access_token"),
    }


def _start_login_flow() -> dict:
    """Start device code login flow."""
    global _active_login_flow

    import asyncio
    from ..auth import request_device_code, AuthError

    with _login_flow_lock:
        # Check if already logged in
        from ..config import is_authenticated
        if is_authenticated():
            return {"error": "already_authenticated", "message": "Already logged in"}

        # Check if flow already active
        if _active_login_flow is not None:
            # Return existing flow info
            return {
                "status": "pending",
                "user_code": _active_login_flow["user_code"],
                "verification_url": _active_login_flow["verification_url"],
                "expires_in": _active_login_flow["expires_in"],
            }

        try:
            # Request device code
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                device_code_response = loop.run_until_complete(request_device_code())
            finally:
                loop.close()

            # Store flow state
            _active_login_flow = {
                "device_code": device_code_response.device_code,
                "user_code": device_code_response.user_code,
                "verification_url": device_code_response.verification_url,
                "expires_in": device_code_response.expires_in,
                "interval": device_code_response.interval,
            }

            return {
                "status": "pending",
                "user_code": device_code_response.user_code,
                "verification_url": device_code_response.verification_url,
                "expires_in": device_code_response.expires_in,
            }

        except AuthError as e:
            return {"error": "auth_error", "message": str(e)}
        except Exception as e:
            return {"error": "unknown_error", "message": str(e)}


def _poll_login_status() -> dict:
    """Poll for login completion."""
    global _active_login_flow

    import httpx
    from ..config import get_api_base, is_authenticated
    from ..auth import save_token, TokenResponse
    from ..telemetry import get_device_id
    import platform
    import socket

    with _login_flow_lock:
        # Check if already logged in
        if is_authenticated():
            _active_login_flow = None
            return {"status": "completed", "authenticated": True}

        # Check if flow is active
        if _active_login_flow is None:
            return {"status": "no_flow", "message": "No login flow active"}

        device_code = _active_login_flow["device_code"]

        try:
            # Get device name
            hostname = socket.gethostname()
            system = platform.system()
            device_name = f"{hostname} ({system})"

            # Poll the token endpoint
            token_url = f"{get_api_base()}/token"
            print(f"[DEBUG] Polling token URL: {token_url}")

            with httpx.Client() as client:
                response = client.post(
                    token_url,
                    json={
                        "device_code": device_code,
                        "client_id": "repr-cli",
                        "device_id": get_device_id(),
                        "device_name": device_name,
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    data = response.json()
                    user_data = data.get("user", {})
                    token = TokenResponse(
                        access_token=data["access_token"],
                        user_id=user_data.get("id", ""),
                        email=user_data.get("email", ""),
                        username=user_data.get("username"),
                        litellm_api_key=data.get("litellm_api_key"),
                    )
                    save_token(token)

                    # Clear flow
                    _active_login_flow = None

                    return {
                        "status": "completed",
                        "authenticated": True,
                        "user": {
                            "user_id": token.user_id,
                            "email": token.email,
                            "username": token.username,
                        },
                    }

                if response.status_code == 400:
                    data = response.json()
                    error = data.get("error", "unknown")

                    if error == "authorization_pending":
                        return {"status": "pending", "message": "Waiting for authorization"}
                    elif error == "slow_down":
                        return {"status": "pending", "message": "Slow down, polling too fast"}
                    elif error == "expired_token":
                        _active_login_flow = None
                        return {"status": "expired", "message": "Device code expired"}
                    elif error == "access_denied":
                        _active_login_flow = None
                        return {"status": "denied", "message": "Authorization denied"}
                    else:
                        _active_login_flow = None
                        return {"status": "error", "message": f"Authorization failed: {error}"}

                return {"status": "error", "message": f"Unexpected status: {response.status_code}"}

        except httpx.RequestError as e:
            return {"status": "error", "message": f"Network error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def _cancel_login_flow() -> dict:
    """Cancel active login flow."""
    global _active_login_flow

    with _login_flow_lock:
        if _active_login_flow is None:
            return {"success": True, "message": "No active flow"}

        _active_login_flow = None
        return {"success": True, "message": "Login flow cancelled"}


def _logout() -> dict:
    """Logout current user."""
    global _active_login_flow

    from ..auth import logout
    from ..config import is_authenticated

    with _login_flow_lock:
        _active_login_flow = None

    if not is_authenticated():
        return {"success": True, "message": "Already logged out"}

    logout()
    return {"success": True, "message": "Logged out successfully"}


def _save_auth_token(token_data: dict) -> dict:
    """Save auth token received from frontend direct auth with api.repr.dev."""
    from ..auth import save_token, TokenResponse

    try:
        user = token_data.get("user", {})
        token = TokenResponse(
            access_token=token_data["access_token"],
            user_id=user.get("id", ""),
            email=user.get("email", ""),
            username=user.get("username"),
            litellm_api_key=token_data.get("litellm_api_key"),
        )
        save_token(token)
        return {"success": True, "message": "Token saved successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Username API helpers
# ============================================================================

def _get_username_info() -> dict:
    """Get current username info (local + remote)."""
    from ..config import get_auth, get_profile_config, is_authenticated

    profile = get_profile_config()
    local_username = profile.get("username")
    claimed = profile.get("claimed", False)

    result = {
        "local_username": local_username,
        "claimed": claimed,
        "remote_username": None,
    }

    # If authenticated, get remote username
    if is_authenticated():
        auth = get_auth()
        result["remote_username"] = auth.get("username")
        result["user_id"] = auth.get("user_id")
        result["email"] = auth.get("email")

    return result


def _set_local_username(username: str) -> dict:
    """Set local username (without claiming on server)."""
    from ..config import set_profile_config

    if not username or not username.strip():
        return {"success": False, "error": "Username cannot be empty"}

    username = username.strip().lower()

    # Basic validation
    if len(username) < 3:
        return {"success": False, "error": "Username must be at least 3 characters"}
    if len(username) > 30:
        return {"success": False, "error": "Username must be at most 30 characters"}

    set_profile_config(username=username, claimed=False)
    return {"success": True, "username": username}


def _check_username_availability(username: str) -> dict:
    """Check if username is available on the server."""
    import httpx
    from ..config import get_api_base

    if not username or not username.strip():
        return {"available": False, "reason": "Username cannot be empty"}

    username = username.strip().lower()

    try:
        url = f"{get_api_base()}/username/check/{username}"
        with httpx.Client() as client:
            response = client.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            return {"available": False, "reason": f"Server error: {response.status_code}"}
    except httpx.RequestError as e:
        return {"available": False, "reason": f"Network error: {str(e)}"}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def _claim_username(username: str) -> dict:
    """Claim username on the server."""
    import httpx
    from ..config import get_api_base, get_access_token, set_profile_config, is_authenticated

    if not is_authenticated():
        return {"success": False, "error": "Not authenticated. Please login first."}

    if not username or not username.strip():
        return {"success": False, "error": "Username cannot be empty"}

    username = username.strip().lower()
    token = get_access_token()

    try:
        url = f"{get_api_base()}/username/claim"
        with httpx.Client() as client:
            response = client.post(
                url,
                json={"username": username},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # Update local config
                    set_profile_config(username=username, claimed=True)
                return data
            return {"success": False, "error": f"Server error: {response.status_code}"}
    except httpx.RequestError as e:
        return {"success": False, "error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Visibility API helpers
# ============================================================================

def _get_visibility_settings() -> dict:
    """Get visibility settings from config, with backend fetch if authenticated."""
    from ..config import load_config, is_authenticated, get_access_token, get_api_base
    import httpx

    config = load_config()
    privacy = config.get("privacy", {})

    # Local defaults (all private by default)
    local_settings = {
        "profile": privacy.get("profile_visibility", "private"),
        "repos_default": privacy.get("repos_default_visibility", "private"),
        "stories_default": privacy.get("stories_default_visibility", "private"),
    }

    # Try to fetch from backend if authenticated
    if is_authenticated():
        try:
            token = get_access_token()
            url = f"{get_api_base()}/visibility"
            with httpx.Client() as client:
                response = client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    backend_settings = response.json()
                    # Merge backend settings (they take precedence)
                    return {
                        "profile": backend_settings.get("profile", local_settings["profile"]),
                        "repos_default": backend_settings.get("repos_default", local_settings["repos_default"]),
                        "stories_default": backend_settings.get("stories_default", local_settings["stories_default"]),
                    }
        except Exception:
            pass  # Fall back to local settings

    return local_settings


def _set_visibility_settings(settings: dict) -> dict:
    """Set visibility settings in config and sync to backend if authenticated."""
    from ..config import load_config, save_config, is_authenticated, get_access_token, get_api_base
    import httpx

    config = load_config()
    if "privacy" not in config:
        config["privacy"] = {}

    valid_values = {"public", "private", "connections"}
    update_data = {}

    if "profile" in settings and settings["profile"] in valid_values:
        config["privacy"]["profile_visibility"] = settings["profile"]
        update_data["profile"] = settings["profile"]
    if "repos_default" in settings and settings["repos_default"] in valid_values:
        config["privacy"]["repos_default_visibility"] = settings["repos_default"]
        update_data["repos_default"] = settings["repos_default"]
    if "stories_default" in settings and settings["stories_default"] in valid_values:
        config["privacy"]["stories_default_visibility"] = settings["stories_default"]
        update_data["stories_default"] = settings["stories_default"]

    save_config(config)

    # Sync to backend if authenticated
    backend_synced = False
    if is_authenticated() and update_data:
        try:
            token = get_access_token()
            url = f"{get_api_base()}/visibility"
            with httpx.Client() as client:
                response = client.patch(
                    url,
                    json=update_data,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30,
                )
                backend_synced = response.status_code == 200
        except Exception:
            pass  # Fail silently, local config is still saved

    return {"success": True, "backend_synced": backend_synced}


def _set_story_visibility(story_id: str, visibility: str) -> dict:
    """Set visibility for a specific story."""
    from ..db import get_db

    valid_values = {"public", "private", "connections"}
    if visibility not in valid_values:
        return {"success": False, "error": f"Invalid visibility: {visibility}"}

    db = get_db()
    story = db.get_story(story_id)
    if not story:
        return {"success": False, "error": "Story not found"}

    # Update the story visibility
    db.update_story_visibility(story_id, visibility)
    return {"success": True, "story_id": story_id, "visibility": visibility}


# ============================================================================
# Publish API helpers
# ============================================================================

def _get_stories_to_publish(
    scope: str,
    repo_name: str | None = None,
    story_id: str | None = None,
    include_pushed: bool = False,
) -> list:
    """Get stories to publish based on scope.

    Only returns stories that are publishable by the current git user.
    Stories from other authors are filtered out.
    """
    from ..db import get_db
    from ..tools import get_git_user_identity

    db = get_db()

    # Get current git user identity
    current_user_email, current_user_name = get_git_user_identity()

    def is_publishable(story) -> bool:
        """Check if a story is publishable by the current user."""
        # If we can't determine the current user, don't allow publishing
        if not current_user_email and not current_user_name:
            return False

        story_email = getattr(story, 'author_email', '') or ''
        story_name = getattr(story, 'author_name', '') or ''

        # Check email match (primary)
        if current_user_email and story_email:
            if current_user_email.lower() == story_email.lower():
                return True

        # Check name match (fallback)
        if current_user_name and story_name:
            if current_user_name.lower() == story_name.lower():
                return True

        return False

    if scope == "story" and story_id:
        story = db.get_story(story_id)
        if story and is_publishable(story):
            return [story]
        return []

    elif scope == "repo" and repo_name:
        projects = db.list_projects()
        project_ids = [p["id"] for p in projects if p["name"] == repo_name]
        if not project_ids:
            return []
        # Filter to only publishable stories
        return [s for s in db.list_stories(limit=10000) if s.project_id in project_ids and is_publishable(s)]

    else:  # scope == "all"
        # Filter to only publishable stories
        return [s for s in db.list_stories(limit=10000) if is_publishable(s)]


def _publish_preview(data: dict) -> dict:
    """Preview what would be published.

    Only stories from the current git user are publishable.
    """
    from ..db import get_db
    from ..tools import get_git_user_identity

    scope = data.get("scope", "all")
    repo_name = data.get("repo_name")
    story_id = data.get("story_id")
    include_pushed = data.get("include_pushed", False)

    # Get publishable stories (filtered by current user)
    stories = _get_stories_to_publish(scope, repo_name, story_id, include_pushed)

    # Get total story count (before filtering) for comparison
    db = get_db()
    if scope == "story" and story_id:
        total_count = 1 if db.get_story(story_id) else 0
    elif scope == "repo" and repo_name:
        projects = db.list_projects()
        project_ids = [p["id"] for p in projects if p["name"] == repo_name]
        total_count = len([s for s in db.list_stories(limit=10000) if s.project_id in project_ids])
    else:
        total_count = len(db.list_stories(limit=10000))

    filtered_count = total_count - len(stories)

    # Get current user info for context
    current_user_email, current_user_name = get_git_user_identity()

    return {
        "count": len(stories),
        "total_count": total_count,
        "filtered_count": filtered_count,
        "current_user": current_user_email or current_user_name or "unknown",
        "stories": [
            {
                "id": s.id,
                "title": s.title,
                "visibility": s.visibility or "private",
                "repo_name": getattr(s, "repo_name", None),
            }
            for s in stories[:100]  # Limit preview to 100 stories
        ],
    }


def _publish_stories(data: dict) -> dict:
    """Publish stories to repr.dev.

    Only stories from the current git user are published.
    """
    import asyncio
    from ..api import push_stories_batch, APIError, AuthError
    from ..config import is_authenticated, get_access_token
    from ..db import get_db

    # Check authentication
    if not is_authenticated():
        return {"success": False, "error": "Not authenticated. Please login first."}

    scope = data.get("scope", "all")
    repo_name = data.get("repo_name")
    story_id = data.get("story_id")
    visibility_override = data.get("visibility")
    include_pushed = data.get("include_pushed", False)

    # Get publishable stories (filtered by current user)
    stories = _get_stories_to_publish(scope, repo_name, story_id, include_pushed)

    if not stories:
        # Check if there are stories that were filtered out
        db = get_db()
        if scope == "story" and story_id:
            story = db.get_story(story_id)
            if story:
                return {"success": False, "error": "This story was authored by a different user and cannot be published."}
        return {"success": True, "published_count": 0, "failed_count": 0, "message": "No stories to publish"}

    # Build batch payload
    stories_payload = []
    for story in stories:
        payload = story.model_dump(mode="json")
        # Use override visibility or story's current visibility
        payload["visibility"] = visibility_override or story.visibility or "private"
        payload["client_id"] = story.id
        stories_payload.append(payload)

    try:
        result = asyncio.run(push_stories_batch(stories_payload))
        pushed = result.get("pushed", 0)
        failed = result.get("failed", 0)

        return {
            "success": True,
            "published_count": pushed,
            "failed_count": failed,
        }

    except AuthError as e:
        return {"success": False, "error": f"Authentication error: {str(e)}"}
    except APIError as e:
        return {"success": False, "error": f"API error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Social API helpers
# ============================================================================

def _get_social_drafts(
    platform: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list:
    """Get social drafts from database."""
    from ..social.db import get_social_db
    from ..social.models import SocialPlatform, DraftStatus
    
    db = get_social_db()
    
    target_platform = None
    if platform:
        try:
            target_platform = SocialPlatform(platform)
        except ValueError:
            pass
    
    target_status = None
    if status:
        try:
            target_status = DraftStatus(status)
        except ValueError:
            pass
    
    drafts = db.list_drafts(
        platform=target_platform,
        status=target_status,
        limit=limit,
    )
    
    return [d.model_dump(mode="json") for d in drafts]


def _get_social_draft(draft_id: str) -> dict | None:
    """Get a single draft by ID."""
    from ..social.db import get_social_db
    
    db = get_social_db()
    draft = db.get_draft(draft_id)
    
    if draft:
        return draft.model_dump(mode="json")
    return None


def _generate_social_drafts(data: dict) -> dict:
    """Generate social drafts from recent stories."""
    from ..social.generator import generate_from_recent_commits, generate_from_project
    from ..social.db import get_social_db
    from ..social.models import SocialPlatform
    from ..projects import get_project
    
    days = data.get("days", 7)
    limit = data.get("limit", 5)
    use_llm = data.get("use_llm", True)
    platforms_str = data.get("platforms")
    project_name = data.get("project")  # New: project name
    
    platforms = None
    if platforms_str:
        platforms = []
        for p in platforms_str.split(",") if isinstance(platforms_str, str) else platforms_str:
            try:
                platforms.append(SocialPlatform(p.strip() if isinstance(p, str) else p))
            except ValueError:
                pass
    
    try:
        # If project specified, use project-specific generation
        if project_name:
            project_config = get_project(project_name)
            if not project_config:
                return {"success": False, "error": f"Project not found: {project_name}"}
            
            # Use project's platforms if not explicitly specified
            if not platforms and project_config.get("platforms"):
                platforms = []
                for p in project_config["platforms"]:
                    try:
                        platforms.append(SocialPlatform(p))
                    except ValueError:
                        pass
            
            drafts = generate_from_project(
                project_path=project_config.get("path"),
                days=days,
                platforms=platforms,
                use_llm=use_llm,
                limit=limit,
            )
        else:
            drafts = generate_from_recent_commits(
                days=days,
                platforms=platforms,
                use_llm=use_llm,
                limit=limit,
            )
        
        # Save to database
        db = get_social_db()
        for draft in drafts:
            db.save_draft(draft)
        
        return {
            "success": True,
            "count": len(drafts),
            "drafts": [d.model_dump(mode="json") for d in drafts],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _update_social_draft(draft_id: str, data: dict) -> dict:
    """Update a draft's content."""
    from ..social.db import get_social_db
    
    db = get_social_db()
    draft = db.get_draft(draft_id)
    
    if not draft:
        return {"success": False, "error": "Draft not found"}
    
    db.update_draft_content(
        draft_id,
        title=data.get("title"),
        content=data.get("content"),
        thread_parts=data.get("thread_parts"),
    )
    
    return {"success": True}


def _delete_social_draft(draft_id: str) -> dict:
    """Delete a draft."""
    from ..social.db import get_social_db
    
    db = get_social_db()
    db.delete_draft(draft_id)
    return {"success": True}


def _post_social_draft(draft_id: str, platform: str | None = None) -> dict:
    """Post a draft to its platform."""
    import asyncio
    from ..social.posting import post_draft, PostingError
    from ..social.models import SocialPlatform
    
    target_platform = None
    if platform:
        try:
            target_platform = SocialPlatform(platform)
        except ValueError:
            pass
    
    try:
        result = asyncio.run(post_draft(draft_id, target_platform))
        return result
    except PostingError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_social_connections() -> dict:
    """Get OAuth connection status for all platforms."""
    from ..social.oauth import get_all_connection_statuses
    from ..social.db import get_social_db
    
    statuses = get_all_connection_statuses()
    db = get_social_db()
    stats = db.get_stats()
    
    return {
        "connections": statuses,
        "stats": stats,
    }


def _start_social_oauth(platform: str) -> dict:
    """Start OAuth flow for a platform."""
    from ..social.oauth import OAuthFlow
    from ..social.models import SocialPlatform
    
    try:
        target_platform = SocialPlatform(platform)
    except ValueError:
        return {"success": False, "error": f"Unknown platform: {platform}"}
    
    if target_platform not in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]:
        return {"success": False, "error": f"{platform} doesn't require OAuth"}
    
    flow = OAuthFlow(target_platform)
    auth_url = flow.get_authorization_url()
    
    # Store flow state for callback
    # Note: In a real implementation, this would be stored in a session or cache
    return {
        "success": True,
        "auth_url": auth_url,
        "state": flow.state,
    }


def _disconnect_social_platform(platform: str) -> dict:
    """Disconnect from a social platform."""
    from ..social.oauth import disconnect_platform
    from ..social.models import SocialPlatform
    
    try:
        target_platform = SocialPlatform(platform)
    except ValueError:
        return {"success": False, "error": f"Unknown platform: {platform}"}
    
    disconnect_platform(target_platform)
    return {"success": True}


class TimelineHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for story dashboard."""

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self):
        print(f"[GET] {self.path}")  # Debug log
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
            elif self.path == "/api/auth":
                self.serve_auth_status()
            elif self.path == "/api/auth/login/status":
                self.serve_login_poll()
            elif self.path == "/api/username":
                self.serve_username_info()
            elif self.path.startswith("/api/username/check/"):
                self.check_username()
            elif self.path == "/api/visibility":
                self.serve_visibility_settings()
            elif self.path.startswith("/api/publish/preview"):
                self.serve_publish_preview()
            elif self.path == "/api/version":
                self.serve_version()
            # Social API endpoints
            elif self.path == "/api/social/drafts" or self.path.startswith("/api/social/drafts?"):
                self.serve_social_drafts()
            elif self.path.startswith("/api/social/drafts/") and not self.path.endswith("/post"):
                self.serve_social_draft()
            elif self.path == "/api/social/connections":
                self.serve_social_connections()
            # Projects API endpoints
            elif self.path == "/api/projects":
                self.serve_projects()
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
        print(f"[POST] {self.path}")  # Debug log
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
        elif self.path == "/api/auth/login":
            self.start_login()
        elif self.path == "/api/auth/login/cancel":
            self.cancel_login()
        elif self.path == "/api/auth/save":
            self.save_auth_token()
        elif self.path == "/api/auth/logout":
            self.do_logout()
        elif self.path == "/api/username/set":
            self.set_username()
        elif self.path == "/api/username/claim":
            self.claim_username()
        elif self.path == "/api/visibility":
            self.update_visibility_settings()
        elif self.path.startswith("/api/stories/") and self.path.endswith("/visibility"):
            self.update_story_visibility()
        elif self.path == "/api/publish":
            print("[POST] Matched /api/publish, calling do_publish()")  # Debug log
            self.do_publish()
        elif self.path == "/api/publish/mark-pushed":
            self.mark_stories_pushed()
        # Social API endpoints
        elif self.path == "/api/social/generate":
            self.generate_social_drafts()
        elif self.path.startswith("/api/social/drafts/") and self.path.endswith("/post"):
            self.post_social_draft()
        elif self.path.startswith("/api/social/drafts/") and "/update" in self.path:
            self.update_social_draft()
        elif self.path.startswith("/api/social/drafts/") and "/delete" in self.path:
            self.delete_social_draft()
        elif self.path == "/api/social/connect":
            self.start_social_oauth()
        elif self.path == "/api/social/disconnect":
            self.disconnect_social()
        else:
            print(f"[POST] No match for path: {self.path}")  # Debug log
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

    def serve_version(self):
        """Serve version info and update availability."""
        try:
            from .. import __version__
            from ..updater import check_for_update, get_installation_method

            # Check for updates (cached result to avoid too many API calls)
            update_available = None
            try:
                update_available = check_for_update()
            except Exception:
                pass  # Silently fail if update check fails

            response = {
                "version": __version__,
                "update_available": update_available,
                "installation_method": get_installation_method(),
            }
            body = json.dumps(response)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

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

    # =========================================================================
    # Auth endpoints
    # =========================================================================

    def serve_auth_status(self):
        """Serve current authentication status."""
        try:
            status = _get_auth_status()
            body = json.dumps(status)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def start_login(self):
        """Start device code login flow."""
        try:
            result = _start_login_flow()
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_login_poll(self):
        """Poll for login completion."""
        try:
            result = _poll_login_status()
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def cancel_login(self):
        """Cancel active login flow."""
        try:
            result = _cancel_login_flow()
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def save_auth_token(self):
        """Save auth token from frontend direct auth."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            result = _save_auth_token(data)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def do_logout(self):
        """Logout current user."""
        try:
            result = _logout()
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    # =========================================================================
    # Username endpoints
    # =========================================================================

    def serve_username_info(self):
        """Serve current username info."""
        try:
            info = _get_username_info()
            body = json.dumps(info)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def check_username(self):
        """Check username availability."""
        try:
            # Extract username from path: /api/username/check/{username}
            parts = self.path.split("/")
            username = parts[-1] if len(parts) > 4 else ""

            result = _check_username_availability(username)
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def set_username(self):
        """Set local username."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _set_local_username(data.get("username", ""))
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

    def claim_username(self):
        """Claim username on server."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _claim_username(data.get("username", ""))
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

    # =========================================================================
    # Visibility endpoints
    # =========================================================================

    def serve_visibility_settings(self):
        """Serve visibility settings."""
        try:
            settings = _get_visibility_settings()
            body = json.dumps(settings)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def update_visibility_settings(self):
        """Update visibility settings."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _set_visibility_settings(data)
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

    def update_story_visibility(self):
        """Update visibility for a specific story."""
        try:
            # Extract story_id from path: /api/stories/{story_id}/visibility
            parts = self.path.split("/")
            story_id = parts[3] if len(parts) > 4 else ""

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            result = _set_story_visibility(story_id, data.get("visibility", ""))
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

    # =========================================================================
    # Publish endpoints
    # =========================================================================

    def serve_publish_preview(self):
        """Preview what would be published."""
        from urllib.parse import urlparse, parse_qs

        try:
            query = parse_qs(urlparse(self.path).query)
            data = {
                "scope": query.get("scope", ["all"])[0],
                "repo_name": query.get("repo_name", [None])[0],
                "story_id": query.get("story_id", [None])[0],
                "include_pushed": query.get("include_pushed", ["false"])[0] == "true",
            }

            result = _publish_preview(data)
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def do_publish(self):
        """Publish stories to repr.dev."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}

            result = _publish_stories(data)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def mark_stories_pushed(self):
        """Mark stories as pushed in local DB."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}

            story_ids = data.get("story_ids", [])
            if story_ids:
                from datetime import datetime
                now = datetime.utcnow().isoformat()
                db = _get_db()
                placeholders = ",".join("?" * len(story_ids))
                db.execute(
                    f"UPDATE stories SET pushed_at = ? WHERE id IN ({placeholders})",
                    [now] + story_ids
                )
                db.commit()

            response_body = json.dumps({"success": True, "marked": len(story_ids)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    # =========================================================================
    # Social endpoints
    # =========================================================================

    def serve_social_drafts(self):
        """Serve list of social drafts."""
        from urllib.parse import urlparse, parse_qs
        
        try:
            query = parse_qs(urlparse(self.path).query)
            platform = query.get("platform", [None])[0]
            status = query.get("status", [None])[0]
            limit = int(query.get("limit", [100])[0])
            
            drafts = _get_social_drafts(platform, status, limit)
            body = json.dumps({"drafts": drafts})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_social_draft(self):
        """Serve a single draft."""
        try:
            # Extract draft_id from path: /api/social/drafts/{draft_id}
            parts = self.path.split("/")
            draft_id = parts[4] if len(parts) > 4 else ""
            
            draft = _get_social_draft(draft_id)
            if draft:
                body = json.dumps(draft)
                self.send_response(200)
            else:
                body = json.dumps({"error": "Draft not found"})
                self.send_response(404)
            
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_social_connections(self):
        """Serve social connection status."""
        try:
            result = _get_social_connections()
            body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def serve_projects(self):
        """Serve projects list for social post generation."""
        try:
            from ..projects import list_projects, get_default_project
            
            projects = list_projects()
            default = get_default_project()
            
            result = {
                "projects": projects,
                "default_project": default.get("name") if default else None,
            }
            
            body = json.dumps(result, default=str)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def generate_social_drafts(self):
        """Generate social drafts from stories."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}
            
            result = _generate_social_drafts(data)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def post_social_draft(self):
        """Post a draft to its platform."""
        try:
            # Extract draft_id from path: /api/social/drafts/{draft_id}/post
            parts = self.path.split("/")
            draft_id = parts[4] if len(parts) > 5 else ""
            
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}
            platform = data.get("platform")
            
            result = _post_social_draft(draft_id, platform)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def update_social_draft(self):
        """Update a draft's content."""
        try:
            # Extract draft_id from path: /api/social/drafts/{draft_id}/update
            parts = self.path.split("/")
            draft_id = parts[4] if len(parts) > 5 else ""
            
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}
            
            result = _update_social_draft(draft_id, data)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def delete_social_draft(self):
        """Delete a draft."""
        try:
            # Extract draft_id from path: /api/social/drafts/{draft_id}/delete
            parts = self.path.split("/")
            draft_id = parts[4] if len(parts) > 5 else ""
            
            result = _delete_social_draft(draft_id)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except Exception as e:
            self.send_error(500, str(e))

    def start_social_oauth(self):
        """Start OAuth flow for a platform."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}
            platform = data.get("platform", "")
            
            result = _start_social_oauth(platform)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def disconnect_social(self):
        """Disconnect from a social platform."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}
            platform = data.get("platform", "")
            
            result = _disconnect_social_platform(platform)
            response_body = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(response_body.encode()))
            self.end_headers()
            self.wfile.write(response_body.encode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
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