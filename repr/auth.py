"""
Authentication via device code flow.

Tokens are stored securely in OS keychain (see keychain.py).
"""

import asyncio
import time
from dataclasses import dataclass

import httpx

from .config import set_auth, clear_auth, get_auth, is_authenticated, get_api_base


def _get_device_code_url() -> str:
    return f"{get_api_base()}/device-code"


def _get_token_url() -> str:
    return f"{get_api_base()}/token"

# Polling configuration
POLL_INTERVAL = 5  # seconds
MAX_POLL_TIME = 600  # 10 minutes


@dataclass
class DeviceCodeResponse:
    """Response from device code request."""
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


@dataclass
class TokenResponse:
    """Response from token request."""
    access_token: str
    user_id: str
    email: str
    litellm_api_key: str | None = None  # rf_* token for LLM proxy authentication


class AuthError(Exception):
    """Authentication error."""
    pass


async def request_device_code() -> DeviceCodeResponse:
    """
    Request a new device code for authentication.
    
    Returns:
        DeviceCodeResponse with user code to display
    
    Raises:
        AuthError: If request fails
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                _get_device_code_url(),
                json={"client_id": "repr-cli"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            
            return DeviceCodeResponse(
                device_code=data["device_code"],
                user_code=data["user_code"],
                verification_url=data.get("verification_url", "https://repr.dev/device"),
                expires_in=data.get("expires_in", 600),
                interval=data.get("interval", 5),
            )
        except httpx.HTTPStatusError as e:
            raise AuthError(f"Failed to get device code: {e.response.status_code}")
        except httpx.RequestError as e:
            raise AuthError(f"Network error: {str(e)}")


async def poll_for_token(device_code: str, interval: int = POLL_INTERVAL) -> TokenResponse:
    """
    Poll for access token after user authorizes.
    
    Args:
        device_code: The device code from initial request
        interval: Polling interval in seconds
    
    Returns:
        TokenResponse with access token
    
    Raises:
        AuthError: If polling fails or times out
    """
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        while time.time() - start_time < MAX_POLL_TIME:
            try:
                response = await client.post(
                    _get_token_url(),
                    json={
                        "device_code": device_code,
                        "client_id": "repr-cli",
                    },
                    timeout=30,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return TokenResponse(
                        access_token=data["access_token"],
                        user_id=data["user_id"],
                        email=data["email"],
                        litellm_api_key=data.get("litellm_api_key"),
                    )
                
                if response.status_code == 400:
                    data = response.json()
                    error = data.get("error", "unknown")
                    
                    if error == "authorization_pending":
                        # User hasn't authorized yet, continue polling
                        await asyncio.sleep(interval)
                        continue
                    elif error == "slow_down":
                        # Increase interval
                        interval = min(interval + 5, 30)
                        await asyncio.sleep(interval)
                        continue
                    elif error == "expired_token":
                        raise AuthError("Device code expired. Please try again.")
                    elif error == "access_denied":
                        raise AuthError("Authorization denied by user.")
                    else:
                        raise AuthError(f"Authorization failed: {error}")
                
                response.raise_for_status()
                
            except httpx.RequestError as e:
                # Network error, retry
                await asyncio.sleep(interval)
                continue
        
        raise AuthError("Authorization timed out. Please try again.")


def save_token(token_response: TokenResponse) -> None:
    """
    Save authentication token securely.
    
    Token is stored in OS keychain, config only stores a reference.
    
    Args:
        token_response: Token response from successful auth
    """
    set_auth(
        access_token=token_response.access_token,
        user_id=token_response.user_id,
        email=token_response.email,
        litellm_api_key=token_response.litellm_api_key,
    )


def logout() -> None:
    """Clear authentication and logout.
    
    Removes token from keychain and clears config reference.
    """
    clear_auth()


def get_current_user() -> dict | None:
    """
    Get current authenticated user info.
    
    Returns:
        User info dict or None if not authenticated
    """
    return get_auth()


def require_auth() -> str:
    """
    Get access token, raising error if not authenticated.
    
    Returns:
        Access token
    
    Raises:
        AuthError: If not authenticated
    """
    auth = get_auth()
    if not auth or not auth.get("access_token"):
        raise AuthError("Not authenticated. Run 'repr login' first.")
    return auth["access_token"]


def migrate_plaintext_auth() -> bool:
    """
    Migrate plaintext auth tokens to keychain storage.
    
    Called on first run after upgrade to detect and migrate old tokens.
    
    Returns:
        True if migration occurred
    """
    from .keychain import store_secret
    import json
    from .config import CONFIG_FILE, save_config
    
    if not CONFIG_FILE.exists():
        return False
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        
        auth = config.get("auth")
        if not auth:
            return False
        
        # Check if already migrated (has keychain ref)
        if auth.get("token_keychain_ref"):
            return False
        
        # Check for plaintext token
        plaintext_token = auth.get("access_token")
        if not plaintext_token:
            return False
        
        # Migrate to keychain
        user_id = auth.get("user_id", "unknown")[:8]
        keychain_ref = f"auth_token_{user_id}"
        store_secret(keychain_ref, plaintext_token)
        
        # Update config (remove plaintext, add reference)
        del config["auth"]["access_token"]
        config["auth"]["token_keychain_ref"] = keychain_ref
        
        # Handle litellm key if present
        litellm_key = auth.get("litellm_api_key")
        if litellm_key:
            litellm_ref = f"litellm_key_{user_id}"
            store_secret(litellm_ref, litellm_key)
            del config["auth"]["litellm_api_key"]
            config["auth"]["litellm_keychain_ref"] = litellm_ref
        
        save_config(config)
        return True
        
    except Exception:
        return False


class AuthFlow:
    """
    Manages the device code authentication flow with progress callbacks.
    """
    
    def __init__(
        self,
        on_code_received: callable = None,
        on_progress: callable = None,
        on_success: callable = None,
        on_error: callable = None,
    ):
        self.on_code_received = on_code_received
        self.on_progress = on_progress
        self.on_success = on_success
        self.on_error = on_error
        self._cancelled = False
    
    def cancel(self) -> None:
        """Cancel the authentication flow."""
        self._cancelled = True
    
    async def run(self) -> TokenResponse | None:
        """
        Run the full authentication flow.
        
        Returns:
            TokenResponse if successful, None if cancelled
        """
        try:
            # Request device code
            device_code_response = await request_device_code()
            
            if self.on_code_received:
                self.on_code_received(device_code_response)
            
            # Poll for token
            start_time = time.time()
            interval = device_code_response.interval
            
            async with httpx.AsyncClient() as client:
                while not self._cancelled:
                    elapsed = time.time() - start_time
                    remaining = device_code_response.expires_in - elapsed
                    
                    if remaining <= 0:
                        raise AuthError("Device code expired. Please try again.")
                    
                    if self.on_progress:
                        self.on_progress(remaining)
                    
                    try:
                        response = await client.post(
                            _get_token_url(),
                            json={
                                "device_code": device_code_response.device_code,
                                "client_id": "repr-cli",
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
                                litellm_api_key=data.get("litellm_api_key"),
                            )
                            save_token(token)
                            
                            if self.on_success:
                                self.on_success(token)
                            
                            return token
                        
                        if response.status_code == 400:
                            data = response.json()
                            error = data.get("error", "unknown")
                            
                            if error == "authorization_pending":
                                await asyncio.sleep(interval)
                                continue
                            elif error == "slow_down":
                                interval = min(interval + 5, 30)
                                await asyncio.sleep(interval)
                                continue
                            elif error == "expired_token":
                                raise AuthError("Device code expired. Please try again.")
                            elif error == "access_denied":
                                raise AuthError("Authorization denied by user.")
                        
                    except httpx.RequestError:
                        await asyncio.sleep(interval)
                        continue
                    
                    await asyncio.sleep(interval)
            
            return None  # Cancelled
            
        except AuthError as e:
            if self.on_error:
                self.on_error(e)
            raise
