"""
OpenAI-based analysis for repository profiling.

This module implements a direct OpenAI integration for analyzing git repositories
using a two-phase approach:
1. EXTRACTION: Process batches of commits with diffs using gpt-5-nano
2. SYNTHESIS: Combine summaries into final profile using gpt-5.2
"""

import asyncio
from typing import Any

from openai import AsyncOpenAI

from .tools import get_commits_with_diffs
from .discovery import RepoInfo
from .config import get_litellm_config, get_llm_config, get_api_base


# Model configuration (defaults for OpenAI)
DEFAULT_EXTRACTION_MODEL = "openai/gpt-5-nano-2025-08-07"
DEFAULT_SYNTHESIS_MODEL = "openai/gpt-5.2-2025-12-11"
EXTRACTION_TEMPERATURE = 0.3
SYNTHESIS_TEMPERATURE = 0.7
COMMITS_PER_BATCH = 25  # Default fallback, use config value when possible


def estimate_tokens(commits: list[dict[str, Any]]) -> int:
    """
    Estimate token count for a list of commits.

    Uses a rough heuristic: ~4 characters per token (GPT tokenization rule of thumb).
    Includes commit messages, file paths, and diffs.

    Args:
        commits: List of commits with diffs

    Returns:
        Estimated token count
    """
    total_chars = 0

    for commit in commits:
        # Count commit message
        total_chars += len(commit.get('message', ''))

        # Count file information
        for file_info in commit.get('files', []):
            total_chars += len(file_info.get('path', ''))
            if 'diff' in file_info and file_info['diff']:
                total_chars += len(file_info['diff'])

    # Rule of thumb: ~4 characters per token
    estimated_tokens = total_chars // 4

    # Add overhead for prompts and formatting (~2000 tokens)
    return estimated_tokens + 2000


def get_batch_size() -> int:
    """
    Get batch size from config, with fallback to COMMITS_PER_BATCH constant.

    Returns:
        Batch size (max commits per batch)
    """
    try:
        from .config import load_config
        config = load_config()
        return config.get("generation", {}).get("max_commits_per_batch", COMMITS_PER_BATCH)
    except Exception:
        return COMMITS_PER_BATCH


def get_openai_client(api_key: str = None, base_url: str = None, verbose: bool = False) -> AsyncOpenAI:
    """
    Get OpenAI-compatible client that proxies through our backend.
    
    Args:
        api_key: API key (optional, for local LLM mode)
        base_url: Base URL for API (optional, for local LLM mode)
        verbose: Whether to print debug info
    
    Returns:
        AsyncOpenAI client
    """
    import sys
    
    # If explicit parameters provided, use them (for local mode)
    if api_key:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if verbose:
            print(f"[DEBUG] Using explicit API key with base_url: {base_url or 'OpenAI default'}", file=sys.stderr)
        return AsyncOpenAI(**kwargs)
    
    # Use our backend as the proxy - it will forward to LiteLLM
    # The rf_* token is used to authenticate with our backend
    _, litellm_key = get_litellm_config()
    if not litellm_key:
        raise ValueError("Not logged in. Please run 'repr login' first.")
    
    # Point to our backend's LLM proxy endpoint
    backend_url = get_api_base().replace("/api/cli", "")
    proxy_url = f"{backend_url}/api/llm/v1"
    
    if verbose:
        print(f"[DEBUG] Backend URL: {backend_url}", file=sys.stderr)
        print(f"[DEBUG] Proxy URL: {proxy_url}", file=sys.stderr)
        print(f"[DEBUG] Token: {litellm_key[:15]}...", file=sys.stderr)
    
    return AsyncOpenAI(
        api_key=litellm_key,
        base_url=proxy_url
    )


