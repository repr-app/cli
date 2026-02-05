"""
OAuth flows for social platforms.

Handles OAuth 2.0 authentication for Twitter and LinkedIn.
"""

import asyncio
import hashlib
import secrets
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import httpx

from ..storage import generate_ulid
from .models import (
    SocialPlatform,
    SocialConnection,
    ConnectionStatus,
)
from .db import get_social_db


# OAuth configuration (these would be stored in config in production)
OAUTH_CONFIG = {
    SocialPlatform.TWITTER: {
        "client_id": "",  # Set via config
        "client_secret": "",  # Set via config
        "auth_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
        "scopes": ["tweet.read", "tweet.write", "users.read", "offline.access"],
        "uses_pkce": True,
    },
    SocialPlatform.LINKEDIN: {
        "client_id": "",  # Set via config
        "client_secret": "",  # Set via config
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["r_liteprofile", "w_member_social"],
        "uses_pkce": False,
    },
}

# Callback URL for OAuth (local server)
DEFAULT_CALLBACK_URL = "http://localhost:8765/oauth/callback"


def _generate_pkce_pair() -> Tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = (
        code_challenge
        .hex()
        .encode()
    )
    import base64
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    return code_verifier, code_challenge


def _get_oauth_config(platform: SocialPlatform) -> Dict[str, Any]:
    """Get OAuth config for platform, merged with user config."""
    from ..config import load_config
    
    base_config = OAUTH_CONFIG.get(platform, {}).copy()
    user_config = load_config()
    
    # Check for user-provided OAuth credentials
    social_config = user_config.get("social", {}).get(platform.value, {})
    if social_config.get("client_id"):
        base_config["client_id"] = social_config["client_id"]
    if social_config.get("client_secret"):
        base_config["client_secret"] = social_config["client_secret"]
    
    return base_config


