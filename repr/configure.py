"""
Configuration wizard for repr CLI.

Provides:
- First-run detection
- Interactive setup wizard (LLM → Repos → Schedule)
- Individual configuration commands
"""

import shutil
from pathlib import Path
from typing import Any

import httpx
from rich.prompt import Prompt
from rich.table import Table

from .config import (
    CONFIG_FILE,
    BYOK_PROVIDERS,
    add_byok_provider,
    get_llm_config,
    get_tracked_repos,
    load_config,
    save_config,
    set_llm_config,
    add_tracked_repo,
    set_repo_hook_status,
)
from .keychain import store_secret, get_secret
from .llm import detect_all_local_llms, LocalLLMInfo
from .ui import (
    console,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_next_steps,
    confirm,
    create_spinner,
    BRAND_PRIMARY,
    BRAND_MUTED,
)


# =============================================================================
# PROVIDER DEFINITIONS
# =============================================================================

# Local providers (run on user's machine)
LOCAL_PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "description": "Local, private, free - most popular choice",
        "url": "http://localhost:11434",
        "models_endpoint": "/api/tags",
        "api_style": "openai",
        "install_url": "https://ollama.ai",
    },
    "lmstudio": {
        "name": "LM Studio",
        "description": "Local with GUI model management",
        "url": "http://localhost:1234",
        "models_endpoint": "/v1/models",
        "api_style": "openai",
        "install_url": "https://lmstudio.ai",
    },
}

# API providers (require API key)
API_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "description": "GPT-4, GPT-4o, etc.",
        "base_url": "https://api.openai.com/v1",
        "models_endpoint": "/models",
        "api_style": "openai",
        "auth_methods": ["api_key"],  # Could add "oauth" for codex later
        "default_model": "gpt-4o-mini",
        "env_var": "OPENAI_API_KEY",
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Claude models",
        "base_url": "https://api.anthropic.com/v1",
        "models_endpoint": "/models",
        "api_style": "anthropic",
        "auth_methods": ["api_key", "claude_setup"],
        "default_model": "claude-sonnet-4-20250514",
        "env_var": "ANTHROPIC_API_KEY",
    },
    "gemini": {
        "name": "Google Gemini",
        "description": "Gemini Pro, Flash, etc.",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models_endpoint": "/models",
        "api_style": "gemini",
        "auth_methods": ["api_key"],
        "default_model": "gemini-1.5-flash",
        "env_var": "GEMINI_API_KEY",
    },
    "groq": {
        "name": "Groq",
        "description": "Fast inference for open models",
        "base_url": "https://api.groq.com/openai/v1",
        "models_endpoint": "/models",
        "api_style": "openai",
        "auth_methods": ["api_key"],
        "default_model": "llama-3.1-70b-versatile",
        "env_var": "GROQ_API_KEY",
    },
    "together": {
        "name": "Together AI",
        "description": "Open source models",
        "base_url": "https://api.together.xyz/v1",
        "models_endpoint": "/models",
        "api_style": "openai",
        "auth_methods": ["api_key"],
        "default_model": "meta-llama/Llama-3-70b-chat-hf",
        "env_var": "TOGETHER_API_KEY",
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "Access multiple providers through one API",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "/models",
        "api_style": "openai",
        "auth_methods": ["api_key"],
        "default_model": "anthropic/claude-3.5-sonnet",
        "env_var": "OPENROUTER_API_KEY",
    },
}


# =============================================================================
# FIRST RUN DETECTION
# =============================================================================

def is_first_run() -> bool:
    """
    Check if this is the first run of repr.

    First run is determined by:
    - No config file exists, OR
    - Config exists but no LLM is configured
    """
    if not CONFIG_FILE.exists():
        return True

    config = load_config()
    llm_config = config.get("llm", {})

    # Check if any LLM is configured
    has_local = llm_config.get("local_provider") is not None
    has_byok = bool(llm_config.get("byok", {}))

    return not (has_local or has_byok)


def is_configured() -> bool:
    """Check if repr is fully configured (has LLM)."""
    return not is_first_run()


# =============================================================================
# MODEL LISTING
# =============================================================================

def list_ollama_models(url: str = "http://localhost:11434") -> list[dict[str, Any]]:
    """List available Ollama models with details."""
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if name:
                    models.append({
                        "id": name,
                        "name": name.split(":")[0],  # Remove tag
                        "size": m.get("size", 0),
                        "modified": m.get("modified_at", ""),
                    })
            return models
    except Exception:
        pass
    return []


