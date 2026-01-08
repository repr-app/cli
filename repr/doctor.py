"""
Health check and diagnostics for repr CLI.

Provides comprehensive system status and actionable recommendations.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "ok", "warning", "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    fix: str | None = None


@dataclass
class DoctorReport:
    """Complete health check report."""
    checks: list[CheckResult]
    overall_status: str  # "healthy", "warnings", "issues"
    recommendations: list[str]


def check_auth() -> CheckResult:
    """Check authentication status."""
    from .config import is_authenticated, get_auth
    
    if is_authenticated():
        auth = get_auth()
        email = auth.get("email", "unknown") if auth else "unknown"
        return CheckResult(
            name="Authentication",
            status="ok",
            message=f"Signed in as {email}",
            details={"email": email},
        )
    else:
        return CheckResult(
            name="Authentication",
            status="warning",
            message="Not signed in",
            details={},
            fix="Run `repr login` to enable cloud features",
        )


def check_local_llm() -> CheckResult:
    """Check local LLM availability."""
    from .llm import detect_local_llm, test_local_llm
    from .config import get_llm_config
    
    llm_config = get_llm_config()
    
    # Check configured endpoint first
    if llm_config.get("local_api_url"):
        result = test_local_llm(
            url=llm_config["local_api_url"],
            model=llm_config.get("local_model"),
        )
        if result.success:
            return CheckResult(
                name="Local LLM",
                status="ok",
                message=f"Connected to {result.endpoint}",
                details={
                    "provider": result.provider,
                    "model": result.model,
                    "response_time_ms": result.response_time_ms,
                },
            )
        else:
            return CheckResult(
                name="Local LLM",
                status="error",
                message=f"Configured endpoint unreachable: {llm_config['local_api_url']}",
                details={"error": result.error},
                fix="Start your local LLM or run `repr llm configure`",
            )
    
    # Try auto-detection
    detected = detect_local_llm()
    if detected:
        return CheckResult(
            name="Local LLM",
            status="ok",
            message=f"Detected {detected.name} at {detected.url}",
            details={
                "provider": detected.provider,
                "url": detected.url,
                "models": detected.models[:5],  # First 5
                "default_model": detected.default_model,
            },
        )
    else:
        return CheckResult(
            name="Local LLM",
            status="warning",
            message="No local LLM detected",
            details={},
            fix="Install Ollama (`ollama serve`) or run `repr llm configure`",
        )


def check_tracked_repos() -> CheckResult:
    """Check tracked repositories."""
    from .config import get_tracked_repos
    
    tracked = get_tracked_repos()
    
    if not tracked:
        return CheckResult(
            name="Tracked Repositories",
            status="warning",
            message="No repositories tracked",
            details={},
            fix="Run `repr init` or `repr repos add <path>`",
        )
    
    # Check if repos exist
    existing = []
    missing = []
    for repo in tracked:
        path = Path(repo["path"])
        if path.exists() and (path / ".git").exists():
            existing.append(repo)
        else:
            missing.append(repo["path"])
    
    if missing:
        return CheckResult(
            name="Tracked Repositories",
            status="warning",
            message=f"{len(existing)} repos accessible, {len(missing)} missing",
            details={
                "existing": len(existing),
                "missing": missing,
            },
            fix=f"Remove missing repos: repr repos remove <path>",
        )
    
    return CheckResult(
        name="Tracked Repositories",
        status="ok",
        message=f"{len(tracked)} repositories tracked",
        details={
            "count": len(tracked),
            "repos": [Path(r["path"]).name for r in tracked[:5]],
        },
    )


def check_hooks() -> CheckResult:
    """Check hook installation status."""
    from .config import get_tracked_repos
    from .hooks import is_hook_installed
    
    tracked = get_tracked_repos()
    
    if not tracked:
        return CheckResult(
            name="Git Hooks",
            status="warning",
            message="No repositories to check",
            details={},
        )
    
    installed = 0
    not_installed = []
    
    for repo in tracked:
        path = Path(repo["path"])
        if path.exists() and is_hook_installed(path):
            installed += 1
        elif path.exists():
            not_installed.append(Path(repo["path"]).name)
    
    total = len([r for r in tracked if Path(r["path"]).exists()])
    
    if installed == total:
        return CheckResult(
            name="Git Hooks",
            status="ok",
            message=f"Installed in {installed}/{total} repos",
            details={"installed": installed, "total": total},
        )
    elif installed > 0:
        return CheckResult(
            name="Git Hooks",
            status="warning",
            message=f"Installed in {installed}/{total} repos",
            details={
                "installed": installed,
                "total": total,
                "missing": not_installed[:5],
            },
            fix="Run `repr hooks install --all` to install in all repos",
        )
    else:
        return CheckResult(
            name="Git Hooks",
            status="warning",
            message="No hooks installed",
            details={},
            fix="Run `repr hooks install --all` to enable auto-tracking",
        )


def check_story_queue() -> CheckResult:
    """Check commit queue status."""
    from .config import get_tracked_repos, get_llm_config
    from .hooks import load_queue
    
    tracked = get_tracked_repos()
    llm_config = get_llm_config()
    batch_size = llm_config.get("batch_size", 5)
    
    total_queued = 0
    repos_with_queue = []
    
    for repo in tracked:
        path = Path(repo["path"])
        if path.exists():
            queue = load_queue(path)
            if queue:
                total_queued += len(queue)
                repos_with_queue.append({
                    "name": path.name,
                    "count": len(queue),
                })
    
    if total_queued == 0:
        return CheckResult(
            name="Commit Queue",
            status="ok",
            message="No commits pending",
            details={},
        )
    elif total_queued >= batch_size:
        return CheckResult(
            name="Commit Queue",
            status="warning",
            message=f"{total_queued} commits pending (batch size: {batch_size})",
            details={
                "total": total_queued,
                "batch_size": batch_size,
                "repos": repos_with_queue,
            },
            fix="Run `repr generate` to create stories from pending commits",
        )
    else:
        return CheckResult(
            name="Commit Queue",
            status="ok",
            message=f"{total_queued} commits queued (batch: {batch_size})",
            details={
                "total": total_queued,
                "batch_size": batch_size,
            },
        )


def check_unpushed_stories() -> CheckResult:
    """Check for unpushed stories."""
    from .storage import get_unpushed_stories, get_story_count
    from .config import is_authenticated
    
    total = get_story_count()
    unpushed = get_unpushed_stories()
    
    if total == 0:
        return CheckResult(
            name="Stories",
            status="warning",
            message="No stories generated yet",
            details={},
            fix="Run `repr generate` to create stories from your commits",
        )
    
    if not unpushed:
        return CheckResult(
            name="Stories",
            status="ok",
            message=f"{total} stories (all synced)",
            details={"total": total, "unpushed": 0},
        )
    
    if is_authenticated():
        return CheckResult(
            name="Stories",
            status="warning",
            message=f"{total} stories ({len(unpushed)} not pushed)",
            details={"total": total, "unpushed": len(unpushed)},
            fix="Run `repr push` to publish unpushed stories",
        )
    else:
        return CheckResult(
            name="Stories",
            status="ok",
            message=f"{total} stories (local only)",
            details={"total": total, "unpushed": len(unpushed)},
        )


def check_stories_needing_review() -> CheckResult:
    """Check for stories needing review."""
    from .storage import get_stories_needing_review
    
    needs_review = get_stories_needing_review()
    
    if not needs_review:
        return CheckResult(
            name="Story Review",
            status="ok",
            message="No stories need review",
            details={},
        )
    else:
        return CheckResult(
            name="Story Review",
            status="warning",
            message=f"{len(needs_review)} stories need review",
            details={
                "count": len(needs_review),
                "stories": [s.get("summary", s.get("id", ""))[:50] for s in needs_review[:3]],
            },
            fix="Run `repr stories review` to review flagged stories",
        )


def check_privacy_settings() -> CheckResult:
    """Check privacy configuration."""
    from .config import get_privacy_settings, is_cloud_allowed
    
    privacy = get_privacy_settings()
    
    if privacy.get("lock_permanent"):
        return CheckResult(
            name="Privacy",
            status="ok",
            message="Local-only mode (permanent)",
            details={"lock_permanent": True},
        )
    elif privacy.get("lock_local_only"):
        return CheckResult(
            name="Privacy",
            status="ok",
            message="Local-only mode enabled",
            details={"lock_local_only": True},
        )
    elif is_cloud_allowed():
        return CheckResult(
            name="Privacy",
            status="ok",
            message="Cloud features enabled",
            details={
                "telemetry": privacy.get("telemetry_enabled", False),
                "visibility": privacy.get("profile_visibility", "public"),
            },
        )
    else:
        return CheckResult(
            name="Privacy",
            status="ok",
            message="Local mode (not authenticated)",
            details={},
        )


def check_byok() -> CheckResult:
    """Check BYOK provider configuration."""
    from .config import list_byok_providers, get_byok_config
    
    providers = list_byok_providers()
    
    if not providers:
        return CheckResult(
            name="BYOK Providers",
            status="ok",
            message="No BYOK providers configured",
            details={},
        )
    
    # Verify each provider has valid config
    valid = []
    invalid = []
    
    for provider in providers:
        config = get_byok_config(provider)
        if config and config.get("api_key"):
            valid.append(provider)
        else:
            invalid.append(provider)
    
    if invalid:
        return CheckResult(
            name="BYOK Providers",
            status="warning",
            message=f"{len(valid)} valid, {len(invalid)} misconfigured",
            details={
                "valid": valid,
                "invalid": invalid,
            },
            fix=f"Reconfigure: repr llm add {invalid[0]}",
        )
    
    return CheckResult(
        name="BYOK Providers",
        status="ok",
        message=f"{len(valid)} providers configured",
        details={"providers": valid},
    )


def run_all_checks() -> DoctorReport:
    """
    Run all health checks and generate report.
    
    Returns:
        DoctorReport with all check results
    """
    checks = [
        check_auth(),
        check_local_llm(),
        check_tracked_repos(),
        check_hooks(),
        check_story_queue(),
        check_unpushed_stories(),
        check_stories_needing_review(),
        check_privacy_settings(),
        check_byok(),
    ]
    
    # Determine overall status
    has_errors = any(c.status == "error" for c in checks)
    has_warnings = any(c.status == "warning" for c in checks)
    
    if has_errors:
        overall_status = "issues"
    elif has_warnings:
        overall_status = "warnings"
    else:
        overall_status = "healthy"
    
    # Collect recommendations
    recommendations = [c.fix for c in checks if c.fix and c.status in ("warning", "error")]
    
    return DoctorReport(
        checks=checks,
        overall_status=overall_status,
        recommendations=recommendations,
    )






































