"""
Story generation templates.

Provides different prompts for generating stories based on use case:
- resume: Professional accomplishment summaries
- changelog: Technical change documentation
- narrative: Storytelling format
- interview: Behavioral interview preparation
"""

from typing import Any


# Template definitions
TEMPLATES = {
    "resume": {
        "name": "Resume",
        "description": "Professional accomplishment summaries for resumes and portfolios",
        "system_prompt": """You are helping a developer document their work accomplishments for a professional resume or portfolio.

Focus on:
- Quantifiable impact where possible (performance improvements, user metrics, etc.)
- Technical complexity and problem-solving
- Leadership and collaboration
- Technologies and skills demonstrated

Write in first person, using action verbs. Keep it concise and impactful.
Format: 2-3 bullet points per accomplishment, each 1-2 sentences.""",
        "user_prompt_template": """Based on these commits, write professional accomplishment summaries:

Repository: {repo_name}
Commits:
{commits_summary}

Generate 1-3 accomplishment summaries suitable for a resume.""",
    },
    
    "changelog": {
        "name": "Changelog",
        "description": "Technical change documentation for release notes",
        "system_prompt": """You are writing technical changelog entries for a software project.

Focus on:
- What changed (features, fixes, improvements)
- Why it matters (user impact, developer experience)
- Breaking changes or migration notes
- Technical details relevant to other developers

Use conventional changelog format with categories:
- Added: New features
- Changed: Changes to existing functionality
- Fixed: Bug fixes
- Removed: Removed features
- Security: Security improvements""",
        "user_prompt_template": """Generate changelog entries from these commits:

Repository: {repo_name}
Commits:
{commits_summary}

Write changelog entries grouped by category.""",
    },
    
    "narrative": {
        "name": "Narrative",
        "description": "Storytelling format for blogs or case studies",
        "system_prompt": """You are helping a developer tell the story of their work in an engaging narrative format.

Focus on:
- The challenge or problem being solved
- The approach and decision-making process
- Obstacles encountered and how they were overcome
- Results and lessons learned

Write in a conversational, engaging tone suitable for a blog post or case study.
Use present tense for engagement. Include technical details but make it accessible.""",
        "user_prompt_template": """Tell the story of this development work:

Repository: {repo_name}
Commits:
{commits_summary}

Write a narrative (2-3 paragraphs) that would work as a blog post section.""",
    },
    
    "interview": {
        "name": "Interview Prep",
        "description": "Behavioral interview preparation with STAR format",
        "system_prompt": """You are helping a developer prepare for behavioral interviews using the STAR method.

Format each accomplishment as:
- Situation: Context and background
- Task: What needed to be done
- Action: What you did specifically
- Result: The outcome and impact

Focus on:
- Technical decision-making
- Problem-solving approach
- Collaboration and communication
- Quantifiable results""",
        "user_prompt_template": """Create interview-ready stories from these commits:

Repository: {repo_name}
Commits:
{commits_summary}

Generate 1-2 STAR-format stories for behavioral interviews.""",
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

