"""
Story synthesis from commits and sessions.

Creates coherent Story objects by:
1. Batching commits (time-ordered)
2. Using LLM to decide story boundaries and extract context
3. Linking sessions to stories based on commit overlap
4. Building content index per batch
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Callable

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import get_or_generate_username
from .models import (
    CodeSnippet,
    CommitData,
    ContentIndex,
    FileChange,
    SessionContext,
    Story,
    StoryDigest,
)


# =============================================================================
# LLM Schemas
# =============================================================================

class StoryBoundary(BaseModel):
    """LLM-identified story boundary within a batch of commits."""
    commit_shas: list[str] = Field(description="SHAs of commits that form this story")
    title: str = Field(description="One-line title for this story")
    problem: str = Field(default="", description="What problem was being solved")
    approach: str = Field(default="", description="Technical approach used")
    implementation_details: list[str] = Field(default_factory=list, description="Specific code changes and patterns")
    decisions: list[str] = Field(default_factory=list, description="Key decisions")
    tradeoffs: str = Field(default="")
    outcome: str = Field(default="")
    lessons: list[str] = Field(default_factory=list)
    category: str = Field(default="feature")
    diagram: str | None = Field(default=None, description="ASCII diagram explaining the change")
    technologies: list[str] = Field(default_factory=list, description="Resume-worthy skills demonstrated")


class BatchAnalysis(BaseModel):
    """LLM output for analyzing a batch of commits."""
    stories: list[StoryBoundary] = Field(
        description="List of coherent stories found in the commits"
    )


# =============================================================================
# Prompts
# =============================================================================
PUBLIC_STORY_SYSTEM = """You're creating structured content for a developer's "build in public" feed.

Write like a real developer logging progress, not a blog or marketing post.

Tone rules (VERY IMPORTANT):
- Prefer first-person when natural ("I")
- Be specific and concrete
- Sound like a Slack message to teammates
- Avoid grand metaphors and philosophical language
- Avoid generic lessons or "universal truths"
- Slight messiness is OK — polish is not the goal
- No hype, no thought-leader tone

Given a technical story, compose:

1. HOOK (<60 chars):
   A short first-person dev-log opener.
   Focus on a problem, realization, or change.
   Examples:
   - "I got tired of doing timezone math."
   - "This kept crashing until I found why."
   - "I finally fixed the story engine docs."
   Avoid clickbait and drama.

2. WHAT (1 sentence):
   What you actually changed.
   Concrete, observable behavior only.

3. VALUE (1 sentence):
   Why this matters to users or teammates.
   Practical impact > abstract value.

4. INSIGHT (1 sentence):
   A grounded takeaway from THIS change.
   Not universal wisdom — just what you learned.

5. SHOW (optional):
   Code or before/after only if it adds clarity.

6. POST_BODY (2–5 sentences):
   Write the final post in a natural voice.
   - First person
   - Mention what changed and why
   - Include one small detail (a file/function/user pain) for authenticity
   - You MAY include the insight, but do NOT label it "Insight:"
   - Should not feel templated or like a changelog

Output JSON with these exact fields:
- "hook": string (<60 chars)
- "what": string (1 sentence)
- "value": string (1 sentence)
- "insight": string (1 sentence)
- "show": string or null
- "post_body": string
"""


PUBLIC_STORY_USER = """Turn this into a first-person build-in-public dev log:

Title: {title}
Category: {category}
Problem: {problem}
Approach: {approach}
Outcome: {outcome}
Implementation Details: {implementation_details}

Write like a developer explaining their own work.

Output valid JSON with "hook", "what", "value", "insight", "show", and "post_body" fields."""

INTERNAL_STORY_SYSTEM = """You're creating structured content for a developer's internal feed.

Write like an engineer documenting work for teammates.

Tone rules:
- First-person preferred
- Direct and practical
- No marketing or philosophical tone
- Say what happened, why, and what changed
- Avoid abstract language

Given a technical story:

1. HOOK (<60 chars):
   A short first-person dev-log line.

2. WHAT (1 sentence):
   Observable change made.

3. VALUE (1 sentence):
   Why this helps users or the team.

4. PROBLEM (1 sentence):
   What was broken or missing.

5. HOW (list):
   Concrete technical actions taken (files/functions/patterns).

6. INSIGHT (1 sentence):
   Practical lesson from this change.

7. SHOW (optional):
   Only include if useful.

8. POST_BODY (3–6 sentences):
   A natural internal update for teammates.
   - First person
   - Mention the problem briefly, what you changed, and any gotchas
   - Reference 1–2 concrete details (file/function/config)
   - No templated structure, no headings

Output JSON with:
- "hook"
- "what"
- "value"
- "problem"
- "how"
- "insight"
- "show"
- "post_body"
"""

INTERNAL_STORY_USER = """Extract this as a first-person internal dev log:

Title: {title}
Category: {category}
Problem: {problem}
Approach: {approach}
Outcome: {outcome}
Implementation Details: {implementation_details}
Decisions: {decisions}
Files: {files}

Write like a developer explaining their own work.

Output valid JSON with "hook", "what", "value", "problem", "how", "insight", "show", and "post_body" fields."""

STORY_SYNTHESIS_SYSTEM = """You analyze git commits and group them into coherent "stories" - logical units of work.

Your job:
1. Read the batch of commits
2. Group related commits into meaningful stories (features, fixes, refactors)
3. For each group, extract the WHY/WHAT/HOW context

IMPORTANT: A story should represent ONE coherent unit of value. Apply these rules:

GROUPING (consolidate):
- Multiple commits for the same feature → GROUP into one story
- A commit + its follow-up fix → GROUP together

SPLITTING (unpack):
- A single commit with MULTIPLE UNRELATED changes → SPLIT into separate stories
- Look for signs of a "packed" commit:
  * Commit message lists multiple things ("Add X, fix Y, update Z")
  * Files changed span unrelated areas (e.g., auth + UI + docs)
  * Insertions/deletions suggest multiple distinct changes
- When splitting, the same commit SHA can appear in multiple stories
- Each split story should have its own distinct title, problem, and approach

Output JSON with a "stories" array. EVERY field must be filled in - do not leave any empty:

Required fields for each story:
- commit_shas: List of commit SHAs that form this story (REQUIRED)
- title: One-line title describing the work (REQUIRED)
- problem: What was lacking/broken/needed? WHY was this change made? (REQUIRED)
- approach: HOW was it solved? What strategy or pattern? (REQUIRED)
- implementation_details: List of SPECIFIC code changes made (REQUIRED - at least 2 items):
  * What files were modified and how
  * What functions/classes were added or changed
  * What patterns or techniques were used
  * Any APIs, libraries, or frameworks involved
- decisions: List of key choices made, format: ["Chose X because Y", ...]
- category: One of: feature, bugfix, refactor, perf, infra, docs, test, chore
- technologies: Resume-worthy skills demonstrated (REQUIRED - be specific):
  * Frameworks/libraries: React, FastAPI, scikit-learn, PyTorch, Next.js, Prisma, SQLAlchemy
  * Infrastructure: Kubernetes, Docker, Terraform, AWS Lambda, GCP, Nginx
  * Tools/practices: CI/CD, GitHub Actions, Redis, PostgreSQL, GraphQL, REST API
  * Patterns: WebSockets, OAuth, JWT, Event-driven, CQRS
  * NOT just languages - those are inferred from files

Optional field:
- diagram: ASCII diagram explaining the change visually (null if not helpful)
  Include a diagram ONLY when it adds clarity for:
  * Architecture changes (component relationships, data flow)
  * State machine or flow changes (before/after)
  * API/interface changes (request/response flow)
  * Refactoring (module structure changes)

  Diagram style: Use simple box-and-arrow ASCII art. Max 15 lines.
  Example:
  ```
  Before:           After:
  [Client]          [Client]
      |                 |
      v                 v
  [Server]          [Cache] --> [Server]
  ```

Rules:
- Every commit must appear in at least one story
- A packed commit may appear in MULTIPLE stories if it contains distinct changes
- NEVER leave problem, approach, or implementation_details empty
- Be specific: "Added `UserAuth` class with JWT validation" not "Added auth"
- Use plain engineering language in titles and summaries
- Avoid dramatic or philosophical phrasing
- Prefer literal descriptions over metaphors
"""

STORY_SYNTHESIS_USER = """Analyze these commits and group them into stories with FULL context:

{commits_text}

Output valid JSON with a "stories" array. Fill in ALL fields with specific details.

Example 1 - Normal story:
{{
  "stories": [
    {{
      "commit_shas": ["abc1234"],
      "title": "Add user authentication",
      "problem": "Users could not log in to the application",
      "approach": "Implemented JWT-based auth with refresh tokens",
      "implementation_details": [
        "Added UserAuth class in auth/user_auth.py with login() and verify_token() methods",
        "Created JWT middleware in middleware/jwt.py using PyJWT library"
      ],
      "decisions": ["Chose JWT over sessions for stateless scaling"],
      "category": "feature",
      "technologies": ["JWT", "bcrypt", "FastAPI"],
      "diagram": null
    }}
  ]
}}

