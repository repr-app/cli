"""
Social post generator using LLM.

Generates engaging social posts from stories using AI.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from ..storage import generate_ulid
from .models import (
    SocialPlatform,
    SocialDraft,
    DraftStatus,
    get_platform_config,
)
from .formatters import format_story_for_platform


async def generate_with_llm(
    story: Dict[str, Any],
    platform: SocialPlatform,
    additional_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate platform-specific content using LLM.
    
    Falls back to template-based formatting if LLM is unavailable.
    """
    from ..llm import get_llm_client, LLMError
    from ..config import get_llm_config
    
    config = get_platform_config(platform)
    
    # Build the prompt
    platform_instructions = {
        SocialPlatform.TWITTER: """
Write an engaging Twitter post (max 280 chars) about this dev story.
- Be conversational and punchy
- Use 1-2 relevant hashtags
- If the content is rich, suggest a thread (return thread_parts array)
- Focus on the hook and outcome
""",
        SocialPlatform.LINKEDIN: """
Write a professional LinkedIn post about this technical work.
- Professional but approachable tone
- Start with a hook that stops scrolling
- Include the problem, approach, and outcome
- Add a key takeaway
- End with relevant hashtags (3-5)
""",
        SocialPlatform.REDDIT: """
Write a Reddit post title and body.
- Title should spark curiosity (not clickbait)
- Body should be detailed but scannable
- Use markdown formatting
- Include technical details developers appreciate
- Return both 'title' and 'content' fields
""",
        SocialPlatform.HACKERNEWS: """
Write a Hacker News submission.
- Title must be concise and factual (max 80 chars)
- If it's a "Show HN" project, prefix with "Show HN: "
- Content should be technical and substantive
- Return 'title' and optionally 'content' for text posts
""",
        SocialPlatform.INDIEHACKERS: """
Write an IndieHackers post in build-in-public style.
- Personal and relatable narrative
- Share the journey and learnings
- Be authentic about challenges
- End with engagement prompt
- Return 'title' and 'content'
""",
    }
    
    prompt = f"""You are a developer content writer. Generate a social media post for {platform.value}.

{platform_instructions.get(platform, "Write an engaging post.")}

Platform constraints:
- Max content length: {config.max_length} characters
- Title required: {config.requires_title}
- Title max length: {config.title_max_length or 'N/A'}
- Supports threads: {config.supports_threads}

Story to write about:
Title: {story.get('title', 'N/A')}
Hook: {story.get('hook', 'N/A')}
Problem: {story.get('problem', story.get('what', 'N/A'))}
Approach: {story.get('approach', 'N/A')}
Outcome: {story.get('value', story.get('outcome', 'N/A'))}
Insight: {story.get('insight', 'N/A')}
Technologies: {', '.join(story.get('technologies', []))}
Category: {story.get('category', 'feature')}

{f"Additional context: {additional_context}" if additional_context else ""}

Return a JSON object with these fields:
- title (string, if platform requires it)
- content (string, main post content)
- thread_parts (array of strings, for Twitter threads only)

Respond with only the JSON object, no markdown code blocks."""

    try:
        llm_config = get_llm_config()
        client = get_llm_client()
        
        response = await client.chat.completions.create(
            model=llm_config.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a developer content writer. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Clean up potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        result = json.loads(content)
        return result
        
    except Exception as e:
        # Fall back to template-based formatting
        print(f"LLM generation failed, using template: {e}")
        return format_story_for_platform(story, platform)


def generate_draft_from_story(
    story: Dict[str, Any],
    platform: SocialPlatform,
    include_url: Optional[str] = None,
    subreddit: Optional[str] = None,
    use_llm: bool = True,
) -> SocialDraft:
    """
    Generate a social draft from a story.
    
    Args:
        story: Story dictionary
        platform: Target platform
        include_url: URL to include in post
        subreddit: Target subreddit (for Reddit)
        use_llm: Whether to use LLM for generation
    
    Returns:
        SocialDraft ready for review
    """
    import asyncio
    
    if use_llm:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    generate_with_llm(story, platform)
                )
            finally:
                loop.close()
        except Exception:
            # Fall back to template
            result = format_story_for_platform(
                story, platform,
                include_url=include_url,
                subreddit=subreddit or "programming",
            )
    else:
        result = format_story_for_platform(
            story, platform,
            include_url=include_url,
            subreddit=subreddit or "programming",
        )
    
    # Add URL to content if not already included
    if include_url and platform != SocialPlatform.HACKERNEWS:
        content = result.get("content", "")
        if include_url not in content:
            if platform == SocialPlatform.TWITTER and not result.get("thread_parts"):
                # For Twitter, append URL if space allows
                if len(content) + len(include_url) + 2 <= 280:
                    result["content"] = f"{content}\n\n{include_url}"
    
    draft = SocialDraft(
        id=generate_ulid(),
        platform=platform,
        story_id=story.get("id"),
        title=result.get("title"),
        content=result.get("content", ""),
        thread_parts=result.get("thread_parts"),
        url=include_url if platform == SocialPlatform.HACKERNEWS else None,
        subreddit=subreddit or result.get("subreddit"),
        status=DraftStatus.DRAFT,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        auto_generated=True,
    )
    
    return draft


