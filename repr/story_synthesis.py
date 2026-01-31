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

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .models import (
    CommitData,
    ContentIndex,
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


class BatchAnalysis(BaseModel):
    """LLM output for analyzing a batch of commits."""
    stories: list[StoryBoundary] = Field(
        description="List of coherent stories found in the commits"
    )


# =============================================================================
# Prompts
# =============================================================================

STORY_SYNTHESIS_SYSTEM = """You analyze git commits and group them into coherent "stories" - logical units of work.

Your job:
1. Read the batch of commits
2. Group related commits into meaningful stories (features, fixes, refactors)
3. For each group, extract the WHY/WHAT/HOW context

IMPORTANT: Prefer grouping commits over creating many small stories. A story should represent a complete unit of value or logical change. 
- If multiple commits relate to the same feature, GROUP THEM.
- If a commit is a small fix for a previous commit in the batch, GROUP THEM.

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

Rules:
- Every commit must appear in exactly one story
- NEVER leave problem, approach, or implementation_details empty
- Be specific: "Added `UserAuth` class with JWT validation" not "Added auth"
"""

STORY_SYNTHESIS_USER = """Analyze these commits and group them into stories with FULL context:

{commits_text}

Output valid JSON with a "stories" array. Fill in ALL fields with specific details.
Example format:
{{
  "stories": [
    {{
      "commit_shas": ["abc1234"],
      "title": "Add user authentication",
      "problem": "Users could not log in to the application",
      "approach": "Implemented JWT-based auth with refresh tokens",
      "implementation_details": [
        "Added UserAuth class in auth/user_auth.py with login() and verify_token() methods",
        "Created JWT middleware in middleware/jwt.py using PyJWT library",
        "Updated User model with password_hash field and bcrypt hashing"
      ],
      "decisions": ["Chose JWT over sessions for stateless scaling"],
      "category": "feature"
    }}
  ]
}}"""


# =============================================================================
# Synthesis Engine
# =============================================================================

class StorySynthesizer:
    """Synthesizes stories from commits using LLM."""
    
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = "gpt-4o-mini",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or "gpt-4o-mini"
        self._client: AsyncOpenAI | None = None
    
    def _get_client(self) -> AsyncOpenAI:
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
                            # Use configured model if we haven't set one
                            if self.model == "gpt-4o-mini" and llm_config.get("local_model"):
                                self.model = llm_config["local_model"]
                    
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
            
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        
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
        
        # Get LLM analysis
        client = self._get_client()
        commits_text = self._format_commits_for_prompt(commits)
        
        try:
            response = await client.chat.completions.create(
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
            # Log the error for debugging
            import os
            if os.environ.get("REPR_DEBUG"):
                print(f"DEBUG: Exception in LLM call: {type(e).__name__}: {e}")
            
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
            
            # Detect technologies from files
            files_list = sorted(all_files)[:50]  # Cap at 50 files
            technologies = self._detect_tech_stack(files_list)

            # Deterministic ID based on sorted commit SHAs
            # This prevents duplicates if the same stories are generated again
            sorted_shas = sorted(matched_shas)
            story_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"repr-story-{'-'.join(sorted_shas)}"))

            story = Story(
                id=story_id,
                created_at=now,
                updated_at=now,
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
