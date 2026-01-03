"""
REST API client for repr.dev endpoints.
"""

import hashlib
from typing import Any

import httpx

from .auth import require_auth, AuthError
from .config import get_api_base


def _get_profile_url() -> str:
    return f"{get_api_base()}/profile"


def _get_repo_profile_url() -> str:
    return f"{get_api_base()}/repo-profile"


def _get_user_url() -> str:
    return f"{get_api_base()}/user"


def _get_stories_url() -> str:
    return f"{get_api_base()}/stories"


def _get_public_settings_url() -> str:
    """Get URL for public profile settings endpoint."""
    # This endpoint is under /api/public not /api/cli
    return f"{get_api_base().replace('/api/cli', '/api/public')}/settings"


class APIError(Exception):
    """API request error."""
    pass


def _get_headers() -> dict[str, str]:
    """Get headers with authentication."""
    token = require_auth()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "repr-cli/0.1.1",
    }


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


async def push_profile(content: str, profile_name: str, analyzed_repos: list[dict[str, Any] | str] | None = None) -> dict[str, Any]:
    """
    Push a profile to repr.dev.
    
    Args:
        content: Markdown content of the profile
        profile_name: Name/identifier of the profile
        analyzed_repos: Optional list of repository metadata (dicts) or names (strings for backward compat)
    
    Returns:
        Response data with profile URL
    
    Raises:
        APIError: If upload fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            # Compute content hash
            content_hash = compute_content_hash(content)
            
            payload = {
                "content": content,
                "name": profile_name,
                "content_hash": content_hash,
            }
            if analyzed_repos is not None:
                payload["analyzed_repos"] = analyzed_repos
            
            response = await client.post(
                _get_profile_url(),
                headers=_get_headers(),
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            elif e.response.status_code == 413:
                raise APIError("Profile too large to upload.")
            else:
                raise APIError(f"Upload failed: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def get_user_profile() -> dict[str, Any] | None:
    """
    Get the user's current profile from the server.
    
    Returns:
        Profile data or None if not found
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                _get_profile_url(),
                headers=_get_headers(),
                timeout=30,
            )
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            raise APIError(f"Failed to get profile: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def get_user_info() -> dict[str, Any]:
    """
    Get current user information.
    
    Returns:
        User info dict
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                _get_user_url(),
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            raise APIError(f"Failed to get user info: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def delete_profile() -> bool:
    """
    Delete the user's profile from the server.
    
    Returns:
        True if deleted successfully
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(
                _get_profile_url(),
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return True
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            elif e.response.status_code == 404:
                return True  # Already deleted
            raise APIError(f"Failed to delete profile: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def push_repo_profile(
    content: str,
    repo_name: str,
    repo_metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Push a single repository profile to repr.dev.
    
    Args:
        content: Markdown content of the profile
        repo_name: Name of the repository
        repo_metadata: Repository metadata (commit_count, languages, etc.)
    
    Returns:
        Response data with profile URL
    
    Raises:
        APIError: If upload fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            content_hash = compute_content_hash(content)
            
            payload = {
                "repo_name": repo_name,
                "content": content,
                "content_hash": content_hash,
                **repo_metadata,
            }
            
            response = await client.post(
                _get_repo_profile_url(),
                headers=_get_headers(),
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            elif e.response.status_code == 413:
                raise APIError("Profile too large to upload.")
            else:
                raise APIError(f"Upload failed: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


def sync_push_profile(content: str, profile_name: str, analyzed_repos: list[str] | None = None) -> dict[str, Any]:
    """
    Synchronous wrapper for push_profile.
    
    Args:
        content: Markdown content of the profile
        profile_name: Name/identifier of the profile
        analyzed_repos: Optional list of repository names analyzed
    
    Returns:
        Response data with profile URL
    """
    import asyncio
    return asyncio.run(push_profile(content, profile_name, analyzed_repos))


def sync_get_user_info() -> dict[str, Any]:
    """
    Synchronous wrapper for get_user_info.
    
    Returns:
        User info dict
    """
    import asyncio
    return asyncio.run(get_user_info())


async def get_stories(
    repo_name: str | None = None,
    since: str | None = None,
    technologies: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Get commit stories from repr.dev.
    
    Args:
        repo_name: Filter by repository name
        since: Filter by date (ISO format or human-readable like "1 week ago")
        technologies: Comma-separated list of technologies to filter by
        limit: Maximum number of stories to return
        offset: Pagination offset
    
    Returns:
        Dict with 'stories' list and 'total' count
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
            }
            if repo_name:
                params["repo_name"] = repo_name
            if since:
                params["since"] = since
            if technologies:
                params["technologies"] = technologies
            
            response = await client.get(
                _get_stories_url(),
                headers=_get_headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            raise APIError(f"Failed to get stories: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def push_story(story_data: dict[str, Any]) -> dict[str, Any]:
    """
    Push a commit story to repr.dev.
    
    Args:
        story_data: Story data including summary, technologies, repo info, etc.
    
    Returns:
        Created/updated story data
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                _get_stories_url(),
                headers=_get_headers(),
                json=story_data,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            raise APIError(f"Failed to push story: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")


async def get_public_profile_settings() -> dict[str, Any]:
    """
    Get the current user's public profile settings.
    
    Returns:
        Dict with username, is_profile_public, profile_url, etc.
    
    Raises:
        APIError: If request fails
        AuthError: If not authenticated
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                _get_public_settings_url(),
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("Session expired. Please run 'repr login' again.")
            raise APIError(f"Failed to get profile settings: {e.response.status_code}")
        except httpx.RequestError as e:
            raise APIError(f"Network error: {str(e)}")