def generate_social_drafts(
    stories: List[Dict[str, Any]],
    platforms: Optional[List[SocialPlatform]] = None,
    include_url_template: Optional[str] = None,
    subreddit: Optional[str] = None,
    use_llm: bool = True,
    limit_per_platform: int = 5,
) -> List[SocialDraft]:
    """
    Generate social drafts for multiple stories and platforms.
    
    Args:
        stories: List of story dictionaries
        platforms: Target platforms (default: all)
        include_url_template: URL template with {story_id} placeholder
        subreddit: Target subreddit for Reddit
        use_llm: Whether to use LLM for generation
        limit_per_platform: Max drafts per platform
    
    Returns:
        List of SocialDraft objects
    """
    if platforms is None:
        platforms = [
            SocialPlatform.TWITTER,
            SocialPlatform.LINKEDIN,
            SocialPlatform.REDDIT,
            SocialPlatform.HACKERNEWS,
            SocialPlatform.INDIEHACKERS,
        ]
    
    drafts = []
    
    # Limit stories
    stories_to_process = stories[:limit_per_platform]
    
    for story in stories_to_process:
        # Build URL if template provided
        url = None
        if include_url_template and story.get("id"):
            url = include_url_template.format(story_id=story["id"])
        
        for platform in platforms:
            try:
                draft = generate_draft_from_story(
                    story=story,
                    platform=platform,
                    include_url=url,
                    subreddit=subreddit,
                    use_llm=use_llm,
                )
                drafts.append(draft)
            except Exception as e:
                print(f"Failed to generate draft for {platform.value}: {e}")
                continue
    
    return drafts


def generate_from_recent_commits(
    days: int = 7,
    platforms: Optional[List[SocialPlatform]] = None,
    use_llm: bool = True,
    limit: int = 5,
    project_path: Optional[str] = None,
) -> List[SocialDraft]:
    """
    Generate social drafts from recent stories.
    
    Args:
        days: Look back this many days
        platforms: Target platforms
        use_llm: Whether to use LLM
        limit: Maximum stories to process
        project_path: Optional path to filter stories by project
    
    Returns:
        List of SocialDraft objects
    """
    from ..db import get_db
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Get recent stories
    all_stories = db.list_stories(limit=100)
    
    # Normalize project path for comparison
    normalized_path = None
    if project_path:
        normalized_path = str(Path(project_path).expanduser().resolve())
    
    def is_recent(story) -> bool:
        if not story.created_at:
            return False
        # Handle both timezone-aware and naive datetimes
        created = story.created_at
        if created.tzinfo is None:
            # Assume UTC for naive datetimes
            created = created.replace(tzinfo=timezone.utc)
        return created >= since
    
    def matches_project(story) -> bool:
        if not normalized_path:
            return True
        # Check if story belongs to this project
        story_path = getattr(story, 'project_path', None) or getattr(story, 'repo_path', None)
        if story_path:
            return str(Path(story_path).resolve()) == normalized_path
        return True  # Include if no path info
    
    recent_stories = [
        s.model_dump() for s in all_stories
        if is_recent(s) and matches_project(s)
    ][:limit]
    
    if not recent_stories:
        return []
    
    return generate_social_drafts(
        stories=recent_stories,
        platforms=platforms,
        use_llm=use_llm,
        limit_per_platform=limit,
    )


def generate_from_project(
    project_path: str,
    days: int = 7,
    platforms: Optional[List[SocialPlatform]] = None,
    use_llm: bool = True,
    limit: int = 5,
) -> List[SocialDraft]:
    """
    Generate social drafts from stories for a specific project.
    
    Args:
        project_path: Path to the git repository
        days: Look back this many days
        platforms: Target platforms
        use_llm: Whether to use LLM
        limit: Maximum stories to process
    
    Returns:
        List of SocialDraft objects
    """
    from ..db import get_db
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Normalize path
    normalized_path = str(Path(project_path).expanduser().resolve())
    
    # Try to find project by path in database
    project_id = None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM projects WHERE path = ?",
            (normalized_path,)
        ).fetchone()
        if row:
            project_id = row["id"]
    
    if not project_id:
        # Fall back to filtering all stories by path
        return generate_from_recent_commits(
            days=days,
            platforms=platforms,
            use_llm=use_llm,
            limit=limit,
            project_path=project_path,
        )
    
    # Get stories for this project
    stories = []
    with db.connect() as conn:
        query = """
            SELECT * FROM stories 
            WHERE project_id = ? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        for row in conn.execute(query, (project_id, since.isoformat(), limit)).fetchall():
            story = dict(row)
            # Deserialize JSON fields
            for field in ["technologies", "implementation_details", "decisions", "lessons"]:
                if story.get(field):
                    try:
                        story[field] = json.loads(story[field])
                    except (json.JSONDecodeError, TypeError):
                        story[field] = []
            stories.append(story)
    
    if not stories:
        return []
    
    return generate_social_drafts(
        stories=stories,
        platforms=platforms,
        use_llm=use_llm,
        limit_per_platform=limit,
    )
