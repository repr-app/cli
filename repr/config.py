"""
Configuration management for ~/.repr/ directory.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================================
# API Configuration
# ============================================================================

# Environment detection
_DEV_MODE = os.getenv("REPR_DEV", "").lower() in ("1", "true", "yes")
_CI_MODE = os.getenv("REPR_CI", "").lower() in ("1", "true", "yes")
_FORCED_MODE = os.getenv("REPR_MODE", "").lower()  # "local" or "cloud"

# Production URLs
PROD_API_BASE = "https://api.repr.dev/api/cli"

# Local development URLs
LOCAL_API_BASE = "http://localhost:8003/api/cli"


def get_api_base() -> str:
    """Get the API base URL based on environment."""
    if env_url := os.getenv("REPR_API_BASE"):
        return env_url
    return LOCAL_API_BASE if _DEV_MODE else PROD_API_BASE


def is_dev_mode() -> bool:
    """Check if running in dev mode."""
    return _DEV_MODE


def is_ci_mode() -> bool:
    """Check if running in CI mode (safe defaults, no prompts)."""
    return _CI_MODE


def get_forced_mode() -> str | None:
    """Get forced mode from environment (local/cloud)."""
    return _FORCED_MODE if _FORCED_MODE in ("local", "cloud") else None


def set_dev_mode(enabled: bool) -> None:
    """Set dev mode programmatically (for CLI --dev flag)."""
    global _DEV_MODE
    _DEV_MODE = enabled


# ============================================================================
# File Configuration
# ============================================================================

# Support REPR_HOME override for multi-user/CI environments
REPR_HOME = Path(os.getenv("REPR_HOME", Path.home() / ".repr"))
CONFIG_DIR = REPR_HOME
CONFIG_FILE = CONFIG_DIR / "config.json"
PROFILES_DIR = CONFIG_DIR / "profiles"
CACHE_DIR = CONFIG_DIR / "cache"
AUDIT_DIR = CONFIG_DIR / "audit"
REPO_HASHES_FILE = CACHE_DIR / "repo-hashes.json"

# Version for config schema migrations
CONFIG_VERSION = 3

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "auth": None,  # Now stores reference to keychain, not token itself
    "profile": {
        "username": None,  # Local username (generated if not set)
        "claimed": False,  # Whether username is verified with repr.dev
        "bio": None,
        "location": None,
        "website": None,
        "twitter": None,
        "linkedin": None,
        "available": False,  # Available for work
    },
    "settings": {
        "default_paths": ["~/code"],
        "skip_patterns": ["node_modules", "venv", ".venv", "vendor", "__pycache__", ".git"],
    },
    "sync": {
        "last_pushed": None,
        "last_profile": None,
    },
    "llm": {
        "default": "local",  # "local", "cloud", or "byok:<provider>"
        "local_provider": None,  # "ollama", "lmstudio", "custom"
        "local_api_url": None,  # Local LLM API base URL (e.g., "http://localhost:11434/v1")
        "local_api_key": None,  # Local LLM API key (often "ollama" for Ollama)
        "local_model": None,  # Model name for local LLM (e.g., "llama3.2")
        "extraction_model": None,  # Model for extracting accomplishments
        "synthesis_model": None,  # Model for synthesizing profile
        "cloud_model": "gpt-4o-mini",  # Default cloud model
        "cloud_send_diffs": False,  # Whether to send diffs to cloud (privacy setting)
        "cloud_redact_paths": True,  # Whether to redact absolute paths
        "cloud_redact_emails": False,  # Whether to redact author emails
        "cloud_redact_patterns": [],  # Regex patterns to redact from commit messages
        "cloud_allowlist_repos": [],  # Only these repos can use cloud (empty = all)
        "byok": {},  # BYOK provider configs: {"openai": {"model": "gpt-4o-mini"}, ...}
    },
    "generation": {
        "batch_size": 5,  # Commits per story
        "auto_generate_on_hook": False,  # Auto-generate when hook runs
        "default_template": "resume",  # Default story template
        "token_limit": 100000,  # Max tokens per cloud request
        "max_commits_per_batch": 50,  # Max commits per request
    },
    "publish": {
        "on_generate": "never",  # "never", "prompt", "always"
        "on_sync": "prompt",  # "never", "prompt", "always"
    },
    "privacy": {
        "lock_local_only": False,  # Disable cloud features entirely
        "lock_permanent": False,  # Make local-only lock irreversible
        "profile_visibility": "public",  # "public", "unlisted", "private"
        "telemetry_enabled": False,  # Opt-in telemetry
    },
    "tracked_repos": [],  # List of {"path": str, "last_sync": str|None, "hook_installed": bool, "paused": bool}
}


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    CONFIG_DIR.mkdir(exist_ok=True)
    PROFILES_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)
    AUDIT_DIR.mkdir(exist_ok=True)


def _atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON to file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Deep merge two dicts, with overlay taking precedence."""
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    """Load configuration from disk, creating default if missing."""
    ensure_directories()
    
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            # Deep merge with defaults for any missing keys
            merged = _deep_merge(DEFAULT_CONFIG, config)
            
            # Check for config migration
            if config.get("version", 1) < CONFIG_VERSION:
                merged = _migrate_config(merged, config.get("version", 1))
                save_config(merged)
            
            return merged
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def _migrate_config(config: dict, from_version: int) -> dict:
    """Migrate config from older version."""
    # Version 2 -> 3: Add BYOK, profile metadata, audit settings
    if from_version < 3:
        # Ensure new sections exist
        if "profile" not in config:
            config["profile"] = DEFAULT_CONFIG["profile"].copy()
        if "publish" not in config:
            config["publish"] = DEFAULT_CONFIG["publish"].copy()
        if "llm" in config:
            config["llm"].setdefault("byok", {})
            config["llm"].setdefault("cloud_redact_emails", False)
            config["llm"].setdefault("cloud_redact_patterns", [])
            config["llm"].setdefault("cloud_allowlist_repos", [])
    
    config["version"] = CONFIG_VERSION
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to disk atomically.
    
    Uses write-to-temp-then-rename pattern to prevent corruption
    if the process is interrupted during write.
    """
    ensure_directories()
    
    # Write to temp file first, then atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2, default=str)
        os.replace(tmp_path, CONFIG_FILE)  # Atomic on POSIX
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def get_config_value(key: str) -> Any:
    """Get a config value by dot-notation key (e.g., 'llm.default')."""
    config = load_config()
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def set_config_value(key: str, value: Any) -> None:
    """Set a config value by dot-notation key (e.g., 'llm.default')."""
    config = load_config()
    parts = key.split(".")
    
    # Navigate to parent
    parent = config
    for part in parts[:-1]:
        if part not in parent:
            parent[part] = {}
        parent = parent[part]
    
    # Set value
    parent[parts[-1]] = value
    save_config(config)


def get_auth() -> dict[str, Any] | None:
    """Get authentication info if available."""
    config = load_config()
    auth = config.get("auth")
    
    if not auth:
        return None
    
    # If using keychain (v3+), retrieve token from keychain
    if auth.get("token_keychain_ref"):
        from .keychain import get_secret
        token = get_secret(auth["token_keychain_ref"])
        if token:
            return {**auth, "access_token": token}
        return None
    
    # Legacy plaintext token
    return auth


def set_auth(
    access_token: str,
    user_id: str,
    email: str,
    litellm_api_key: str | None = None,
) -> None:
    """Store authentication info securely."""
    from .keychain import store_secret
    
    config = load_config()
    
    # Store token in keychain
    keychain_ref = f"auth_token_{user_id[:8]}"
    store_secret(keychain_ref, access_token)
    
    config["auth"] = {
        "token_keychain_ref": keychain_ref,
        "user_id": user_id,
        "email": email,
        "authenticated_at": datetime.now().isoformat(),
    }
    
    if litellm_api_key:
        litellm_ref = f"litellm_key_{user_id[:8]}"
        store_secret(litellm_ref, litellm_api_key)
        config["auth"]["litellm_keychain_ref"] = litellm_ref
    
    save_config(config)


def clear_auth() -> None:
    """Clear authentication info."""
    from .keychain import delete_secret
    
    config = load_config()
    auth = config.get("auth")
    
    if auth:
        # Remove from keychain
        if auth.get("token_keychain_ref"):
            delete_secret(auth["token_keychain_ref"])
        if auth.get("litellm_keychain_ref"):
            delete_secret(auth["litellm_keychain_ref"])
    
    config["auth"] = None
    save_config(config)


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    auth = get_auth()
    return auth is not None and auth.get("access_token") is not None


def get_access_token() -> str | None:
    """Get access token if authenticated."""
    auth = get_auth()
    return auth.get("access_token") if auth else None


def get_litellm_config() -> tuple[str | None, str | None]:
    """Get LiteLLM configuration if available.
    
    Returns:
        Tuple of (litellm_url, litellm_api_key)
    """
    from .keychain import get_secret
    
    auth = get_auth()
    if not auth:
        return None, None
    
    litellm_url = auth.get("litellm_url")
    litellm_key = None
    
    if auth.get("litellm_keychain_ref"):
        litellm_key = get_secret(auth["litellm_keychain_ref"])
    elif auth.get("litellm_api_key"):  # Legacy
        litellm_key = auth["litellm_api_key"]
    
    return litellm_url, litellm_key


# ============================================================================
# Privacy Configuration
# ============================================================================

def is_cloud_allowed() -> bool:
    """Check if cloud operations are allowed.
    
    Cloud is blocked if:
    - privacy.lock_local_only is True
    - REPR_MODE=local is set
    - REPR_CI=true is set
    """
    if _CI_MODE:
        return False
    if _FORCED_MODE == "local":
        return False
    
    config = load_config()
    privacy = config.get("privacy", {})
    return not privacy.get("lock_local_only", False)


def lock_local_only(permanent: bool = False) -> None:
    """Lock to local-only mode.
    
    Args:
        permanent: If True, lock cannot be reversed
    """
    config = load_config()
    config["privacy"]["lock_local_only"] = True
    if permanent:
        config["privacy"]["lock_permanent"] = True
    save_config(config)


def unlock_local_only() -> bool:
    """Unlock from local-only mode.
    
    Returns:
        True if unlocked, False if permanently locked
    """
    config = load_config()
    privacy = config.get("privacy", {})
    
    if privacy.get("lock_permanent"):
        return False
    
    config["privacy"]["lock_local_only"] = False
    save_config(config)
    return True


def get_privacy_settings() -> dict[str, Any]:
    """Get current privacy settings."""
    config = load_config()
    return config.get("privacy", DEFAULT_CONFIG["privacy"])


# ============================================================================
# LLM Configuration
# ============================================================================

def get_llm_config() -> dict[str, Any]:
    """Get LLM configuration.
    
    Returns:
        Dict with full LLM config
    """
    config = load_config()
    return config.get("llm", DEFAULT_CONFIG["llm"])


def set_llm_config(
    extraction_model: str | None = None,
    synthesis_model: str | None = None,
    local_api_url: str | None = None,
    local_api_key: str | None = None,
    local_model: str | None = None,
    default: str | None = None,
) -> None:
    """Set LLM configuration.
    
    Only updates provided values, leaves others unchanged.
    """
    config = load_config()
    if "llm" not in config:
        config["llm"] = DEFAULT_CONFIG["llm"].copy()
    
    if extraction_model is not None:
        config["llm"]["extraction_model"] = extraction_model if extraction_model else None
    if synthesis_model is not None:
        config["llm"]["synthesis_model"] = synthesis_model if synthesis_model else None
    if local_api_url is not None:
        config["llm"]["local_api_url"] = local_api_url if local_api_url else None
    if local_api_key is not None:
        config["llm"]["local_api_key"] = local_api_key if local_api_key else None
    if local_model is not None:
        config["llm"]["local_model"] = local_model if local_model else None
    if default is not None:
        config["llm"]["default"] = default
    
    save_config(config)


def clear_llm_config() -> None:
    """Clear all LLM configuration."""
    config = load_config()
    config["llm"] = DEFAULT_CONFIG["llm"].copy()
    save_config(config)


def get_default_llm_mode() -> str:
    """Get the default LLM mode."""
    config = load_config()
    return config.get("llm", {}).get("default", "local")


# ============================================================================
# BYOK Configuration
# ============================================================================

BYOK_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "name": "Anthropic",
        "default_model": "claude-3-sonnet-20240229",
        "base_url": "https://api.anthropic.com/v1",
    },
    "groq": {
        "name": "Groq",
        "default_model": "llama-3.1-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "together": {
        "name": "Together AI",
        "default_model": "meta-llama/Llama-3-70b-chat-hf",
        "base_url": "https://api.together.xyz/v1",
    },
}


def add_byok_provider(provider: str, api_key: str, model: str | None = None) -> bool:
    """Add a BYOK provider.
    
    Args:
        provider: Provider name (openai, anthropic, etc.)
        api_key: API key for the provider
        model: Optional model override
    
    Returns:
        True if added successfully
    """
    from .keychain import store_secret
    
    if provider not in BYOK_PROVIDERS:
        return False
    
    # Store API key in keychain
    keychain_ref = f"byok_{provider}"
    store_secret(keychain_ref, api_key)
    
    # Update config
    config = load_config()
    if "byok" not in config.get("llm", {}):
        config["llm"]["byok"] = {}
    
    config["llm"]["byok"][provider] = {
        "keychain_ref": keychain_ref,
        "model": model or BYOK_PROVIDERS[provider]["default_model"],
        "send_diffs": False,
        "redact_paths": True,
    }
    
    save_config(config)
    return True


def remove_byok_provider(provider: str) -> bool:
    """Remove a BYOK provider.
    
    Args:
        provider: Provider name
    
    Returns:
        True if removed, False if not found
    """
    from .keychain import delete_secret
    
    config = load_config()
    byok = config.get("llm", {}).get("byok", {})
    
    if provider not in byok:
        return False
    
    # Remove from keychain
    if byok[provider].get("keychain_ref"):
        delete_secret(byok[provider]["keychain_ref"])
    
    del config["llm"]["byok"][provider]
    save_config(config)
    return True


def get_byok_config(provider: str) -> dict[str, Any] | None:
    """Get BYOK configuration for a provider.
    
    Returns:
        Config dict with api_key included, or None if not configured
    """
    from .keychain import get_secret
    
    config = load_config()
    byok = config.get("llm", {}).get("byok", {})
    
    if provider not in byok:
        return None
    
    provider_config = byok[provider].copy()
    
    # Get API key from keychain
    if provider_config.get("keychain_ref"):
        api_key = get_secret(provider_config["keychain_ref"])
        if api_key:
            provider_config["api_key"] = api_key
        else:
            return None  # Key not found
    
    # Add provider info
    if provider in BYOK_PROVIDERS:
        provider_config["base_url"] = BYOK_PROVIDERS[provider]["base_url"]
        provider_config["provider_name"] = BYOK_PROVIDERS[provider]["name"]
    
    return provider_config


def list_byok_providers() -> list[str]:
    """List configured BYOK providers."""
    config = load_config()
    return list(config.get("llm", {}).get("byok", {}).keys())


# ============================================================================
# Profile Configuration
# ============================================================================

def get_profile_config() -> dict[str, Any]:
    """Get profile configuration."""
    config = load_config()
    return config.get("profile", DEFAULT_CONFIG["profile"])


def set_profile_config(**kwargs) -> None:
    """Set profile configuration fields."""
    config = load_config()
    if "profile" not in config:
        config["profile"] = DEFAULT_CONFIG["profile"].copy()
    
    for key, value in kwargs.items():
        if key in DEFAULT_CONFIG["profile"]:
            config["profile"][key] = value
    
    save_config(config)


def get_skip_patterns() -> list[str]:
    """Get list of patterns to skip during discovery."""
    config = load_config()
    return config.get("settings", {}).get("skip_patterns", DEFAULT_CONFIG["settings"]["skip_patterns"])


def update_sync_info(profile_name: str) -> None:
    """Update last sync information."""
    config = load_config()
    config["sync"] = {
        "last_pushed": datetime.now().isoformat(),
        "last_profile": profile_name,
    }
    save_config(config)


def get_sync_info() -> dict[str, Any]:
    """Get sync information."""
    config = load_config()
    return config.get("sync", {})


# ============================================================================
# Profile File Management
# ============================================================================

def list_profiles() -> list[dict[str, Any]]:
    """List all saved profiles with metadata, sorted by modification time (newest first)."""
    ensure_directories()
    
    profiles = []
    for profile_path in sorted(PROFILES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        content = profile_path.read_text()
        
        # Extract basic stats from content
        project_count = content.count("## ") - 1  # Subtract header sections
        if project_count < 0:
            project_count = 0
        
        # Check if synced
        sync_info = get_sync_info()
        is_synced = sync_info.get("last_profile") == profile_path.name
        
        # Load metadata if exists
        metadata = get_profile_metadata(profile_path.stem)
        
        profiles.append({
            "name": profile_path.stem,
            "filename": profile_path.name,
            "path": profile_path,
            "size": profile_path.stat().st_size,
            "modified": datetime.fromtimestamp(profile_path.stat().st_mtime),
            "project_count": project_count,
            "synced": is_synced,
            "repos": metadata.get("repos", []) if metadata else [],
        })
    
    return profiles


def get_latest_profile() -> Path | None:
    """Get path to the latest profile."""
    profiles = list_profiles()
    return profiles[0]["path"] if profiles else None


def get_profile(name: str) -> Path | None:
    """Get path to a specific profile by name."""
    profile_path = PROFILES_DIR / f"{name}.md"
    return profile_path if profile_path.exists() else None


def get_profile_metadata(name: str) -> dict[str, Any] | None:
    """Get metadata for a specific profile by name."""
    metadata_path = PROFILES_DIR / f"{name}.meta.json"
    if not metadata_path.exists():
        return None
    
    try:
        with open(metadata_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_profile(content: str, name: str | None = None, repos: list[dict[str, Any]] | None = None) -> Path:
    """Save a profile to disk with optional metadata (repos as rich objects)."""
    ensure_directories()
    
    if name is None:
        name = datetime.now().strftime("%Y-%m-%d")
    
    # Handle duplicate names by adding suffix
    profile_path = PROFILES_DIR / f"{name}.md"
    counter = 1
    while profile_path.exists():
        profile_path = PROFILES_DIR / f"{name}-{counter}.md"
        counter += 1
    
    profile_path.write_text(content)
    
    # Save metadata if repos provided
    if repos is not None:
        metadata_path = profile_path.with_suffix('.meta.json')
        metadata = {
            "repos": repos,
            "created_at": datetime.now().isoformat(),
        }
        _atomic_json_write(metadata_path, metadata)
    
    return profile_path


def save_repo_profile(content: str, repo_name: str, repo_metadata: dict[str, Any]) -> Path:
    """Save a per-repo profile to disk as {repo_name}_{date}.md."""
    ensure_directories()
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    name = f"{repo_name}_{date_str}"
    
    profile_path = PROFILES_DIR / f"{name}.md"
    counter = 1
    while profile_path.exists():
        profile_path = PROFILES_DIR / f"{name}-{counter}.md"
        counter += 1
    
    profile_path.write_text(content)
    
    metadata_path = profile_path.with_suffix('.meta.json')
    metadata = {
        "repo": repo_metadata,
        "created_at": datetime.now().isoformat(),
    }
    _atomic_json_write(metadata_path, metadata)
    
    return profile_path


# ============================================================================
# Cache Management
# ============================================================================

def load_repo_hashes() -> dict[str, str]:
    """Load cached repository hashes."""
    ensure_directories()
    
    if not REPO_HASHES_FILE.exists():
        return {}
    
    try:
        with open(REPO_HASHES_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_repo_hashes(hashes: dict[str, str]) -> None:
    """Save repository hashes to cache atomically."""
    ensure_directories()
    
    # Write to temp file first, then atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(hashes, f, indent=2)
        os.replace(tmp_path, REPO_HASHES_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def get_repo_hash(repo_path: str) -> str | None:
    """Get cached hash for a repository."""
    hashes = load_repo_hashes()
    return hashes.get(repo_path)


def set_repo_hash(repo_path: str, hash_value: str) -> None:
    """Set cached hash for a repository."""
    hashes = load_repo_hashes()
    hashes[repo_path] = hash_value
    save_repo_hashes(hashes)


def clear_cache() -> None:
    """Clear all cached data."""
    if REPO_HASHES_FILE.exists():
        REPO_HASHES_FILE.unlink()


def get_cache_size() -> int:
    """Get total size of cache directory in bytes."""
    total = 0
    if CACHE_DIR.exists():
        for f in CACHE_DIR.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total


# ============================================================================
# Tracked Repositories Management
# ============================================================================

def get_tracked_repos() -> list[dict[str, Any]]:
    """Get list of tracked repositories.
    
    Returns:
        List of dicts with 'path', 'last_sync', 'hook_installed', 'paused'
    """
    config = load_config()
    return config.get("tracked_repos", [])


def add_tracked_repo(path: str) -> None:
    """Add a repository to tracked list.
    
    Args:
        path: Absolute path to repository
    """
    config = load_config()
    
    # Normalize path
    normalized_path = str(Path(path).expanduser().resolve())
    
    # Check if already tracked
    tracked = config.get("tracked_repos", [])
    for repo in tracked:
        if repo["path"] == normalized_path:
            return  # Already tracked
    
    # Add new repo
    tracked.append({
        "path": normalized_path,
        "last_sync": None,
        "hook_installed": False,
        "paused": False,
    })
    
    config["tracked_repos"] = tracked
    save_config(config)


def remove_tracked_repo(path: str) -> bool:
    """Remove a repository from tracked list.
    
    Args:
        path: Path to repository
    
    Returns:
        True if removed, False if not found
    """
    config = load_config()
    normalized_path = str(Path(path).expanduser().resolve())
    
    tracked = config.get("tracked_repos", [])
    original_len = len(tracked)
    
    # Filter out the repo
    tracked = [r for r in tracked if r["path"] != normalized_path]
    
    if len(tracked) < original_len:
        config["tracked_repos"] = tracked
        save_config(config)
        return True
    
    return False


def update_repo_sync(path: str, timestamp: str | None = None) -> None:
    """Update last sync timestamp for a repository.
    
    Args:
        path: Path to repository
        timestamp: ISO format timestamp (default: now)
    """
    config = load_config()
    normalized_path = str(Path(path).expanduser().resolve())
    
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    tracked = config.get("tracked_repos", [])
    for repo in tracked:
        if repo["path"] == normalized_path:
            repo["last_sync"] = timestamp
            break
    
    config["tracked_repos"] = tracked
    save_config(config)


def set_repo_hook_status(path: str, installed: bool) -> None:
    """Set hook installation status for a repository.
    
    Args:
        path: Path to repository
        installed: Whether hook is installed
    """
    config = load_config()
    normalized_path = str(Path(path).expanduser().resolve())
    
    tracked = config.get("tracked_repos", [])
    for repo in tracked:
        if repo["path"] == normalized_path:
            repo["hook_installed"] = installed
            break
    
    config["tracked_repos"] = tracked
    save_config(config)


def set_repo_paused(path: str, paused: bool) -> None:
    """Set paused status for a repository.
    
    Args:
        path: Path to repository
        paused: Whether auto-tracking is paused
    """
    config = load_config()
    normalized_path = str(Path(path).expanduser().resolve())
    
    tracked = config.get("tracked_repos", [])
    for repo in tracked:
        if repo["path"] == normalized_path:
            repo["paused"] = paused
            break
    
    config["tracked_repos"] = tracked
    save_config(config)


def get_repo_info(path: str) -> dict[str, Any] | None:
    """Get tracking info for a specific repository.
    
    Args:
        path: Path to repository
    
    Returns:
        Repo info dict or None if not tracked
    """
    normalized_path = str(Path(path).expanduser().resolve())
    tracked = get_tracked_repos()
    
    for repo in tracked:
        if repo["path"] == normalized_path:
            return repo
    
    return None


# ============================================================================
# Data Storage Info
# ============================================================================

def get_data_info() -> dict[str, Any]:
    """Get information about local data storage."""
    from .storage import STORIES_DIR, get_story_count
    
    ensure_directories()
    
    # Calculate sizes
    def dir_size(path: Path) -> int:
        total = 0
        if path.exists():
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total
    
    stories_size = dir_size(STORIES_DIR) if STORIES_DIR.exists() else 0
    profiles_size = dir_size(PROFILES_DIR)
    cache_size = dir_size(CACHE_DIR)
    config_size = CONFIG_FILE.stat().st_size if CONFIG_FILE.exists() else 0
    
    return {
        "stories_count": get_story_count(),
        "stories_size": stories_size,
        "profiles_size": profiles_size,
        "cache_size": cache_size,
        "config_size": config_size,
        "total_size": stories_size + profiles_size + cache_size + config_size,
        "paths": {
            "home": str(REPR_HOME),
            "stories": str(STORIES_DIR),
            "profiles": str(PROFILES_DIR),
            "cache": str(CACHE_DIR),
            "config": str(CONFIG_FILE),
        },
    }
