"""
LLM detection, configuration, and testing.

Supports:
- Local LLMs: Ollama, LM Studio, custom OpenAI-compatible endpoints
- Cloud: repr.dev managed inference
- BYOK: Bring your own key (OpenAI, Anthropic, etc.)
"""

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class LocalLLMInfo:
    """Information about a detected local LLM."""
    provider: str  # "ollama", "lmstudio", "custom"
    name: str
    url: str
    models: list[str]
    default_model: str | None


@dataclass
class LLMTestResult:
    """Result of LLM connection test."""
    success: bool
    provider: str
    endpoint: str
    model: str | None
    response_time_ms: float | None
    error: str | None


# Known local LLM endpoints
LOCAL_ENDPOINTS = [
    {
        "provider": "ollama",
        "name": "Ollama",
        "url": "http://localhost:11434",
        "api_path": "/v1",
        "models_endpoint": "/api/tags",
    },
    {
        "provider": "lmstudio",
        "name": "LM Studio",
        "url": "http://localhost:1234",
        "api_path": "/v1",
        "models_endpoint": "/v1/models",
    },
]


def detect_local_llm() -> LocalLLMInfo | None:
    """
    Detect available local LLM endpoints.
    
    Returns:
        LocalLLMInfo if found, None otherwise
    """
    for endpoint in LOCAL_ENDPOINTS:
        try:
            # Try to connect and get models
            models_url = f"{endpoint['url']}{endpoint['models_endpoint']}"
            resp = httpx.get(models_url, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Parse models based on provider
                if endpoint["provider"] == "ollama":
                    models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
                else:
                    models = [m.get("id", "") for m in data.get("data", [])]
                
                models = [m for m in models if m]  # Filter empty
                
                return LocalLLMInfo(
                    provider=endpoint["provider"],
                    name=endpoint["name"],
                    url=endpoint["url"],
                    models=models,
                    default_model=models[0] if models else None,
                )
                
        except Exception:
            continue
    
    return None


def detect_all_local_llms() -> list[LocalLLMInfo]:
    """
    Detect all available local LLM endpoints.
    
    Returns:
        List of LocalLLMInfo for all found providers
    """
    found = []
    
    for endpoint in LOCAL_ENDPOINTS:
        try:
            models_url = f"{endpoint['url']}{endpoint['models_endpoint']}"
            resp = httpx.get(models_url, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                
                if endpoint["provider"] == "ollama":
                    models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
                else:
                    models = [m.get("id", "") for m in data.get("data", [])]
                
                models = [m for m in models if m]
                
                found.append(LocalLLMInfo(
                    provider=endpoint["provider"],
                    name=endpoint["name"],
                    url=endpoint["url"],
                    models=models,
                    default_model=models[0] if models else None,
                ))
                
        except Exception:
            continue
    
    return found


def test_local_llm(
    url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLMTestResult:
    """
    Test local LLM connection and generation.
    
    Args:
        url: LLM API base URL (auto-detect if None)
        model: Model to test (use default if None)
        api_key: API key if required
    
    Returns:
        LLMTestResult with test outcome
    """
    import time
    
    # Auto-detect if no URL provided
    if not url:
        detected = detect_local_llm()
        if not detected:
            return LLMTestResult(
                success=False,
                provider="unknown",
                endpoint="",
                model=None,
                response_time_ms=None,
                error="No local LLM detected. Is Ollama or LM Studio running?",
            )
        url = detected.url
        if not model:
            model = detected.default_model
        provider = detected.provider
    else:
        provider = "custom"
    
    # Determine model
    if not model:
        model = "llama3.2"  # Common default
    
    # Test generation
    try:
        start = time.time()
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Use chat completions endpoint
        chat_url = f"{url}/v1/chat/completions"
        
        resp = httpx.post(
            chat_url,
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                "max_tokens": 10,
            },
            timeout=30,
        )
        
        elapsed_ms = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return LLMTestResult(
                success=True,
                provider=provider,
                endpoint=url,
                model=model,
                response_time_ms=elapsed_ms,
                error=None,
            )
        else:
            return LLMTestResult(
                success=False,
                provider=provider,
                endpoint=url,
                model=model,
                response_time_ms=elapsed_ms,
                error=f"HTTP {resp.status_code}: {resp.text[:100]}",
            )
            
    except httpx.ConnectError:
        return LLMTestResult(
            success=False,
            provider=provider,
            endpoint=url,
            model=model,
            response_time_ms=None,
            error=f"Connection failed: {url}",
        )
    except httpx.TimeoutException:
        return LLMTestResult(
            success=False,
            provider=provider,
            endpoint=url,
            model=model,
            response_time_ms=None,
            error="Request timed out (30s)",
        )
    except Exception as e:
        return LLMTestResult(
            success=False,
            provider=provider,
            endpoint=url,
            model=model,
            response_time_ms=None,
            error=str(e),
        )


def test_byok_provider(provider: str, api_key: str, model: str | None = None) -> LLMTestResult:
    """
    Test BYOK provider connection.
    
    Args:
        provider: Provider name (openai, anthropic, etc.)
        api_key: API key
        model: Model to test
    
    Returns:
        LLMTestResult with test outcome
    """
    import time
    from .config import BYOK_PROVIDERS
    
    if provider not in BYOK_PROVIDERS:
        return LLMTestResult(
            success=False,
            provider=provider,
            endpoint="",
            model=model,
            response_time_ms=None,
            error=f"Unknown provider: {provider}",
        )
    
    provider_info = BYOK_PROVIDERS[provider]
    base_url = provider_info["base_url"]
    if not model:
        model = provider_info["default_model"]
    
    try:
        start = time.time()
        
        if provider == "anthropic":
            # Anthropic uses different API format
            resp = httpx.post(
                f"{base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                },
                timeout=30,
            )
        else:
            # OpenAI-compatible API
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                    "max_tokens": 10,
                },
                timeout=30,
            )
        
        elapsed_ms = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return LLMTestResult(
                success=True,
                provider=provider,
                endpoint=base_url,
                model=model,
                response_time_ms=elapsed_ms,
                error=None,
            )
        elif resp.status_code == 401:
            return LLMTestResult(
                success=False,
                provider=provider,
                endpoint=base_url,
                model=model,
                response_time_ms=elapsed_ms,
                error="Invalid API key",
            )
        else:
            return LLMTestResult(
                success=False,
                provider=provider,
                endpoint=base_url,
                model=model,
                response_time_ms=elapsed_ms,
                error=f"HTTP {resp.status_code}: {resp.text[:100]}",
            )
            
    except Exception as e:
        return LLMTestResult(
            success=False,
            provider=provider,
            endpoint=base_url,
            model=model,
            response_time_ms=None,
            error=str(e),
        )


