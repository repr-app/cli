"""
Platform-specific formatters for social posts.

Each formatter takes a story and produces platform-optimized content.
"""

from typing import Optional, List, Dict, Any
from .models import (
    SocialPlatform,
    TwitterThread,
    get_platform_config,
)


def _truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)].rstrip() + suffix


def _extract_key_tech(technologies: List[str], max_items: int = 3) -> str:
    """Extract key technologies as hashtags or mentions."""
    if not technologies:
        return ""
    # Filter out generic terms
    generic = {"python", "javascript", "typescript", "react", "node", "git"}
    key_tech = [t for t in technologies[:max_items * 2] if t.lower() not in generic][:max_items]
    if not key_tech:
        key_tech = technologies[:max_items]
    return " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in key_tech)


def format_for_twitter(
    story: Dict[str, Any],
    include_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a story for Twitter/X.
    
    Returns:
        {
            "content": str,           # Main tweet (first if thread)
            "thread_parts": List[str], # Thread continuation (if any)
            "is_thread": bool,
        }
    
    Strategy:
    - If hook + value fit in 280 chars: single tweet
    - Otherwise: create a thread with hook -> what -> value -> insight
    """
    config = get_platform_config(SocialPlatform.TWITTER)
    max_len = config.max_length
    
    hook = story.get("hook", "") or story.get("title", "")
    what = story.get("what", "") or story.get("problem", "")
    value = story.get("value", "") or story.get("outcome", "")
    insight = story.get("insight", "")
    technologies = story.get("technologies", [])
    
    # Try single tweet first
    tech_tags = _extract_key_tech(technologies, 2)
    url_suffix = f"\n\n{include_url}" if include_url else ""
    
    # Attempt 1: Hook + value (punchy)
    single_tweet = f"{hook}"
    if value:
        single_tweet = f"{hook}\n\n{value}"
    if tech_tags:
        single_tweet += f"\n\n{tech_tags}"
    single_tweet += url_suffix
    
    if len(single_tweet) <= max_len:
        return {
            "content": single_tweet,
            "thread_parts": None,
            "is_thread": False,
        }
    
    # Attempt 2: Just hook
    minimal_tweet = f"{_truncate(hook, max_len - len(url_suffix) - len(tech_tags) - 2)}"
    if tech_tags:
        minimal_tweet += f"\n\n{tech_tags}"
    minimal_tweet += url_suffix
    
    if len(minimal_tweet) <= max_len and not what:
        return {
            "content": minimal_tweet,
            "thread_parts": None,
            "is_thread": False,
        }
    
    # Build thread
    thread_parts = []
    
    # Tweet 1: Hook (attention grabber)
    t1 = f"{_truncate(hook, max_len - 10)}\n\n🧵 Thread:"
    if len(t1) > max_len:
        t1 = f"{_truncate(hook, max_len - 15)}\n\n🧵"
    thread_parts.append(t1)
    
    # Tweet 2: What/Problem
    if what:
        t2 = f"The problem:\n\n{_truncate(what, max_len - 20)}"
        thread_parts.append(t2)
    
    # Tweet 3: Value/Outcome
    if value:
        t3 = f"The result:\n\n{_truncate(value, max_len - 20)}"
        thread_parts.append(t3)
    
    # Tweet 4: Insight/Learning (if present)
    if insight:
        t4 = f"Key insight:\n\n{_truncate(insight, max_len - 20)}"
        thread_parts.append(t4)
    
    # Final tweet: CTA + tech tags + URL
    final = "That's a wrap!"
    if tech_tags:
        final += f"\n\n{tech_tags}"
    if include_url:
        final += f"\n\nFull story: {include_url}"
    if len(final) <= max_len:
        thread_parts.append(final)
    
    return {
        "content": thread_parts[0] if thread_parts else "",
        "thread_parts": thread_parts[1:] if len(thread_parts) > 1 else None,
        "is_thread": len(thread_parts) > 1,
    }


def format_for_linkedin(
    story: Dict[str, Any],
    include_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a story for LinkedIn.
    
    Strategy: Professional tone, longer form narrative.
    Structure:
    - Hook (attention line)
    - Problem/Context
    - Approach
    - Outcome/Value
    - Key takeaway
    - Hashtags
    """
    config = get_platform_config(SocialPlatform.LINKEDIN)
    max_len = config.max_length
    
    hook = story.get("hook", "") or story.get("title", "")
    problem = story.get("problem", "") or story.get("what", "")
    approach = story.get("approach", "")
    value = story.get("value", "") or story.get("outcome", "")
    insight = story.get("insight", "")
    technologies = story.get("technologies", [])
    
    # Build the post
    parts = []
    
    # Hook (make it punchy)
    if hook:
        parts.append(f"{hook}")
        parts.append("")  # Empty line
    
    # Problem/Context
    if problem:
        parts.append(f"The challenge: {problem}")
        parts.append("")
    
    # Approach (brief)
    if approach:
        approach_brief = _truncate(approach, 500)
        parts.append(f"The approach: {approach_brief}")
        parts.append("")
    
    # Value/Outcome
    if value:
        parts.append(f"The result: {value}")
        parts.append("")
    
    # Key insight
    if insight:
        parts.append(f"💡 Key takeaway: {insight}")
        parts.append("")
    
    # URL
    if include_url:
        parts.append(f"Read the full story: {include_url}")
        parts.append("")
    
    # Hashtags (professional style)
    if technologies:
        tech_tags = " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in technologies[:5])
        parts.append(tech_tags)
        parts.append("#BuildInPublic #SoftwareEngineering #TechStory")
    
    content = "\n".join(parts)
    return {
        "content": _truncate(content, max_len),
    }


def format_for_reddit(
    story: Dict[str, Any],
    subreddit: str = "programming",
    include_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a story for Reddit.
    
    Strategy: Title that sparks curiosity + detailed body.
    """
    config = get_platform_config(SocialPlatform.REDDIT)
    
    hook = story.get("hook", "") or story.get("title", "")
    problem = story.get("problem", "") or story.get("what", "")
    approach = story.get("approach", "")
    value = story.get("value", "") or story.get("outcome", "")
    insight = story.get("insight", "")
    technologies = story.get("technologies", [])
    
    # Title: Hook or derived from problem
    title = _truncate(hook, config.title_max_length or 300)
    if not title:
        title = _truncate(f"How I solved: {problem}", config.title_max_length or 300)
    
    # Body
    body_parts = []
    
    if problem:
        body_parts.append(f"## The Problem\n\n{problem}")
    
    if approach:
        body_parts.append(f"## The Approach\n\n{approach}")
    
    if value:
        body_parts.append(f"## The Result\n\n{value}")
    
    if insight:
        body_parts.append(f"## Key Takeaway\n\n{insight}")
    
    if technologies:
        tech_list = ", ".join(technologies[:10])
        body_parts.append(f"**Tech used:** {tech_list}")
    
    if include_url:
        body_parts.append(f"\n---\n[Full story and code]({include_url})")
    
    body = "\n\n".join(body_parts)
    
    return {
        "title": title,
        "content": _truncate(body, config.max_length),
        "subreddit": subreddit,
    }


def format_for_hackernews(
    story: Dict[str, Any],
    include_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a story for Hacker News.
    
    Strategy: Concise, technical title. HN prefers:
    - "Show HN: ..." for projects
    - Factual titles (not clickbait)
    - URL submissions or text posts
    """
    config = get_platform_config(SocialPlatform.HACKERNEWS)
    
    hook = story.get("hook", "") or story.get("title", "")
    problem = story.get("problem", "") or story.get("what", "")
    value = story.get("value", "") or story.get("outcome", "")
    insight = story.get("insight", "")
    technologies = story.get("technologies", [])
    category = story.get("category", "feature")
    
    # Determine if this should be "Show HN" or regular post
    is_show_hn = category in ["feature", "project", "release"]
    
    # Build title
    if is_show_hn and hook:
        title = f"Show HN: {_truncate(hook, (config.title_max_length or 80) - 10)}"
    elif hook:
        title = _truncate(hook, config.title_max_length or 80)
    else:
        title = _truncate(problem, config.title_max_length or 80)
    
    # Text content (for self-posts without URL)
    text_parts = []
    
    if problem and not include_url:
        text_parts.append(problem)
    
    if value:
        text_parts.append(f"\n{value}")
    
    if insight:
        text_parts.append(f"\nKey insight: {insight}")
    
    if technologies:
        tech_list = ", ".join(technologies[:5])
        text_parts.append(f"\nTech: {tech_list}")
    
    text = "".join(text_parts) if text_parts else None
    
    return {
        "title": title,
        "content": _truncate(text, config.max_length) if text else None,
        "url": include_url,
        "is_show_hn": is_show_hn,
    }


def format_for_indiehackers(
    story: Dict[str, Any],
    include_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a story for IndieHackers.
    
    Strategy: Personal narrative, build-in-public style.
    Focus on the journey, learnings, and relatability.
    """
    config = get_platform_config(SocialPlatform.INDIEHACKERS)
    
    hook = story.get("hook", "") or story.get("title", "")
    problem = story.get("problem", "") or story.get("what", "")
    approach = story.get("approach", "")
    value = story.get("value", "") or story.get("outcome", "")
    insight = story.get("insight", "")
    technologies = story.get("technologies", [])
    
    # Title: Hook or "Building in public: ..."
    if hook:
        title = _truncate(hook, config.title_max_length or 100)
    else:
        title = _truncate(f"Building: {problem}", config.title_max_length or 100)
    
    # Body: Personal narrative style
    body_parts = []
    
    body_parts.append(f"Hey IH! 👋")
    body_parts.append("")
    
    if problem:
        body_parts.append(f"**What I was trying to solve:**\n{problem}")
        body_parts.append("")
    
    if approach:
        body_parts.append(f"**How I approached it:**\n{approach}")
        body_parts.append("")
    
    if value:
        body_parts.append(f"**What happened:**\n{value}")
        body_parts.append("")
    
    if insight:
        body_parts.append(f"**The big lesson:**\n{insight}")
        body_parts.append("")
    
    if technologies:
        tech_list = ", ".join(technologies[:8])
        body_parts.append(f"**Tech stack:** {tech_list}")
        body_parts.append("")
    
    if include_url:
        body_parts.append(f"[Check out the full story]({include_url})")
        body_parts.append("")
    
    body_parts.append("Would love to hear your thoughts! 🙏")
    
    body = "\n".join(body_parts)
    
    return {
        "title": title,
        "content": _truncate(body, config.max_length),
    }


# Formatter registry
FORMATTERS = {
    SocialPlatform.TWITTER: format_for_twitter,
    SocialPlatform.LINKEDIN: format_for_linkedin,
    SocialPlatform.REDDIT: format_for_reddit,
    SocialPlatform.HACKERNEWS: format_for_hackernews,
    SocialPlatform.INDIEHACKERS: format_for_indiehackers,
}

# Parameters accepted by each formatter
FORMATTER_PARAMS = {
    SocialPlatform.TWITTER: {"include_url"},
    SocialPlatform.LINKEDIN: {"include_url"},
    SocialPlatform.REDDIT: {"include_url", "subreddit"},
    SocialPlatform.HACKERNEWS: {"include_url"},
    SocialPlatform.INDIEHACKERS: {"include_url"},
}


def format_story_for_platform(
    story: Dict[str, Any],
    platform: SocialPlatform,
    **kwargs,
) -> Dict[str, Any]:
    """Format a story for a specific platform."""
    formatter = FORMATTERS.get(platform)
    if not formatter:
        raise ValueError(f"Unknown platform: {platform}")
    
    # Filter kwargs to only pass what the formatter accepts
    allowed_params = FORMATTER_PARAMS.get(platform, set())
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}
    
    return formatter(story, **filtered_kwargs)