def list_openai_models(api_key: str, base_url: str = "https://api.openai.com/v1") -> list[dict[str, Any]]:
    """List available OpenAI models."""
    try:
        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                # Filter to chat models
                if any(x in model_id for x in ["gpt", "o1", "o3", "chatgpt"]):
                    models.append({
                        "id": model_id,
                        "name": model_id,
                        "owned_by": m.get("owned_by", ""),
                    })
            return sorted(models, key=lambda x: x["id"])
    except Exception:
        pass
    return []


def list_anthropic_models(api_key: str) -> list[dict[str, Any]]:
    """List available Anthropic models."""
    # Anthropic doesn't have a models list endpoint, return known models
    return [
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
        {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
        {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
    ]


def list_gemini_models(api_key: str) -> list[dict[str, Any]]:
    """List available Gemini models."""
    try:
        resp = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            models = []
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    models.append({
                        "id": name,
                        "name": m.get("displayName", name),
                        "description": m.get("description", ""),
                    })
            return models
    except Exception:
        pass
    # Fallback to known models
    return [
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
        {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash"},
    ]


def list_groq_models(api_key: str) -> list[dict[str, Any]]:
    """List available Groq models."""
    try:
        resp = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
    except Exception:
        pass
    return [
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B"},
        {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B"},
        {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B"},
    ]


def list_provider_models(provider: str, api_key: str | None = None, url: str | None = None) -> list[dict[str, Any]]:
    """List models for a given provider."""
    if provider == "ollama":
        return list_ollama_models(url or "http://localhost:11434")
    elif provider == "lmstudio":
        # LM Studio uses OpenAI-compatible API
        try:
            resp = httpx.get(f"{url or 'http://localhost:1234'}/v1/models", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
        except Exception:
            pass
        return []
    elif provider == "openai":
        return list_openai_models(api_key, url or "https://api.openai.com/v1") if api_key else []
    elif provider == "anthropic":
        return list_anthropic_models(api_key) if api_key else []
    elif provider == "gemini":
        return list_gemini_models(api_key) if api_key else []
    elif provider == "groq":
        return list_groq_models(api_key) if api_key else []
    elif provider in ("together", "openrouter"):
        # These use OpenAI-compatible API
        if api_key:
            base = API_PROVIDERS[provider]["base_url"]
            return list_openai_models(api_key, base)
        return []
    return []


# =============================================================================
# MODEL SELECTION UI
# =============================================================================

def select_model(models: list[dict[str, Any]], default: str | None = None) -> str | None:
    """
    Interactive model selection with filtering.

    Args:
        models: List of model dicts with 'id' and 'name' keys
        default: Default model ID to pre-select

    Returns:
        Selected model ID or None if cancelled
    """
    if not models:
        return Prompt.ask("Model name", default=default or "")

    console.print()
    console.print("[bold]Available models:[/]")
    console.print(f"[{BRAND_MUTED}]Type to filter, or enter number to select[/]")
    console.print()

    # Show models with numbers
    filtered = models
    filter_text = ""

    while True:
        # Display filtered list (max 15)
        display_models = filtered[:15]
        for i, model in enumerate(display_models, 1):
            name = model.get("name", model["id"])
            model_id = model["id"]
            if default and model_id == default:
                console.print(f"  [bold green]{i:2}.[/] {name} [dim](default)[/]")
            else:
                console.print(f"  [bold]{i:2}.[/] {name}")

        if len(filtered) > 15:
            console.print(f"  [{BRAND_MUTED}]... and {len(filtered) - 15} more (type to filter)[/]")

        console.print()

        # Get input
        prompt_text = "Select"
        if filter_text:
            prompt_text = f"Filter: {filter_text} | Select"

        choice = Prompt.ask(prompt_text, default="1" if default else "")

        # Handle backspace/clear filter
        if choice == "" and filter_text:
            filter_text = ""
            filtered = models
            console.print("\033[F" * (len(display_models) + 4))  # Move cursor up
            continue

        # Try as number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(display_models):
                return display_models[idx]["id"]
        except ValueError:
            pass

        # Try as filter text
        if choice:
            filter_text = choice.lower()
            filtered = [m for m in models if filter_text in m.get("name", "").lower() or filter_text in m["id"].lower()]
            if len(filtered) == 1:
                return filtered[0]["id"]
            elif len(filtered) == 0:
                print_warning("No models match filter")
                filter_text = ""
                filtered = models
            else:
                # Clear and redraw
                console.print("\033[F" * (len(display_models) + 4))  # Move cursor up
                continue

        # If just enter with default, use default
        if choice == "" and default:
            return default

    return None


# =============================================================================
# LLM WIZARD
# =============================================================================

def wizard_llm() -> bool:
    """
    Interactive LLM configuration wizard.

    Returns:
        True if configured successfully
    """
    console.print()
    console.print("[bold]LLM Setup[/]")
    console.print("─" * 40)
    console.print()

    # Detect local LLMs
    with create_spinner() as progress:
        task = progress.add_task("Detecting local LLMs...", total=None)
        local_llms = detect_all_local_llms()

    # Build provider options
    options = []

    # Add detected local LLMs first
    for llm in local_llms:
        options.append({
            "type": "local",
            "provider": llm.provider,
            "name": f"{llm.name} (detected)",
            "description": f"{len(llm.models)} models available",
            "url": llm.url,
            "models": llm.models,
        })

    # Add other local providers if not detected
    for provider_id, info in LOCAL_PROVIDERS.items():
        if not any(o["provider"] == provider_id for o in options):
            options.append({
                "type": "local_manual",
                "provider": provider_id,
                "name": info["name"],
                "description": f"{info['description']} (not running)",
                "url": info["url"],
            })

    # Add API providers
    for provider_id, info in API_PROVIDERS.items():
        options.append({
            "type": "api",
            "provider": provider_id,
            "name": info["name"],
            "description": info["description"],
        })

    # Display options
    console.print("Select your LLM provider:")
    console.print()

    for i, opt in enumerate(options, 1):
        name = opt["name"]
        desc = opt["description"]
        if opt["type"] == "local":
            console.print(f"  [bold green]{i:2}.[/] {name}")
            console.print(f"      [{BRAND_MUTED}]{desc}[/]")
        elif opt["type"] == "local_manual":
            console.print(f"  [bold]{i:2}.[/] {name}")
            console.print(f"      [{BRAND_MUTED}]{desc}[/]")
        else:
            console.print(f"  [bold]{i:2}.[/] {name}")
            console.print(f"      [{BRAND_MUTED}]{desc}[/]")

    console.print()

    # Get selection
    choice = Prompt.ask("Choose", default="1")
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(options):
            print_error("Invalid selection")
            return False
        selected = options[idx]
    except ValueError:
        print_error("Invalid selection")
        return False

    console.print()

    # Configure based on type
    if selected["type"] == "local":
        return _configure_local_llm(selected)
    elif selected["type"] == "local_manual":
        return _configure_local_llm_manual(selected)
    else:
        return _configure_api_llm(selected)


def _configure_local_llm(selected: dict) -> bool:
    """Configure a detected local LLM."""
    provider = selected["provider"]
    url = selected["url"]
    models = selected.get("models", [])

    console.print(f"Configuring {selected['name']}...")
    console.print()

    # Get models
    model_list = list_provider_models(provider, url=url)

    if not model_list:
        print_warning("Could not fetch model list")
        model = Prompt.ask("Model name", default="llama3.2")
    else:
        model = select_model(model_list, default=model_list[0]["id"] if model_list else None)
        if not model:
            return False

    # Save configuration
    set_llm_config(
        local_api_url=f"{url}/v1",
        local_model=model,
        default="local",
    )

    # Save provider info
    config = load_config()
    config["llm"]["local_provider"] = provider
    save_config(config)

    print_success(f"Configured {selected['name']} with model {model}")
    return True


def _configure_local_llm_manual(selected: dict) -> bool:
    """Configure a local LLM that's not currently running."""
    provider = selected["provider"]
    info = LOCAL_PROVIDERS[provider]

    console.print(f"{info['name']} is not currently running.")
    console.print()
    console.print(f"Install from: [link={info['install_url']}]{info['install_url']}[/link]")
    console.print()

    if not confirm(f"Configure {info['name']} anyway?"):
        return False

    url = Prompt.ask("Endpoint URL", default=info["url"])
    model = Prompt.ask("Model name", default="llama3.2")

    # Save configuration
    set_llm_config(
        local_api_url=f"{url}/v1",
        local_model=model,
        default="local",
    )

    config = load_config()
    config["llm"]["local_provider"] = provider
    save_config(config)

    print_success(f"Configured {info['name']} with model {model}")
    print_info(f"Make sure {info['name']} is running before generating stories")
    return True


def _configure_api_llm(selected: dict) -> bool:
    """Configure an API-based LLM provider."""
    provider = selected["provider"]
    info = API_PROVIDERS[provider]

    console.print(f"Configuring {info['name']}...")
    console.print()

    # Handle auth methods
    auth_methods = info.get("auth_methods", ["api_key"])

    api_key = None

    if "claude_setup" in auth_methods and provider == "anthropic":
        console.print("Authentication options:")
        console.print("  [bold]1.[/] API Key - Enter your Anthropic API key")
        console.print("  [bold]2.[/] Claude Setup Token - From claude.ai/account")
        console.print()

        auth_choice = Prompt.ask("Choose", choices=["1", "2"], default="1")

        if auth_choice == "2":
            console.print()
            console.print("To get your setup token:")
            console.print("  1. Go to https://claude.ai/account")
            console.print("  2. Run 'claude setup' in terminal")
            console.print("  3. Copy the token from the browser")
            console.print()
            api_key = Prompt.ask("Setup token", password=True)
        else:
            api_key = Prompt.ask("API Key", password=True)
    else:
        # Check environment variable first
        import os
        env_key = os.getenv(info.get("env_var", ""))
        if env_key:
            if confirm(f"Use {info['env_var']} from environment?"):
                api_key = env_key

        if not api_key:
            api_key = Prompt.ask("API Key", password=True)

    if not api_key:
        print_error("API key required")
        return False

    # Test the key and list models
    console.print()
    with create_spinner() as progress:
        task = progress.add_task("Verifying API key...", total=None)
        models = list_provider_models(provider, api_key=api_key)

    if not models:
        print_warning("Could not fetch models (key may still be valid)")
        models = [{"id": info["default_model"], "name": info["default_model"]}]

    # Select model
    model = select_model(models, default=info["default_model"])
    if not model:
        return False

    # Save to keychain and config
    add_byok_provider(provider, api_key, model)

    # Set as default
    set_llm_config(default=f"byok:{provider}")

    print_success(f"Configured {info['name']} with model {model}")
    return True


# =============================================================================
# REPOS WIZARD
# =============================================================================

def wizard_repos() -> bool:
    """
    Interactive repository configuration wizard.

    Returns:
        True if configured successfully
    """
    from .discovery import discover_repos

    console.print()
    console.print("[bold]Repository Setup[/]")
    console.print("─" * 40)
    console.print()

    # Check existing tracked repos
    tracked = get_tracked_repos()
    if tracked:
        console.print(f"Currently tracking {len(tracked)} repositories")
        if not confirm("Scan for more?", default=False):
            return True

    # Determine scan path
    default_paths = [Path.home() / "code", Path.home() / "projects", Path.home() / "dev"]
    scan_path = None

    for p in default_paths:
        if p.exists():
            scan_path = p
            break

    if not scan_path:
        scan_path = Path.cwd()

    path_input = Prompt.ask("Directory to scan", default=str(scan_path))
    scan_path = Path(path_input).expanduser().resolve()

    if not scan_path.exists():
        print_error(f"Directory not found: {scan_path}")
        return False

    # Scan for repos
    console.print()
    with create_spinner() as progress:
        task = progress.add_task(f"Scanning {scan_path}...", total=None)
        repos = discover_repos([scan_path], min_commits=5)

    if not repos:
        print_warning(f"No repositories found in {scan_path}")
        return False

    # Show found repos
    console.print(f"Found [bold]{len(repos)}[/] repositories")
    console.print()

    for repo in repos[:10]:
        lang = repo.primary_language or "Unknown"
        console.print(f"  ✓ {repo.name} ({repo.commit_count} commits) [{lang}]")

    if len(repos) > 10:
        console.print(f"  ... and {len(repos) - 10} more")

    console.print()

    # Ask to track
    if confirm("Track these repositories?", default=True):
        for repo in repos:
            add_tracked_repo(str(repo.path))
        print_success(f"Tracking {len(repos)} repositories")
        return True

    return False


# =============================================================================
# SCHEDULE WIZARD
# =============================================================================

def wizard_schedule() -> bool:
    """
    Interactive schedule configuration wizard.

    Returns:
        True if configured successfully
    """
    from .hooks import install_hook
    from .cron import install_cron

    console.print()
    console.print("[bold]Schedule Setup[/]")
    console.print("─" * 40)
    console.print()

    console.print("How should repr generate stories from your commits?")
    console.print()
    console.print("  [bold]1.[/] Scheduled (recommended) - Every 4 hours via cron")
    console.print(f"     [{BRAND_MUTED}]Predictable, batches work, never interrupts[/]")
    console.print()
    console.print("  [bold]2.[/] On commit - After every 5 commits via git hook")
    console.print(f"     [{BRAND_MUTED}]Real-time, but needs LLM running during commits[/]")
    console.print()
    console.print("  [bold]3.[/] Manual only - Run `repr generate` yourself")
    console.print(f"     [{BRAND_MUTED}]Full control, no automation[/]")
    console.print()

    choice = Prompt.ask("Choose", choices=["1", "2", "3"], default="1")

    tracked = get_tracked_repos()
    config = load_config()

    if choice == "1":
        # Scheduled via cron
        result = install_cron(interval_hours=4, min_commits=3)
        if result["success"]:
            print_success("Cron job installed (every 4h)")
            config["generation"]["auto_generate_on_hook"] = False
            save_config(config)
            # Install hooks for queue tracking
            for repo in tracked:
                try:
                    install_hook(Path(repo["path"]))
                    set_repo_hook_status(repo["path"], True)
                except Exception:
                    pass
        else:
            print_warning(f"Could not install cron: {result['message']}")
            print_info("You can set it up later with `repr cron install`")

    elif choice == "2":
        # On-commit via hooks
        config["generation"]["auto_generate_on_hook"] = True
        save_config(config)
        hook_count = 0
        for repo in tracked:
            try:
                install_hook(Path(repo["path"]))
                set_repo_hook_status(repo["path"], True)
                hook_count += 1
            except Exception:
                pass
        print_success(f"Hooks installed in {hook_count} repos (generates after 5 commits)")

    else:
        # Manual only
        config["generation"]["auto_generate_on_hook"] = False
        save_config(config)
        print_info("Manual mode - run `repr generate` when you want stories")

    return True


# =============================================================================
# FULL WIZARD
# =============================================================================

def run_full_wizard() -> bool:
    """
    Run the complete setup wizard (first-run experience).

    Order: LLM → Repos → Schedule

    Returns:
        True if completed successfully
    """
    print_header()
    console.print("Welcome to repr! Let's get you set up.")
    console.print()
    console.print(f"[{BRAND_MUTED}]Works locally first — sign in later for sync and sharing.[/]")

    # Step 1: LLM
    console.print()
    console.print("[bold]Step 1 of 3: LLM[/]")
    if not wizard_llm():
        print_warning("LLM not configured. You can set it up later with `repr configure llm`")

    # Step 2: Repos
    console.print()
    console.print("[bold]Step 2 of 3: Repositories[/]")
    if not wizard_repos():
        print_warning("No repos tracked. You can add them later with `repr configure repos`")

    # Step 3: Schedule
    console.print()
    console.print("[bold]Step 3 of 3: Schedule[/]")
    wizard_schedule()

    # Done
    console.print()
    print_success("Setup complete!")
    console.print()

    print_next_steps([
        "repr week               See what you worked on this week",
        "repr generate           Save stories permanently",
        "repr login              Unlock cloud sync and publishing",
    ])

    return True


# =============================================================================
# CONFIGURE MENU
# =============================================================================

def run_configure_menu() -> None:
    """
    Show the main configure menu.
    """
    console.print()
    console.print("[bold]What would you like to configure?[/]")
    console.print()

    # Get current status
    llm_config = get_llm_config()
    tracked = get_tracked_repos()
    config = load_config()

    # LLM status
    llm_status = "Not configured"
    if llm_config.get("local_provider"):
        model = llm_config.get("local_model", "unknown")
        llm_status = f"{llm_config['local_provider'].title()} ({model})"
    elif llm_config.get("byok"):
        providers = list(llm_config["byok"].keys())
        llm_status = ", ".join(p.title() for p in providers)

    # Schedule status
    schedule_status = "Manual"
    if config.get("cron", {}).get("installed"):
        interval = config["cron"].get("interval_hours", 4)
        schedule_status = f"Every {interval}h via cron"
    elif config.get("generation", {}).get("auto_generate_on_hook"):
        schedule_status = "On commit via hooks"

    console.print(f"  [bold]1.[/] LLM          [{BRAND_MUTED}]{llm_status}[/]")
    console.print(f"  [bold]2.[/] Repositories [{BRAND_MUTED}]{len(tracked)} tracked[/]")
    console.print(f"  [bold]3.[/] Schedule     [{BRAND_MUTED}]{schedule_status}[/]")
    console.print()
    console.print(f"  [bold]q.[/] Quit")
    console.print()

    choice = Prompt.ask("Choose", default="q")

    if choice == "1":
        wizard_llm()
    elif choice == "2":
        wizard_repos()
    elif choice == "3":
        wizard_schedule()
    elif choice.lower() == "q":
        return
    else:
        print_error("Invalid selection")
