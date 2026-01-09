"""
Story generation templates.

Provides different prompts for generating stories based on use case:
- resume: Professional accomplishment summaries
- changelog: Technical change documentation
- narrative: Storytelling format
- interview: Behavioral interview preparation
"""

from typing import Any
from pydantic import BaseModel, Field


class StoryOutput(BaseModel):
    """Structured output for a generated story."""
    summary: str = Field(description="One-line technical summary of the work (max 120 chars, no fluff)")
    content: str = Field(description="Full technical description in markdown")


# Template definitions
TEMPLATES = {
    "resume": {
        "name": "Resume",
        "description": "Technical work log for resumes and portfolios",
        "system_prompt": """Extract technical work from commits. Be direct and specific.

Output JSON with:
- summary: One line, max 120 chars. State what was done technically. No adjectives, no fluff.
  Good: "Added JWT refresh token rotation with Redis session store"
  Bad: "Enhanced authentication system with improved security"
- content: Markdown with technical details. What was built, how, what tech.

Rules:
- Name specific technologies, libraries, patterns
- Describe the implementation, not the benefit
- No marketing language (enhanced, streamlined, robust, seamless)
- No resume verbs (spearheaded, leveraged, drove)
- If there's a metric, include it. If not, don't invent one.""",
        "user_prompt_template": """Repository: {repo_name}

Commits:
{commits_summary}

Output JSON with summary and content.""",
    },
    
    "changelog": {
        "name": "Changelog",
        "description": "Technical change documentation for release notes",
        "system_prompt": """Extract changes from commits for a changelog. Be specific.

Output JSON with:
- summary: One line describing the main change (max 120 chars)
- content: Markdown changelog with categories (Added/Changed/Fixed/Removed)

Rules:
- List actual changes, not benefits
- Include file/module names when relevant
- No fluff words (improved, enhanced, better)""",
        "user_prompt_template": """Repository: {repo_name}

Commits:
{commits_summary}

Output JSON with summary and content.""",
    },
    
    "narrative": {
        "name": "Narrative",
        "description": "Technical narrative for blogs or case studies",
        "system_prompt": """Write a technical narrative from commits.

Output JSON with:
- summary: One-line description of what was built (max 120 chars)
- content: Markdown narrative explaining the technical work

Focus on:
- What problem was solved
- How it was implemented technically
- What decisions were made and why

No marketing language. Write like you're explaining to another engineer.""",
        "user_prompt_template": """Repository: {repo_name}

Commits:
{commits_summary}

Output JSON with summary and content.""",
    },
    
    "interview": {
        "name": "Interview Prep",
        "description": "Technical interview preparation",
        "system_prompt": """Extract technical work for interview prep.

Output JSON with:
- summary: One-line technical summary (max 120 chars)
- content: Markdown with situation/task/action/result format

Focus on:
- Specific technical decisions made
- Problems encountered and solutions
- Technologies and patterns used

No resume language. Be specific about what you actually did.""",
        "user_prompt_template": """Repository: {repo_name}

Commits:
{commits_summary}

Output JSON with summary and content.""",
    },
}

# Default template
DEFAULT_TEMPLATE = "resume"


def get_template(name: str) -> dict[str, Any] | None:
    """
    Get a template by name.
    
    Args:
        name: Template name
    
    Returns:
        Template dict or None if not found
    """
    return TEMPLATES.get(name.lower())


def list_templates() -> list[dict[str, str]]:
    """
    List all available templates.
    
    Returns:
        List of template info dicts
    """
    return [
        {
            "name": key,
            "display_name": tmpl["name"],
            "description": tmpl["description"],
        }
        for key, tmpl in TEMPLATES.items()
    ]


def format_commits_for_prompt(commits: list[dict[str, Any]]) -> str:
    """
    Format commit list for inclusion in prompt.
    
    Args:
        commits: List of commit dicts
    
    Returns:
        Formatted string for prompt
    """
    lines = []
    for c in commits:
        sha = c.get("sha", c.get("full_sha", ""))[:7]
        msg = c.get("message", "").split("\n")[0][:80]
        date = c.get("date", "")[:10]
        files = c.get("files", [])
        
        lines.append(f"- [{sha}] {msg}")
        if files:
            # Handle files as either list of dicts or list of strings
            file_names = [
                f["path"] if isinstance(f, dict) else f
                for f in files[:5]
            ]
            lines.append(f"  Files: {', '.join(file_names)}")
            if len(files) > 5:
                lines.append(f"  ... and {len(files) - 5} more files")
        if c.get("insertions") or c.get("deletions"):
            lines.append(f"  Changes: +{c.get('insertions', 0)}/-{c.get('deletions', 0)}")
    
    return "\n".join(lines)


def build_generation_prompt(
    template_name: str,
    repo_name: str,
    commits: list[dict[str, Any]],
    custom_prompt: str | None = None,
) -> tuple[str, str]:
    """
    Build the system and user prompts for story generation.
    
    Args:
        template_name: Name of template to use
        repo_name: Repository name
        commits: List of commit dicts
        custom_prompt: Optional custom prompt to append
    
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    template = get_template(template_name)
    if not template:
        template = TEMPLATES[DEFAULT_TEMPLATE]
    
    system_prompt = template["system_prompt"]
    
    # Format commits
    commits_summary = format_commits_for_prompt(commits)
    
    # Build user prompt
    user_prompt = template["user_prompt_template"].format(
        repo_name=repo_name,
        commits_summary=commits_summary,
    )
    
    # Append custom prompt if provided
    if custom_prompt:
        user_prompt += f"\n\nAdditional instructions: {custom_prompt}"
    
    return system_prompt, user_prompt


def get_template_help() -> str:
    """
    Get help text describing all templates.
    
    Returns:
        Formatted help string
    """
    lines = ["Available templates:\n"]
    
    for key, tmpl in TEMPLATES.items():
        lines.append(f"  {key}")
        lines.append(f"    {tmpl['description']}")
        lines.append("")
    
    return "\n".join(lines)