class OAuthFlow:
    """Handles OAuth flow for a platform."""
    
    def __init__(
        self,
        platform: SocialPlatform,
        callback_url: str = DEFAULT_CALLBACK_URL,
    ):
        self.platform = platform
        self.callback_url = callback_url
        self.config = _get_oauth_config(platform)
        self.state = secrets.token_urlsafe(32)
        self.code_verifier: Optional[str] = None
        self.code_challenge: Optional[str] = None
        
        if self.config.get("uses_pkce"):
            self.code_verifier, self.code_challenge = _generate_pkce_pair()
    
    def get_authorization_url(self) -> str:
        """Generate the authorization URL for the user to visit."""
        params = {
            "response_type": "code",
            "client_id": self.config["client_id"],
            "redirect_uri": self.callback_url,
            "scope": " ".join(self.config["scopes"]),
            "state": self.state,
        }
        
        if self.config.get("uses_pkce"):
            params["code_challenge"] = self.code_challenge
            params["code_challenge_method"] = "S256"
        
        return f"{self.config['auth_url']}?{urllib.parse.urlencode(params)}"
    
    async def exchange_code(self, code: str, state: str) -> SocialConnection:
        """Exchange authorization code for access token."""
        if state != self.state:
            raise ValueError("Invalid state parameter")
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.callback_url,
            "client_id": self.config["client_id"],
        }
        
        if self.config.get("client_secret"):
            data["client_secret"] = self.config["client_secret"]
        
        if self.config.get("uses_pkce"):
            data["code_verifier"] = self.code_verifier
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config["token_url"],
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()
        
        # Calculate token expiry
        expires_in = token_data.get("expires_in", 7200)
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Fetch user info
        user_info = await self._fetch_user_info(token_data["access_token"])
        
        connection = SocialConnection(
            id=generate_ulid(),
            platform=self.platform,
            status=ConnectionStatus.CONNECTED,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=token_expires_at,
            platform_user_id=user_info.get("id"),
            platform_username=user_info.get("username"),
            platform_display_name=user_info.get("name"),
            profile_url=user_info.get("profile_url"),
            connected_at=datetime.utcnow(),
        )
        
        # Save to database
        db = get_social_db()
        db.save_connection(connection)
        
        return connection
    
    async def _fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetch user info from platform API."""
        if self.platform == SocialPlatform.TWITTER:
            return await self._fetch_twitter_user(access_token)
        elif self.platform == SocialPlatform.LINKEDIN:
            return await self._fetch_linkedin_user(access_token)
        return {}
    
    async def _fetch_twitter_user(self, access_token: str) -> Dict[str, Any]:
        """Fetch Twitter user info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"user.fields": "id,name,username,profile_image_url"},
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "id": data.get("id"),
                    "username": data.get("username"),
                    "name": data.get("name"),
                    "profile_url": f"https://twitter.com/{data.get('username')}",
                }
        return {}
    
    async def _fetch_linkedin_user(self, access_token: str) -> Dict[str, Any]:
        """Fetch LinkedIn user info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                first_name = data.get("localizedFirstName", "")
                last_name = data.get("localizedLastName", "")
                return {
                    "id": data.get("id"),
                    "username": data.get("id"),  # LinkedIn doesn't have username
                    "name": f"{first_name} {last_name}".strip(),
                    "profile_url": f"https://www.linkedin.com/in/{data.get('id')}",
                }
        return {}


async def refresh_token_if_needed(platform: SocialPlatform) -> Optional[str]:
    """Refresh OAuth token if expired."""
    db = get_social_db()
    connection = db.get_connection(platform)
    
    if not connection:
        return None
    
    # Check if token is expired or about to expire
    if connection.token_expires_at:
        if connection.token_expires_at <= datetime.utcnow() + timedelta(minutes=5):
            # Token expired or expiring soon, refresh it
            if connection.refresh_token:
                try:
                    new_token = await _refresh_oauth_token(platform, connection.refresh_token)
                    if new_token:
                        connection.access_token = new_token["access_token"]
                        connection.refresh_token = new_token.get("refresh_token", connection.refresh_token)
                        connection.token_expires_at = datetime.utcnow() + timedelta(
                            seconds=new_token.get("expires_in", 7200)
                        )
                        connection.status = ConnectionStatus.CONNECTED
                        db.save_connection(connection)
                        return connection.access_token
                except Exception as e:
                    connection.status = ConnectionStatus.EXPIRED
                    connection.error_message = str(e)
                    db.save_connection(connection)
                    return None
            else:
                connection.status = ConnectionStatus.EXPIRED
                db.save_connection(connection)
                return None
    
    return connection.access_token


async def _refresh_oauth_token(platform: SocialPlatform, refresh_token: str) -> Dict[str, Any]:
    """Refresh an OAuth token."""
    config = _get_oauth_config(platform)
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config["client_id"],
    }
    
    if config.get("client_secret"):
        data["client_secret"] = config["client_secret"]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            config["token_url"],
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


def get_connection_status(platform: SocialPlatform) -> Dict[str, Any]:
    """Get current connection status for a platform."""
    db = get_social_db()
    connection = db.get_connection(platform)
    
    if not connection:
        return {
            "platform": platform.value,
            "status": ConnectionStatus.DISCONNECTED.value,
            "connected": False,
        }
    
    return {
        "platform": platform.value,
        "status": connection.status.value,
        "connected": connection.status == ConnectionStatus.CONNECTED,
        "username": connection.platform_username,
        "display_name": connection.platform_display_name,
        "profile_url": connection.profile_url,
        "connected_at": connection.connected_at.isoformat() if connection.connected_at else None,
        "expires_at": connection.token_expires_at.isoformat() if connection.token_expires_at else None,
    }


def disconnect_platform(platform: SocialPlatform) -> bool:
    """Disconnect from a platform."""
    db = get_social_db()
    db.delete_connection(platform)
    return True


def get_all_connection_statuses() -> Dict[str, Any]:
    """Get connection status for all platforms."""
    return {
        platform.value: get_connection_status(platform)
        for platform in [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]
    }