Example 2 - Splitting a packed commit (same SHA in multiple stories):
If commit "def5678" has message "Add auth, fix navbar, update docs" and touches unrelated files:
{{
  "stories": [
    {{
      "commit_shas": ["def5678"],
      "title": "Add user authentication",
      "problem": "...",
      "approach": "...",
      ...
    }},
    {{
      "commit_shas": ["def5678"],
      "title": "Fix navbar alignment",
      "problem": "...",
      "approach": "...",
      ...
    }},
    {{
      "commit_shas": ["def5678"],
      "title": "Update API documentation",
      "problem": "...",
      "approach": "...",
      ...
    }}
  ]
}}

Note: "diagram" is optional. Only include when it clarifies architecture/flow changes."""


# =============================================================================
# File Change Extraction
# =============================================================================

def extract_file_changes_from_commits(
    commit_shas: list[str],
    project_path: str | None = None,
) -> tuple[list[FileChange], int, int]:
    """
    Extract detailed file changes from git commits.

    Args:
        commit_shas: List of commit SHAs to analyze
        project_path: Path to git repo (optional, uses cwd)

    Returns:
        Tuple of (file_changes, total_insertions, total_deletions)
    """
    try:
        from git import Repo
        from pathlib import Path

        repo_path = Path(project_path) if project_path else Path.cwd()
        repo = Repo(repo_path, search_parent_directories=True)
    except Exception:
        return [], 0, 0

    # Aggregate file stats across all commits
    file_stats: dict[str, dict] = {}  # path -> {insertions, deletions, change_type}
    total_ins = 0
    total_del = 0

    for sha in commit_shas:
        try:
            commit = repo.commit(sha)

            # Get per-file stats
            for file_path, stats in commit.stats.files.items():
                ins = stats.get("insertions", 0)
                dels = stats.get("deletions", 0)

                if file_path not in file_stats:
                    file_stats[file_path] = {
                        "insertions": 0,
                        "deletions": 0,
                        "change_type": "modified",
                    }

                file_stats[file_path]["insertions"] += ins
                file_stats[file_path]["deletions"] += dels
                total_ins += ins
                total_del += dels

                # Determine change type
                if ins > 0 and dels == 0 and file_stats[file_path]["deletions"] == 0:
                    file_stats[file_path]["change_type"] = "added"
                elif dels > 0 and ins == 0 and file_stats[file_path]["insertions"] == 0:
                    file_stats[file_path]["change_type"] = "deleted"

        except Exception:
            continue

    # Convert to FileChange objects
    file_changes = [
        FileChange(
            file_path=path,
            change_type=stats["change_type"],
            insertions=stats["insertions"],
            deletions=stats["deletions"],
        )
        for path, stats in sorted(file_stats.items())
    ]

    return file_changes, total_ins, total_del


def extract_key_snippets_from_commits(
    commit_shas: list[str],
    project_path: str | None = None,
    max_snippets: int = 3,
    max_lines: int = 15,
) -> list[CodeSnippet]:
    """
    Extract representative code snippets from commit diffs.

    Args:
        commit_shas: List of commit SHAs
        project_path: Path to git repo
        max_snippets: Maximum number of snippets to return
        max_lines: Maximum lines per snippet

    Returns:
        List of CodeSnippet objects
    """
    try:
        from git import Repo
        from pathlib import Path

        repo_path = Path(project_path) if project_path else Path.cwd()
        repo = Repo(repo_path, search_parent_directories=True)
    except Exception:
        return []

    snippets = []
    seen_files = set()

    # Language detection by extension
    ext_to_lang = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".rb": "ruby", ".php": "php", ".c": "c",
        ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".cs": "csharp",
        ".swift": "swift", ".kt": "kotlin", ".sql": "sql",
        ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".md": "markdown", ".html": "html", ".css": "css", ".scss": "scss",
    }

    for sha in commit_shas:
        if len(snippets) >= max_snippets:
            break

        try:
            commit = repo.commit(sha)

            # Get diff with parent
            if not commit.parents:
                continue
            parent = commit.parents[0]

            for diff in parent.diff(commit, create_patch=True):
                if len(snippets) >= max_snippets:
                    break

                file_path = diff.b_path or diff.a_path
                if not file_path or file_path in seen_files:
                    continue

                # Skip binary and non-code files
                ext = Path(file_path).suffix.lower()
                if ext not in ext_to_lang:
                    continue

                seen_files.add(file_path)

                # Extract added lines from diff
                try:
                    diff_text = diff.diff.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                # Find added lines (lines starting with +, not ++)
                added_lines = []
                for line in diff_text.split("\n"):
                    if line.startswith("+") and not line.startswith("+++"):
                        added_lines.append(line[1:])  # Remove the + prefix

                if not added_lines:
                    continue

                # Take first max_lines of meaningful additions
                content_lines = []
                for line in added_lines:
                    stripped = line.strip()
                    # Skip empty lines, imports, and simple syntax
                    if stripped and not stripped.startswith(("import ", "from ", "#", "//", "/*", "*")):
                        content_lines.append(line)
                    if len(content_lines) >= max_lines:
                        break

                if len(content_lines) < 2:  # Need at least 2 meaningful lines
                    continue

                snippets.append(CodeSnippet(
                    file_path=file_path,
                    language=ext_to_lang.get(ext, ""),
                    content="\n".join(content_lines),
                    line_count=len(content_lines),
                    context=f"Changes in {Path(file_path).name}",
                ))

        except Exception:
            continue

    return snippets


# =============================================================================
# Synthesis Engine
# =============================================================================

class StorySynthesizer:
    """Synthesizes stories from commits using LLM."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self._model_override = model  # Explicit override
        self._model: str | None = None  # Resolved model (lazy)
        self._client: OpenAI | None = None

    @property
    def model(self) -> str:
        """Get the model to use, reading from config if not set."""
        if self._model is None:
            self._model = self._resolve_model()
        return self._model

    @model.setter
    def model(self, value: str):
        """Allow setting model directly."""
        self._model = value

    def _resolve_model(self) -> str:
        """Resolve model from override, config, or default."""
        if self._model_override:
            return self._model_override

        try:
            from .config import get_llm_config
            llm_config = get_llm_config()
            default_mode = llm_config.get("default", "local")

            # Priority: synthesis_model > mode-specific model > default
            if llm_config.get("synthesis_model"):
                return llm_config["synthesis_model"]

            # Use model based on configured default mode
            if default_mode == "local" and llm_config.get("local_model"):
                return llm_config["local_model"]
            elif default_mode == "cloud" and llm_config.get("cloud_model"):
                return llm_config["cloud_model"]

            # Fallback to any configured model
            if llm_config.get("local_model"):
                return llm_config["local_model"]
            if llm_config.get("cloud_model"):
                return llm_config["cloud_model"]
        except Exception:
            pass

        return "gpt-4o-mini"  # Final fallback

    def _get_client(self) -> OpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            import os

            api_key = self.api_key
            base_url = self.base_url

            if not api_key:
                try:
                    from .config import get_byok_config, get_llm_config, get_litellm_config

                    # Check BYOK first
                    byok = get_byok_config("openai")
                    if byok and byok.get("api_key"):
                        api_key = byok["api_key"]
                        base_url = base_url or byok.get("base_url")

                    # Check local LLM config
                    if not api_key:
                        llm_config = get_llm_config()
                        if llm_config.get("local_api_key"):
                            api_key = llm_config["local_api_key"]
                            base_url = base_url or llm_config.get("local_api_url")

                    # Check LiteLLM
                    if not api_key:
                        litellm_url, litellm_key = get_litellm_config()
                        if litellm_key:
                            api_key = litellm_key
                            base_url = base_url or litellm_url
                except Exception:
                    pass

                if not api_key:
                    api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                raise ValueError("No API key found. Configure via 'repr llm byok openai <key>'")

            self._client = OpenAI(api_key=api_key, base_url=base_url)

        return self._client
    
    def _format_commits_for_prompt(self, commits: list[CommitData]) -> str:
        """Format commits for LLM prompt."""
        lines = []
        for c in commits:
            lines.append(f"SHA: {c.sha[:8]}")
            lines.append(f"Message: {c.message}")
            lines.append(f"Files: {', '.join(c.files[:10])}")
            if c.insertions or c.deletions:
                lines.append(f"Changes: +{c.insertions}/-{c.deletions}")
            lines.append("")
        return "\n".join(lines)
    
    async def synthesize_batch(
        self,
        commits: list[CommitData],
        sessions: list[SessionContext] | None = None,
    ) -> tuple[list[Story], ContentIndex]:
        """
        Synthesize stories from a batch of commits.

        Args:
            commits: Commits to analyze (ordered by time)
            sessions: Optional sessions to link

        Returns:
            Tuple of (stories, updated_index)
        """
        if not commits:
            return [], ContentIndex()

        # Get LLM analysis (using sync client to avoid event loop cleanup issues)
        client = self._get_client()
        commits_text = self._format_commits_for_prompt(commits)

        try:
            response = client.chat.completions.create(
                model=self.model.split("/")[-1] if "/" in self.model else self.model,
                messages=[
                    {"role": "system", "content": STORY_SYNTHESIS_SYSTEM},
                    {"role": "user", "content": STORY_SYNTHESIS_USER.format(
                        commits_text=commits_text
                    )},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            content = response.choices[0].message.content

            # Strip markdown code fences if present (many models wrap JSON in ```json blocks)
            content = content.strip()
            if content.startswith("```"):
                # Remove opening fence
                first_newline = content.find("\n")
                if first_newline > 0:
                    content = content[first_newline + 1:]
                # Remove closing fence
                if content.endswith("```"):
                    content = content[:-3].rstrip()

            # Debug: show raw response if REPR_DEBUG is set
            import os
            if os.environ.get("REPR_DEBUG"):
                print(f"DEBUG: Raw LLM response ({len(content)} chars):")
                print(content[:1000])

            analysis = BatchAnalysis.model_validate_json(content)

        except Exception as e:
            # Always print error for visibility
            from rich.console import Console
            Console(stderr=True).print(f"[yellow]  LLM error: {type(e).__name__}: {e}[/]")

            # Fallback: each commit is its own story
            analysis = BatchAnalysis(stories=[
                StoryBoundary(
                    commit_shas=[c.sha],
                    title=c.message.split("\n")[0][:80],
                    category="chore",
                )
                for c in commits
            ])
        
        # Build commit lookup - support both full and prefix matching
        commit_map = {c.sha: c for c in commits}
        
        def find_commit_by_sha(sha: str) -> CommitData | None:
            """Find commit by full or prefix SHA."""
            if sha in commit_map:
                return commit_map[sha]
            # Try prefix matching
            for full_sha, commit in commit_map.items():
                if full_sha.startswith(sha):
                    return commit
            return None
        
        # Create stories
        now = datetime.now(timezone.utc)
        stories = []
        
        for boundary in analysis.stories:
            # Get commits for this story (with prefix matching)
            story_commits = []
            matched_shas = []
            for sha in boundary.commit_shas:
                commit = find_commit_by_sha(sha)
                if commit:
                    story_commits.append(commit)
                    matched_shas.append(commit.sha)  # Use full SHA
            
            if not story_commits:
                continue
            
            # Aggregate files
            all_files = set()
            for c in story_commits:
                all_files.update(c.files)
            
            # Calculate timespan
            timestamps = [c.timestamp for c in story_commits]
            started_at = min(timestamps)
            ended_at = max(timestamps)
            
            # Find linked sessions (by commit overlap)
            linked_sessions = []
            if sessions:
                for session in sessions:
                    if any(sha in session.linked_commits for sha in boundary.commit_shas):
                        linked_sessions.append(session.session_id)
            
            # Use LLM-extracted technologies, fall back to file-based detection
            files_list = sorted(all_files)[:50]  # Cap at 50 files
            technologies = boundary.technologies if boundary.technologies else self._detect_tech_stack(files_list)

            # Extract detailed file changes and snippets for recall
            file_changes, total_ins, total_del = extract_file_changes_from_commits(matched_shas)
            key_snippets = extract_key_snippets_from_commits(matched_shas, max_snippets=3)

            # Deterministic ID based on sorted commit SHAs + title
            # Include title to differentiate stories split from the same packed commit
            sorted_shas = sorted(matched_shas)
            id_input = f"repr-story-{'-'.join(sorted_shas)}-{boundary.title}"
            story_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, id_input))

            # Get author: profile username > GPG-derived mnemonic > git author > unknown
            if identity := get_or_generate_username():
                author_name = identity
            elif story_commits and story_commits[0].author:
                author_name = story_commits[0].author
            else:
                author_name = "unknown"

            # Get email from first commit for Gravatar
            author_email = story_commits[0].author_email if story_commits else ""

            story = Story(
                id=story_id,
                created_at=now,
                updated_at=now,
                author_name=author_name,
                author_email=author_email,
                commit_shas=matched_shas,  # Use full matched SHAs
                session_ids=linked_sessions,
                title=boundary.title,
                problem=boundary.problem,
                approach=boundary.approach,
                implementation_details=boundary.implementation_details,
                decisions=boundary.decisions,
                tradeoffs=boundary.tradeoffs,
                outcome=boundary.outcome,
                lessons=boundary.lessons,
                category=boundary.category,
                technologies=technologies,
                files=files_list,
                started_at=started_at,
                ended_at=ended_at,
                diagram=boundary.diagram,
                # Recall data
                file_changes=file_changes,
                key_snippets=key_snippets,
                total_insertions=total_ins,
                total_deletions=total_del,
            )
            stories.append(story)
        
        # Build index for this batch
        index = self._build_index(stories)
        
        return stories, index
    
    def _build_index(self, stories: list[Story]) -> ContentIndex:
        """Build content index from stories."""
        index = ContentIndex(
            last_updated=datetime.now(timezone.utc),
            story_count=len(stories),
        )
        
        for story in stories:
            # File → story mapping
            for f in story.files:
                if f not in index.files_to_stories:
                    index.files_to_stories[f] = []
                index.files_to_stories[f].append(story.id)
            
            # Keyword extraction (simple: from title and problem)
            keywords = self._extract_keywords(story.title + " " + story.problem)
            for kw in keywords:
                if kw not in index.keywords_to_stories:
                    index.keywords_to_stories[kw] = []
                index.keywords_to_stories[kw].append(story.id)
            
            # Weekly index
            if story.started_at:
                week = story.started_at.strftime("%Y-W%W")
                if week not in index.by_week:
                    index.by_week[week] = []
                index.by_week[week].append(story.id)
            
            # Story digest
            index.story_digests.append(StoryDigest(
                story_id=story.id,
                title=story.title,
                problem_keywords=keywords[:10],
                files=story.files[:5],
                tech_stack=self._detect_tech_stack(story.files),
                category=story.category,
                timestamp=story.started_at or story.created_at,
            ))
        
        return index
    
    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text (simple approach)."""
        import re
        
        # Split on non-word chars, lowercase, filter short words
        words = re.findall(r'\b[a-z]+\b', text.lower())
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'for', 'to', 'in', 'on', 'of', 'and', 'or', 'with', 'from'}
        keywords = [w for w in words if len(w) > 2 and w not in stopwords]
        
        # Dedupe while preserving order
        seen = set()
        result = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
        
        return result
    
    def _detect_tech_stack(self, files: list[str]) -> list[str]:
        """Detect technologies from file extensions/names."""
        tech = set()
        
        ext_map = {
            '.py': 'Python',
            '.ts': 'TypeScript',
            '.tsx': 'React',
            '.js': 'JavaScript',
            '.jsx': 'React',
            '.go': 'Go',
            '.rs': 'Rust',
            '.vue': 'Vue',
            '.sql': 'SQL',
            '.prisma': 'Prisma',
            '.graphql': 'GraphQL',
        }
        
        file_map = {
            'Dockerfile': 'Docker',
            'docker-compose': 'Docker',
            'package.json': 'Node.js',
            'pyproject.toml': 'Python',
            'Cargo.toml': 'Rust',
            'go.mod': 'Go',
        }
        
        for f in files:
            # Check extensions
            for ext, name in ext_map.items():
                if f.endswith(ext):
                    tech.add(name)
            
            # Check filenames
            for fname, name in file_map.items():
                if fname in f:
                    tech.add(name)
        
        return sorted(tech)


# =============================================================================
# Convenience Functions
# =============================================================================

async def synthesize_stories(
    commits: list[CommitData],
    sessions: list[SessionContext] | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    batch_size: int = 25,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[Story], ContentIndex]:
    """
    Synthesize stories from commits with batching.
    
    Args:
        commits: All commits to process
        sessions: Optional sessions for enrichment
        api_key: API key for LLM
        model: Model to use
        batch_size: Commits per batch
        progress_callback: Optional progress callback(current, total)
    
    Returns:
        Tuple of (all_stories, merged_index)
    """
    synthesizer = StorySynthesizer(api_key=api_key, model=model)
    
    all_stories = []
    merged_index = ContentIndex(last_updated=datetime.now(timezone.utc))
    
    # Process in batches
    total_batches = (len(commits) + batch_size - 1) // batch_size
    
    for i in range(0, len(commits), batch_size):
        batch = commits[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        if progress_callback:
            progress_callback(batch_num, total_batches)
        
        stories, index = await synthesizer.synthesize_batch(batch, sessions)
        all_stories.extend(stories)
        
        # Merge index
        for f, story_ids in index.files_to_stories.items():
            if f not in merged_index.files_to_stories:
                merged_index.files_to_stories[f] = []
            merged_index.files_to_stories[f].extend(story_ids)
        
        for kw, story_ids in index.keywords_to_stories.items():
            if kw not in merged_index.keywords_to_stories:
                merged_index.keywords_to_stories[kw] = []
            merged_index.keywords_to_stories[kw].extend(story_ids)
        
        for week, story_ids in index.by_week.items():
            if week not in merged_index.by_week:
                merged_index.by_week[week] = []
            merged_index.by_week[week].extend(story_ids)
        
        merged_index.story_digests.extend(index.story_digests)
    
    merged_index.story_count = len(all_stories)
    
    return all_stories, merged_index


def synthesize_stories_sync(
    commits: list[CommitData],
    sessions: list[SessionContext] | None = None,
    **kwargs,
) -> tuple[list[Story], ContentIndex]:
    """Synchronous wrapper for synthesize_stories."""
    return asyncio.run(synthesize_stories(commits, sessions, **kwargs))


# =============================================================================
# Public/Internal Story Transformation
# =============================================================================

class PublicStory(BaseModel):
    """LLM output for public-facing story (Tripartite Codex)."""
    hook: str = Field(description="Engagement hook, <60 chars")
    what: str = Field(description="Behavioral primitive - observable change")
    value: str = Field(description="External why - user/stakeholder value")
    insight: str = Field(description="Transferable engineering lesson")
    show: str | None = Field(default=None, description="Optional visual/code block")
    post_body: str = Field(description="Final natural post text (2–5 sentences)")


class InternalStory(BaseModel):
    """LLM output for internal story with full technical context."""
    hook: str = Field(description="Engagement hook, <60 chars")
    what: str = Field(description="Behavioral primitive - observable change")
    value: str = Field(description="External why - user/stakeholder value")
    problem: str = Field(default="", description="Internal why - what was broken/missing")
    how: list[str] = Field(default_factory=list, description="Implementation details")
    insight: str = Field(description="Transferable engineering lesson")
    show: str | None = Field(default=None, description="Optional visual/code block")
    post_body: str = Field(description="Final natural internal update (3–6 sentences)")


async def transform_story_for_feed(
    story: Story,
    mode: str = "public",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> PublicStory | InternalStory:
    """
    Transform a technical story into a build-in-public feed post.

    Args:
        story: The Story to transform
        mode: "public" (impact only) or "internal" (with technical details)
        api_key: Optional API key
        base_url: Optional base URL for API
        model: Optional model name

    Returns:
        PublicStory or InternalStory depending on mode
    """
    synthesizer = StorySynthesizer(api_key=api_key, base_url=base_url, model=model)
    client = synthesizer._get_client()
    model_name = synthesizer.model

    # Format implementation details
    impl_details = "\n".join(f"- {d}" for d in story.implementation_details) if story.implementation_details else "None"
    decisions = "\n".join(f"- {d}" for d in story.decisions) if story.decisions else "None"
    files = ", ".join(story.files[:10]) if story.files else "None"

    if mode == "public":
        system_prompt = PUBLIC_STORY_SYSTEM
        user_prompt = PUBLIC_STORY_USER.format(
            title=story.title,
            category=story.category,
            problem=story.problem or "Not specified",
            approach=story.approach or "Not specified",
            outcome=story.outcome or "Not specified",
            implementation_details=impl_details,
        )
        response_model = PublicStory
    else:
        system_prompt = INTERNAL_STORY_SYSTEM
        user_prompt = INTERNAL_STORY_USER.format(
            title=story.title,
            category=story.category,
            problem=story.problem or "Not specified",
            approach=story.approach or "Not specified",
            outcome=story.outcome or "Not specified",
            implementation_details=impl_details,
            decisions=decisions,
            files=files,
        )
        response_model = InternalStory

    try:
        # Use sync client to avoid event loop cleanup issues
        response = client.chat.completions.create(
            model=model_name.split("/")[-1] if "/" in model_name else model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            first_newline = content.find("\n")
            if first_newline > 0:
                content = content[first_newline + 1:]
            if content.endswith("```"):
                content = content[:-3].rstrip()

        result = response_model.model_validate_json(content)

        # Quality check: if hook is empty or too generic, or post_body is empty/short, regenerate
        if not result.hook or len(result.hook) < 10:
            result = _enhance_with_fallback(result, story, mode)
        elif not result.post_body or len(result.post_body.strip()) < 40:
            result = _enhance_with_fallback(result, story, mode)

        return result

    except Exception as e:
        # Print error for visibility
        from rich.console import Console
        Console(stderr=True).print(f"[yellow]  Transform error: {type(e).__name__}: {e}[/]")
        # Fallback: construct structured content from available data
        return _build_fallback_codex(story, mode)


def _build_post_body_public(hook: str, what: str, value: str, insight: str) -> str:
    """Build natural post body for public mode."""
    what_clean = what.rstrip(".").rstrip()
    value_clean = value.lstrip(".").lstrip()
    return (
        f"{hook}\n\n"
        f"{what_clean}. {value_clean}\n"
        f"{insight}"
    ).strip()


def _build_post_body_internal(hook: str, problem: str, what: str, how: list[str], insight: str) -> str:
    """Build natural post body for internal mode."""
    detail = how[0] if how else ""
    what_clean = what.rstrip(".").rstrip()
    body = f"{hook}\n\n{problem}\n\n{what_clean}."
    if detail:
        detail_clean = detail.rstrip(".").rstrip()
        body += f" First change: {detail_clean}."
    body += f" {insight}"
    return body.strip()


def _build_fallback_codex(story: Story, mode: str) -> PublicStory | InternalStory:
    """Build structured Tripartite Codex content when LLM fails."""
    import random

    # Hook variations by category
    category_hooks = {
        "feature": [
            "Finally built the thing.",
            "New capability unlocked.",
            "This changes everything. (Well, something.)",
            "Shipped it.",
        ],
        "bugfix": [
            "One less thing to worry about.",
            "The bug is dead. Long live the code.",
            "Found it. Fixed it. Done.",
            "That crash? Gone.",
        ],
        "refactor": [
            "Same behavior. Better code.",
            "Future me will thank present me.",
            "Cleaned up the mess.",
            "Technical debt: paid.",
        ],
        "perf": [
            "Faster now.",
            "Speed boost shipped.",
            "Shaved off the milliseconds.",
            "Performance win.",
        ],
        "infra": [
            "Infrastructure that just works.",
            "Set it up. Forgot about it.",
            "The plumbing nobody sees.",
            "Foundation laid.",
        ],
        "docs": [
            "Wrote it down so I won't forget.",
            "Documentation: the async communication.",
            "Now it's not just in my head.",
            "Future onboarding: simplified.",
        ],
        "test": [
            "Now I can refactor with confidence.",
            "Tests: the safety net.",
            "Covered.",
            "One more thing that won't break silently.",
        ],
        "chore": [
            "Housekeeping done.",
            "Small fix. Big relief.",
            "Maintenance mode.",
            "Keeping things tidy.",
        ],
    }

    category_insights = {
        "feature": "New capabilities unlock new possibilities.",
        "bugfix": "Fewer edge cases mean more reliable software.",
        "refactor": "Cleaner code is easier to extend.",
        "perf": "Performance gains compound over time.",
        "infra": "Good infrastructure is invisible until it's missing.",
        "docs": "Documentation is a gift to your future self.",
        "test": "Tests are the safety net that enables bold changes.",
        "chore": "Small maintenance prevents big problems.",
    }

    hooks = category_hooks.get(story.category, category_hooks["chore"])
    hook = random.choice(hooks)

    # Build what from title
    what = story.title.rstrip(".")

    # Build value from outcome or generate
    value = story.outcome if story.outcome else f"Improves the {story.category} workflow."

    # Build insight
    insight = category_insights.get(story.category, "Incremental progress adds up.")

    if mode == "public":
        post_body = _build_post_body_public(hook, what, value, insight)
        return PublicStory(
            hook=hook,
            what=what,
            value=value,
            insight=insight,
            show=None,
            post_body=post_body,
        )
    else:
        problem = story.problem or "Needed improvement."
        how = story.implementation_details or []
        post_body = _build_post_body_internal(hook, problem, what, how, insight)
        return InternalStory(
            hook=hook,
            what=what,
            value=value,
            problem=problem,
            how=how,
            insight=insight,
            show=None,
            post_body=post_body,
        )


def _enhance_with_fallback(result: PublicStory | InternalStory, story: Story, mode: str) -> PublicStory | InternalStory:
    """Enhance a weak LLM result with fallback data."""
    import random

    category_hooks = {
        "feature": ["Finally built the thing.", "New capability unlocked.", "Shipped it."],
        "bugfix": ["One less thing to worry about.", "Found it. Fixed it.", "That crash? Gone."],
        "refactor": ["Same behavior. Better code.", "Technical debt: paid.", "Cleaned up."],
        "perf": ["Faster now.", "Speed boost shipped.", "Performance win."],
        "infra": ["Infrastructure that works.", "Foundation laid.", "Set up and running."],
        "docs": ["Wrote it down.", "Now it's documented.", "Future-proofed the knowledge."],
        "test": ["Now I can refactor safely.", "Covered.", "Tests added."],
        "chore": ["Housekeeping done.", "Small fix. Big relief.", "Tidied up."],
    }

    hooks = category_hooks.get(story.category, ["Done."])
    new_hook = random.choice(hooks)

    if mode == "public":
        what = result.what or story.title
        value = result.value or story.outcome or "Improvement shipped."
        insight = result.insight or "Progress is progress."
        post_body = getattr(result, "post_body", "") or _build_post_body_public(
            new_hook, what, value, insight
        )
        return PublicStory(
            hook=new_hook,
            what=what,
            value=value,
            insight=insight,
            show=result.show,
            post_body=post_body,
        )
    else:
        what = result.what or story.title
        problem = result.problem if hasattr(result, 'problem') and result.problem else (story.problem or "")
        how = result.how if hasattr(result, 'how') and result.how else (story.implementation_details or [])
        insight = result.insight or "Progress is progress."
        post_body = getattr(result, "post_body", "") or _build_post_body_internal(
            new_hook, problem, what, how, insight
        )
        return InternalStory(
            hook=new_hook,
            what=what,
            value=result.value or story.outcome or "Improvement shipped.",
            problem=problem,
            how=how,
            insight=insight,
            show=result.show,
            post_body=post_body,
        )


# Legacy function for backward compatibility
def _build_fallback_post(story: Story) -> str:
    """Build a legacy post string from story data."""
    result = _build_fallback_codex(story, "public")
    return result.post_body


def transform_story_for_feed_sync(
    story: Story,
    mode: str = "public",
    **kwargs,
) -> PublicStory | InternalStory:
    """Synchronous wrapper for transform_story_for_feed."""
    return asyncio.run(transform_story_for_feed(story, mode, **kwargs))