async def extract_commit_batch(
    client: AsyncOpenAI,
    commits: list[dict[str, Any]],
    batch_num: int,
    total_batches: int,
    model: str = None,
    system_prompt: str = None,
    user_prompt: str = None,
) -> str:
    """
    Extraction phase: Extract accomplishments from a batch of commits.
    
    Args:
        client: OpenAI client
        commits: List of commits with diffs
        batch_num: Current batch number (for context)
        total_batches: Total number of batches
        model: Model name to use (defaults to stored config or DEFAULT_EXTRACTION_MODEL)
        system_prompt: Custom system prompt (optional, uses default if not provided)
        user_prompt: Custom user prompt (optional, uses default if not provided)
    
    Returns:
        Summary of technical accomplishments in this batch
    """
    if not model:
        llm_config = get_llm_config()
        model = llm_config.get("extraction_model") or DEFAULT_EXTRACTION_MODEL
    
    # Use provided prompts or build defaults
    if not system_prompt or not user_prompt:
        # Format commits for the prompt
        commits_text = []
        for commit in commits:
            commit_text = f"""
Commit: {commit['sha']}
Date: {commit['date']}
Message: {commit['message']}

Files changed:"""
            
            for file_info in commit['files'][:10]:  # Limit files per commit
                change_type = {
                    'A': 'Added',
                    'D': 'Deleted',
                    'M': 'Modified',
                    'R': 'Renamed'
                }.get(file_info['change_type'], 'Changed')
                
                commit_text += f"\n  {change_type}: {file_info['path']}"
                
                if file_info['diff']:
                    # Truncate diff if too long (for token management)
                    diff = file_info['diff'][:2000]
                    commit_text += f"\n```diff\n{diff}\n```"
            
            commits_text.append(commit_text)
        
        commits_formatted = "\n\n---\n".join(commits_text)
        
        if not system_prompt:
            system_prompt = """You are analyzing a developer's actual code commits to extract specific technical accomplishments WITH the reasoning behind them.

Your job: Read the commit messages and diffs, then list CONCRETE technical accomplishments with SPECIFIC details AND infer WHY those decisions were made.

For each accomplishment, capture:
1. WHAT was built (the technical implementation)
2. WHY it was needed (the problem being solved, the user/business need, or the technical constraint)

Rules:
- Use EXACT technology names from the code (FastAPI, React, SQLAlchemy, not "web framework")
- Describe SPECIFIC features built (e.g., "JWT authentication with refresh tokens", not "auth system")
- INFER the motivation when possible:
  - Performance changes → what latency/throughput problem was being solved?
  - New features → what user capability was being enabled?
  - Refactors → what maintainability or scalability issue was being addressed?
  - Error handling → what failure mode was being prevented?
- Mention architectural patterns when evident (microservices, event-driven, REST API, etc.)
- Include scale indicators (number of endpoints, integrations, etc.)
- Be concise but specific - bullet points are fine

What NOT to do:
- Don't write vague statements like "worked on backend"
- Don't guess technologies not shown in the diffs
- Don't include process/methodology unless there's evidence
- Don't fabricate motivations that aren't supported by the code/commits"""

        if not user_prompt:
            user_prompt = f"""Analyze commits batch {batch_num}/{total_batches} and extract technical accomplishments:

{commits_formatted}

List the specific technical work done in this batch. For each item:
1. What was BUILT (the concrete implementation)
2. Why it was needed (infer from context: what problem was solved? what user need? what constraint?)

Focus on substance, not process."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=EXTRACTION_TEMPERATURE,
            max_tokens=16000,  # Increased for reasoning models that use tokens for thinking
        )
        
        return response.choices[0].message.content or ""
    except Exception as e:
        error_msg = str(e).lower()
        # Handle content moderation blocks gracefully
        if "blocked" in error_msg or "content" in error_msg or "moderation" in error_msg:
            # Skip this batch but continue with others
            return f"[Batch {batch_num} skipped - content filter triggered]"
        # Re-raise other errors
        raise


async def synthesize_profile(
    client: AsyncOpenAI,
    summaries: list[str],
    repo_info: dict[str, Any],
    model: str = None,
) -> str:
    """
    Synthesis phase: Combine batch summaries into final developer profile.
    
    Args:
        client: OpenAI client
        summaries: List of batch summaries from extraction phase
        repo_info: Repository metadata
        model: Model name to use (defaults to stored config or DEFAULT_SYNTHESIS_MODEL)
    
    Returns:
        Final developer profile in markdown
    """
    if not model:
        llm_config = get_llm_config()
        model = llm_config.get("synthesis_model") or DEFAULT_SYNTHESIS_MODEL
    summaries_text = "\n\n---\n\n".join([
        f"## Batch {i+1}\n\n{summary}"
        for i, summary in enumerate(summaries)
    ])
    
    system_prompt = """You are an expert technical resume writer creating a developer profile from their ACTUAL code commits.