def list_ollama_models(url: str = "http://localhost:11434") -> list[str]:
    """
    List available Ollama models.
    
    Args:
        url: Ollama API URL
    
    Returns:
        List of model names
    """
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        pass
    return []


def list_openai_compatible_models(url: str, api_key: str | None = None) -> list[str]:
    """
    List models from OpenAI-compatible endpoint.
    
    Args:
        url: API base URL
        api_key: Optional API key
    
    Returns:
        List of model IDs
    """
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        resp = httpx.get(f"{url}/v1/models", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
    except Exception:
        pass
    return []


def get_llm_status() -> dict[str, Any]:
    """
    Get comprehensive LLM status.
    
    Returns:
        Dict with local, cloud, and BYOK status
    """
    from .config import (
        get_llm_config,
        get_default_llm_mode,
        list_byok_providers,
        is_authenticated,
        is_cloud_allowed,
    )
    
    llm_config = get_llm_config()
    default_mode = get_default_llm_mode()
    
    # Check local LLM
    local_info = detect_local_llm()
    local_available = local_info is not None
    
    # Check cloud
    cloud_available = is_authenticated() and is_cloud_allowed()
    
    # Check BYOK
    byok_providers = list_byok_providers()
    
    return {
        "default_mode": default_mode,
        "local": {
            "available": local_available,
            "provider": local_info.provider if local_info else None,
            "name": local_info.name if local_info else None,
            "url": local_info.url if local_info else llm_config.get("local_api_url"),
            "model": llm_config.get("local_model") or (local_info.default_model if local_info else None),
            "models_count": len(local_info.models) if local_info else 0,
        },
        "cloud": {
            "available": cloud_available,
            "model": llm_config.get("cloud_model", "gpt-4o-mini"),
            "blocked_reason": None if cloud_available else (
                "Not authenticated" if not is_authenticated() else "Local-only mode enabled"
            ),
        },
        "byok": {
            "providers": byok_providers,
            "count": len(byok_providers),
        },
        "settings": {
            "cloud_send_diffs": llm_config.get("cloud_send_diffs", False),
            "cloud_redact_paths": llm_config.get("cloud_redact_paths", True),
            "cloud_redact_emails": llm_config.get("cloud_redact_emails", False),
        },
    }


def get_effective_llm_mode() -> tuple[str, dict[str, Any]]:
    """
    Get the effective LLM mode that will be used.
    
    Returns:
        Tuple of (mode, config_dict)
        Mode is one of: "local", "cloud", "byok:<provider>"
    """
    from .config import (
        get_default_llm_mode,
        get_llm_config,
        get_byok_config,
        is_authenticated,
        is_cloud_allowed,
        get_forced_mode,
    )
    
    # Check for forced mode
    forced = get_forced_mode()
    if forced:
        if forced == "local":
            llm_config = get_llm_config()
            return "local", {
                "url": llm_config.get("local_api_url"),
                "model": llm_config.get("local_model"),
            }
    
    default_mode = get_default_llm_mode()
    llm_config = get_llm_config()
    
    # Handle BYOK mode
    if default_mode.startswith("byok:"):
        provider = default_mode.split(":", 1)[1]
        byok_config = get_byok_config(provider)
        if byok_config:
            return default_mode, byok_config
        # Fall back to local if BYOK not configured
        default_mode = "local"
    
    # Handle cloud mode
    if default_mode == "cloud":
        if is_authenticated() and is_cloud_allowed():
            return "cloud", {
                "model": llm_config.get("cloud_model", "gpt-4o-mini"),
            }
        # Fall back to local if cloud not available
        default_mode = "local"
    
    # Local mode
    return "local", {
        "url": llm_config.get("local_api_url"),
        "model": llm_config.get("local_model"),
    }






