Transform the batch analyses into COMPELLING RESUME CONTENT that shows not just WHAT was built, but WHY decisions were made.

CRITICAL - NO GENERIC STATEMENTS:
- ❌ "Experience with web frameworks" → ✅ "Built REST APIs with FastAPI including WebSocket support for real-time updates"
- ❌ "Strong Python skills" → ✅ "Architected async Python backend with SQLAlchemy, Celery task queues, and Redis caching"
- ❌ "Agile methodologies" → Don't mention process/methodology

CRITICAL - INCLUDE THE WHY:
For significant technical work, explain the reasoning:
- ✅ "Built WebSocket token streaming—users expect ChatGPT-like instant feedback; REST endpoints that return only after full completion feel broken for 10-30 second responses"
- ✅ "Implemented Redis-backed auth caching to short-circuit repeated Supabase validation—every API call was adding 50-100ms of overhead"
- ✅ "Added explicit rollback paths in DB transactions—SQLAlchemy's implicit rollback doesn't always fire when expected, causing connection pool pollution"

The WHY demonstrates engineering judgment:
- What problem was being solved?
- What tradeoffs were considered?
- What would have happened without this change?
- What user/business need drove this?

STRUCTURE:
1. **Summary**: 2-3 sentences capturing UNIQUE expertise (not generic "versatile developer")
2. **Key Technical Skills (used in this codebase)**: ONLY technologies ACTUALLY used, with context of HOW they were used
3. **Notable Projects & Contributions**: SPECIFIC features/achievements with technical details AND the reasoning behind key decisions. Group related work under descriptive subsection headers. For each major piece of work, include a "**Why**:" line explaining the problem/motivation.
4. **Development Philosophy (evidence-based)**: ONLY if there's clear evidence (comprehensive tests, specific patterns). Include *Why?* explanations that show the thinking.

Use strong action verbs: Built, Architected, Implemented, Designed, Optimized, Integrated
Every claim must be backed by evidence from the commits."""

    # Build metadata header (injected directly, not LLM-generated)
    languages = repo_info.get('languages', {})
    languages_str = ", ".join([f"{k} ({v}%)" for k, v in languages.items()]) if languages else "Unknown"
    
    # Calculate age display
    age_months = repo_info.get('age_months', 0)
    if age_months < 1:
        age_str = "< 1 month"
    elif age_months < 12:
        age_str = f"{age_months} months"
    else:
        years = age_months // 12
        remaining_months = age_months % 12
        age_str = f"{years} year{'s' if years > 1 else ''}" + (f", {remaining_months} months" if remaining_months else "")
    
    # Format remote URL (clean up if present)
    remote_url = repo_info.get('remote_url', '')
    if remote_url:
        remote_display = remote_url.replace('git@github.com:', 'github.com/').replace('.git', '')
        if remote_display.startswith('https://'):
            remote_display = remote_display[8:]
    else:
        remote_display = None
    
    # Build the metadata header to prepend
    metadata_lines = [
        f"- **Repository**: {repo_info.get('name', 'Unknown')}",
        f"- **Languages**: {languages_str}",
        f"- **Total Commits**: {repo_info.get('commit_count', 'Unknown')}",
        f"- **Contributors**: {repo_info.get('contributors', 'Unknown')}",
        f"- **Active Period**: {repo_info.get('first_commit_date', 'Unknown')} to {repo_info.get('last_commit_date', 'Unknown')} ({age_str})",
    ]
    if remote_display:
        metadata_lines.append(f"- **Remote**: {remote_display}")
    if repo_info.get('is_fork'):
        metadata_lines.append("- **Fork**: Yes")
    
    metadata_header = "\n".join(metadata_lines)
    
    user_prompt = f"""Create a developer profile from these commit analyses:

## Technical Work (from commit analysis):

{summaries_text}

---

Synthesize this into a cohesive developer profile in Markdown format starting with Summary, then Key Technical Skills, Notable Projects & Contributions, and Development Philosophy.

Focus on CONCRETE technical accomplishments AND the reasoning behind key decisions. For each major feature or system, explain WHY it was built that way—what problem it solved, what user need it addressed, or what technical constraint it navigated."""

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=SYNTHESIS_TEMPERATURE,
        max_tokens=16000,  # Increased for reasoning models
    )
    
    llm_content = response.choices[0].message.content or ""
    
    # Prepend metadata header
    return f"{metadata_header}\n\n---\n\n{llm_content}"


async def analyze_repo_openai(
    repo: RepoInfo,
    api_key: str = None,
    base_url: str = None,
    extraction_model: str = None,
    synthesis_model: str = None,
    verbose: bool = False,
    progress_callback: callable = None,
    since: str = None,
) -> str:
    """
    Analyze a single repository using OpenAI-compatible API.
    
    Args:
        repo: Repository information
        api_key: API key (defaults to OPENAI_API_KEY env var)
        base_url: Base URL for API (for local LLMs like Ollama)
        extraction_model: Model for extracting accomplishments (defaults to DEFAULT_EXTRACTION_MODEL)
        synthesis_model: Model for synthesizing profile (defaults to DEFAULT_SYNTHESIS_MODEL)
        verbose: Whether to print verbose output
        progress_callback: Optional callback for progress updates
            Signature: callback(step: str, detail: str, repo: str, progress: float)
        since: Only analyze commits after this point (SHA or date like '2026-01-01')
    
    Returns:
        Repository analysis/narrative in markdown
    """
    client = get_openai_client(api_key=api_key, base_url=base_url, verbose=verbose)
    
    if progress_callback:
        progress_callback(
            step="Extracting",
            detail=f"Reading git history ({repo.commit_count} commits)",
            repo=repo.name,
            progress=5.0,
        )
    
    # Get commits with diffs
    commits = get_commits_with_diffs(
        repo_path=repo.path,
        count=200,  # Last 200 commits
        days=730,  # Last 2 years
        since=since,
    )
    
    if not commits:
        return f"No commits found in {repo.name}"
    
    if progress_callback:
        progress_callback(
            step="Preparing",
            detail=f"Found {len(commits)} commits with diffs to analyze",
            repo=repo.name,
            progress=10.0,
        )
    
    # Split into batches (use config value)
    batch_size = get_batch_size()
    batches = [
        commits[i:i + batch_size]
        for i in range(0, len(commits), batch_size)
    ]
    
    total_batches = len(batches)
    
    if progress_callback:
        progress_callback(
            step="Analyzing",
            detail=f"Processing {total_batches} batches ({batch_size} commits each)",
            repo=repo.name,
            progress=15.0,
        )
    
    # EXTRACTION phase: Process batches with progress tracking
    async def process_batch_with_progress(batch, batch_num):
        """Process a single batch and report progress."""
        result = await extract_commit_batch(client, batch, batch_num, total_batches, model=extraction_model)
        if progress_callback:
            # Progress goes from 15% to 75% during extraction phase
            batch_progress = 15.0 + (60.0 * batch_num / total_batches)
            progress_callback(
                step="Analyzing",
                detail=f"Batch {batch_num}/{total_batches} complete",
                repo=repo.name,
                progress=batch_progress,
            )
        return result
    
    # Process batches concurrently but track progress
    extraction_tasks = [
        process_batch_with_progress(batch, i + 1)
        for i, batch in enumerate(batches)
    ]
    
    summaries = await asyncio.gather(*extraction_tasks)
    
    # Filter out empty summaries
    summaries = [s for s in summaries if s.strip()]
    
    if not summaries:
        return f"Could not extract meaningful information from {repo.name}"
    
    if progress_callback:
        progress_callback(
            step="Synthesizing",
            detail="Generating developer profile from analysis...",
            repo=repo.name,
            progress=80.0,
        )
    
    # SYNTHESIS phase: Combine into final profile
    repo_dict = {
        "name": repo.name,
        "path": str(repo.path),
        "languages": repo.languages,
        "primary_language": repo.primary_language,
        "commit_count": repo.commit_count,
        "contributors": repo.contributors,
        "first_commit_date": repo.first_commit_date.isoformat() if repo.first_commit_date else None,
        "last_commit_date": repo.last_commit_date.isoformat() if repo.last_commit_date else None,
        "remote_url": repo.remote_url,
        "is_fork": repo.is_fork,
        "age_months": repo.age_months,
    }
    
    profile = await synthesize_profile(client, summaries, repo_dict, model=synthesis_model)
    
    if progress_callback:
        progress_callback(
            step="Complete",
            detail=f"Profile generated for {repo.name}",
            repo=repo.name,
            progress=100.0,
        )
    
    return profile


async def analyze_repos_openai(
    repos: list[RepoInfo],
    api_key: str = None,
    base_url: str = None,
    extraction_model: str = None,
    synthesis_model: str = None,
    verbose: bool = False,
    progress_callback: callable = None,
) -> str:
    """
    Analyze multiple repositories and create a combined profile.
    
    Args:
        repos: List of repositories to analyze
        api_key: API key (defaults to OPENAI_API_KEY env var)
        base_url: Base URL for API (for local LLMs like Ollama)
        extraction_model: Model for extracting accomplishments (defaults to DEFAULT_EXTRACTION_MODEL)
        synthesis_model: Model for synthesizing profile (defaults to DEFAULT_SYNTHESIS_MODEL)
        verbose: Whether to print verbose output
        progress_callback: Optional callback for progress updates
            Signature: callback(step: str, detail: str, repo: str, progress: float)
    
    Returns:
        Combined developer profile in markdown
    """
    if not repos:
        return "No repositories to analyze"
    
    total_repos = len(repos)
    
    if progress_callback:
        progress_callback(
            step="Starting",
            detail=f"Analyzing {total_repos} {'repository' if total_repos == 1 else 'repositories'}",
            repo="",
            progress=0.0,
        )
    
    # Analyze each repo
    repo_profiles = []
    for i, repo in enumerate(repos):
        # Create a scoped progress callback for this repo
        def make_repo_callback(repo_idx, repo_name):
            def repo_callback(step, detail, repo, progress):
                # Scale progress: each repo gets equal share
                repo_start = (repo_idx / total_repos) * 90  # Save 10% for final merge
                repo_end = ((repo_idx + 1) / total_repos) * 90
                scaled_progress = repo_start + (progress / 100) * (repo_end - repo_start)
                
                if progress_callback:
                    progress_callback(
                        step=step,
                        detail=f"[{repo_idx + 1}/{total_repos}] {detail}",
                        repo=repo_name,
                        progress=scaled_progress,
                    )
            return repo_callback
        
        profile = await analyze_repo_openai(
            repo, 
            api_key=api_key,
            base_url=base_url,
            extraction_model=extraction_model,
            synthesis_model=synthesis_model,
            verbose=verbose,
            progress_callback=make_repo_callback(i, repo.name),
        )
        repo_profiles.append({
            "name": repo.name,
            "profile": profile,
        })
    
    # If only one repo, return its profile directly
    if len(repos) == 1:
        return repo_profiles[0]["profile"]
    
    # Multiple repos: combine them
    if progress_callback:
        progress_callback(
            step="Merging",
            detail=f"Combining profiles from {total_repos} repositories...",
            repo="all",
            progress=92.0,
        )
    
    client = get_openai_client(api_key=api_key, base_url=base_url, verbose=verbose)
    
    # Aggregate metadata from all repos (injected directly, not LLM-generated)
    total_commits = sum(r.commit_count for r in repos)
    all_languages = {}
    for repo in repos:
        if repo.languages:
            for lang, pct in repo.languages.items():
                all_languages[lang] = all_languages.get(lang, 0) + pct
    # Normalize percentages
    if all_languages:
        total_pct = sum(all_languages.values())
        all_languages = {k: round(v * 100 / total_pct) for k, v in sorted(all_languages.items(), key=lambda x: -x[1])}
    
    # Find date range across all repos
    first_dates = [r.first_commit_date for r in repos if r.first_commit_date]
    last_dates = [r.last_commit_date for r in repos if r.last_commit_date]
    earliest_date = min(first_dates).isoformat() if first_dates else "Unknown"
    latest_date = max(last_dates).isoformat() if last_dates else "Unknown"
    
    # Build metadata header to prepend
    repos_list = ", ".join(r.name for r in repos)
    languages_str = ", ".join([f"{k} ({v}%)" for k, v in all_languages.items()]) if all_languages else "Unknown"
    
    metadata_header = f"""- **Repositories**: {repos_list}
- **Total Commits**: {total_commits}
- **Languages**: {languages_str}
- **Active Period**: {earliest_date} to {latest_date}"""
    
    profiles_text = "\n\n---\n\n".join([
        f"## Repository: {rp['name']}\n\n{rp['profile']}"
        for rp in repo_profiles
    ])
    
    system_prompt = """You are creating a unified developer profile from multiple project analyses.

Combine the insights into a single cohesive profile that:
1. Highlights the breadth of technical skills across projects
2. Identifies common patterns and expertise areas
3. Showcases the most impressive accomplishments WITH the reasoning behind them
4. Maintains specificity - don't generalize away the concrete details
5. Preserves the "why" explanations that demonstrate engineering judgment

Structure:
1. **Summary**: Overall technical profile (2-3 sentences)
2. **Key Technical Skills (used across these codebases)**: Technologies used across projects, with context on HOW they were used
3. **Notable Projects & Contributions**: One section per major project with key accomplishments. For significant work, include "**Why**:" explanations that show the problem being solved or the motivation behind the decision.
4. **Development Philosophy (evidence-based)**: Patterns that emerge across the work, with evidence-based reasoning (e.g., "Instrument first, optimize with data—introduced timing utilities before optimization to avoid guessing at bottlenecks")"""

    user_prompt = f"""Combine these repository analyses into a unified developer profile:

{profiles_text}

Create a cohesive markdown profile that represents the developer's complete body of work, starting with Summary.

Preserve and highlight the "why" explanations that demonstrate engineering judgment—these show the developer thinks about problems, not just code."""

    # Get model for final synthesis
    final_synthesis_model = synthesis_model
    if not final_synthesis_model:
        llm_config = get_llm_config()
        final_synthesis_model = llm_config.get("synthesis_model") or DEFAULT_SYNTHESIS_MODEL
    
    if progress_callback:
        progress_callback(
            step="Finalizing",
            detail="Generating unified developer profile...",
            repo="all",
            progress=95.0,
        )
    
    response = await client.chat.completions.create(
        model=final_synthesis_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=SYNTHESIS_TEMPERATURE,
        max_tokens=16000,
    )
    
    if progress_callback:
        progress_callback(
            step="Complete",
            detail="Profile ready!",
            repo="",
            progress=100.0,
        )
    
    llm_content = response.choices[0].message.content or ""
    
    # Prepend metadata header
    return f"{metadata_header}\n\n---\n\n{llm_content}"

