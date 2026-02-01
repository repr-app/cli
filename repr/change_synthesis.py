"""
Change synthesis - understand file changes across git states.

Detects and synthesizes changes across three git states:
1. Tracked but not staged (working directory)
2. Staged but not committed (index)
3. Committed but not pushed (local commits ahead of remote)

Uses the tripartite codex format for synthesis:
- hook: Engagement hook (<60 chars)
- what: Observable change (1 sentence)
- value: Why it matters (1 sentence)
- problem: What was broken/missing (1 sentence)
- insight: Transferable lesson (1 sentence)
- show: Visual element (code/before-after)
"""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from git import Repo, InvalidGitRepositoryError
from pydantic import BaseModel, Field


class ChangeState(str, Enum):
    """Git state of a change."""
    UNSTAGED = "unstaged"       # Tracked but not staged
    STAGED = "staged"           # Staged but not committed
    UNPUSHED = "unpushed"       # Committed but not pushed


@dataclass
class FileChange:
    """A single file change with its state."""
    path: str
    state: ChangeState
    change_type: str  # A (added), M (modified), D (deleted), R (renamed)
    insertions: int = 0
    deletions: int = 0
    diff_preview: str = ""  # First few lines of diff
    old_path: Optional[str] = None  # For renames


@dataclass
class CommitChange:
    """A commit that hasn't been pushed."""
    sha: str
    message: str
    author: str
    timestamp: datetime
    files: list[FileChange] = field(default_factory=list)


class ChangeSummary(BaseModel):
    """LLM-synthesized summary of changes using tripartite codex."""
    hook: str = Field(default="", description="Engagement hook (<60 chars)")
    what: str = Field(default="", description="Observable change (1 sentence)")
    value: str = Field(default="", description="Why it matters (1 sentence)")
    problem: str = Field(default="", description="What was broken/missing")
    insight: str = Field(default="", description="Transferable lesson")
    show: Optional[str] = Field(default=None, description="Visual element")


@dataclass
class ChangeReport:
    """Complete change report across all git states."""
    repo_path: Path
    timestamp: datetime

    # Changes by state
    unstaged: list[FileChange] = field(default_factory=list)
    staged: list[FileChange] = field(default_factory=list)
    unpushed: list[CommitChange] = field(default_factory=list)

    # Optional synthesis (requires LLM)
    summary: Optional[ChangeSummary] = None

    @property
    def total_files(self) -> int:
        """Total unique files changed."""
        files = set()
        files.update(f.path for f in self.unstaged)
        files.update(f.path for f in self.staged)
        for commit in self.unpushed:
            files.update(f.path for f in commit.files)
        return len(files)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.unstaged or self.staged or self.unpushed)


def get_repo(path: Path) -> Optional[Repo]:
    """Get git repo at path, or None if not a repo."""
    try:
        return Repo(path, search_parent_directories=True)
    except InvalidGitRepositoryError:
        return None


def get_unstaged_changes(repo: Repo) -> list[FileChange]:
    """Get tracked files with unstaged changes (modified in working tree)."""
    changes = []

    # Get diff between index and working tree (create_patch=True to get diff content)
    diffs = repo.index.diff(None, create_patch=True)

    for diff in diffs:
        change_type = "M"
        if diff.new_file:
            change_type = "A"
        elif diff.deleted_file:
            change_type = "D"
        elif diff.renamed:
            change_type = "R"

        # Get diff stats and preview
        insertions = 0
        deletions = 0
        diff_preview = ""

        try:
            diff_text = diff.diff.decode("utf-8", errors="replace") if diff.diff else ""
            lines = diff_text.split("\n")
            insertions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
            # Preview: content lines (skip @@ headers, +++ and --- lines)
            content_lines = [l for l in lines if (l.startswith("+") or l.startswith("-"))
                           and not l.startswith("+++") and not l.startswith("---")]
            diff_preview = "\n".join(content_lines[:15])
        except Exception:
            pass

        changes.append(FileChange(
            path=diff.a_path or diff.b_path,
            state=ChangeState.UNSTAGED,
            change_type=change_type,
            insertions=insertions,
            deletions=deletions,
            diff_preview=diff_preview,
            old_path=diff.rename_from if diff.renamed else None,
        ))

    return changes


def get_staged_changes(repo: Repo) -> list[FileChange]:
    """Get staged changes (in index, not yet committed)."""
    changes = []

    # Get diff between HEAD and index (create_patch=True to get diff content)
    try:
        diffs = repo.head.commit.diff(create_patch=True)
    except ValueError:
        # Empty repo, no HEAD yet
        diffs = repo.index.diff(repo.head.commit, create_patch=True) if repo.head.is_valid() else []

    for diff in diffs:
        change_type = "M"
        if diff.new_file:
            change_type = "A"
        elif diff.deleted_file:
            change_type = "D"
        elif diff.renamed:
            change_type = "R"

        insertions = 0
        deletions = 0
        diff_preview = ""

        try:
            diff_text = diff.diff.decode("utf-8", errors="replace") if diff.diff else ""
            lines = diff_text.split("\n")
            insertions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
            content_lines = [l for l in lines if (l.startswith("+") or l.startswith("-"))
                           and not l.startswith("+++") and not l.startswith("---")]
            diff_preview = "\n".join(content_lines[:15])
        except Exception:
            pass

        changes.append(FileChange(
            path=diff.b_path or diff.a_path,
            state=ChangeState.STAGED,
            change_type=change_type,
            insertions=insertions,
            deletions=deletions,
            diff_preview=diff_preview,
            old_path=diff.rename_from if diff.renamed else None,
        ))

    return changes


def get_unpushed_commits(repo: Repo) -> list[CommitChange]:
    """Get commits that haven't been pushed to remote."""
    commits = []

    # Get current branch
    try:
        branch = repo.active_branch
    except TypeError:
        # Detached HEAD
        return commits

    # Find tracking branch
    tracking = None
    try:
        tracking = branch.tracking_branch()
    except Exception:
        pass

    if not tracking:
        # No upstream - check for any remote with same branch name
        for remote in repo.remotes:
            try:
                remote_ref = f"{remote.name}/{branch.name}"
                if remote_ref in [ref.name for ref in repo.refs]:
                    tracking = repo.refs[remote_ref]
                    break
            except Exception:
                continue

    if not tracking:
        # No remote tracking, can't determine unpushed
        return commits

    # Get commits between tracking branch and HEAD
    try:
        commit_range = f"{tracking.name}..HEAD"
        for commit in repo.iter_commits(commit_range):
            # Get file changes for this commit
            file_changes = []
            try:
                parent = commit.parents[0] if commit.parents else None
                if parent:
                    diffs = parent.diff(commit)
                else:
                    # Initial commit
                    diffs = commit.diff(None)

                for diff in diffs:
                    change_type = "M"
                    if diff.new_file:
                        change_type = "A"
                    elif diff.deleted_file:
                        change_type = "D"
                    elif diff.renamed:
                        change_type = "R"

                    file_changes.append(FileChange(
                        path=diff.b_path or diff.a_path,
                        state=ChangeState.UNPUSHED,
                        change_type=change_type,
                        old_path=diff.rename_from if diff.renamed else None,
                    ))
            except Exception:
                pass

            commits.append(CommitChange(
                sha=commit.hexsha[:7],
                message=commit.message.split("\n")[0],
                author=commit.author.name,
                timestamp=datetime.fromtimestamp(commit.committed_date),
                files=file_changes,
            ))
    except Exception:
        pass

    return commits


def get_change_report(path: Path) -> Optional[ChangeReport]:
    """
    Get comprehensive change report for a repository.

    Args:
        path: Path to repository or file within repository

    Returns:
        ChangeReport with all changes, or None if not a git repo
    """
    repo = get_repo(path)
    if not repo:
        return None

    repo_path = Path(repo.working_dir)

    return ChangeReport(
        repo_path=repo_path,
        timestamp=datetime.now(),
        unstaged=get_unstaged_changes(repo),
        staged=get_staged_changes(repo),
        unpushed=get_unpushed_commits(repo),
    )


# =============================================================================
# LLM Synthesis
# =============================================================================

CHANGE_SYNTHESIS_SYSTEM = """You analyze git changes and create a concise summary using the tripartite codex format.

Given changes across three states (unstaged, staged, unpushed commits), synthesize:

1. HOOK (<60 chars): Engagement hook that captures the essence of the work.
   Be authentic: "Finally fixing that auth bug", "The refactor nobody asked for", "Making tests actually pass"

2. WHAT (1 sentence): The observable change - what would someone see different after these changes?

3. VALUE (1 sentence): Why this matters - user impact, technical benefit, or strategic value.

4. PROBLEM (1 sentence): What was broken, missing, or needed improvement.

5. INSIGHT (1 sentence): A transferable lesson or principle from this work.

6. SHOW (optional): A representative code snippet or before/after if it adds clarity.

Output valid JSON with these exact fields:
- "hook": string (<60 chars)
- "what": string (1 sentence)
- "value": string (1 sentence)
- "problem": string (1 sentence)
- "insight": string (1 sentence)
- "show": string or null
"""

CHANGE_SYNTHESIS_USER = """Synthesize these git changes:

UNSTAGED CHANGES (modified but not staged):
{unstaged}

STAGED CHANGES (ready to commit):
{staged}

UNPUSHED COMMITS:
{unpushed}

Output valid JSON with "hook", "what", "value", "problem", "insight", and "show" fields."""


def format_file_changes(changes: list[FileChange]) -> str:
    """Format file changes for LLM prompt."""
    if not changes:
        return "(none)"

    lines = []
    for c in changes:
        type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(c.change_type, "?")
        stats = f"+{c.insertions}/-{c.deletions}" if c.insertions or c.deletions else ""
        lines.append(f"  {type_icon} {c.path} {stats}")
        if c.diff_preview:
            preview_lines = c.diff_preview.split("\n")[:5]
            for pl in preview_lines:
                lines.append(f"      {pl}")

    return "\n".join(lines)


def format_commit_changes(commits: list[CommitChange]) -> str:
    """Format unpushed commits for LLM prompt."""
    if not commits:
        return "(none)"

    lines = []
    for commit in commits:
        lines.append(f"  [{commit.sha}] {commit.message}")
        for f in commit.files[:5]:
            type_icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(f.change_type, "?")
            lines.append(f"    {type_icon} {f.path}")
        if len(commit.files) > 5:
            lines.append(f"    ... and {len(commit.files) - 5} more files")

    return "\n".join(lines)


GROUP_EXPLAIN_SYSTEM = """You explain git changes concisely. Given a set of file changes, provide a brief 1-2 sentence summary of what's being changed and why it might matter. Be direct and specific."""

GROUP_EXPLAIN_USER = """Explain these {group_type} changes briefly (1-2 sentences):

{changes}"""


async def explain_group(
    group_type: str,
    file_changes: list[FileChange] = None,
    commit_changes: list[CommitChange] = None,
    client=None,  # AsyncOpenAI
    model: str = "gpt-4o-mini",
) -> str:
    """
    Explain a single group of changes.

    Args:
        group_type: "unstaged", "staged", or "unpushed"
        file_changes: List of file changes (for unstaged/staged)
        commit_changes: List of commits (for unpushed)
        client: AsyncOpenAI client
        model: Model to use

    Returns:
        Brief explanation string
    """
    if commit_changes:
        changes_str = format_commit_changes(commit_changes)
    elif file_changes:
        changes_str = format_file_changes(file_changes)
    else:
        return ""

    prompt = GROUP_EXPLAIN_USER.format(
        group_type=group_type,
        changes=changes_str,
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": GROUP_EXPLAIN_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()



async def synthesize_changes(
    report: ChangeReport,
    client,  # AsyncOpenAI
    model: str = "gpt-4o-mini",
) -> ChangeSummary:
    """
    Use LLM to synthesize a change report into tripartite codex format.

    Args:
        report: The change report to synthesize
        client: AsyncOpenAI client
        model: Model to use

    Returns:
        ChangeSummary with synthesized content
    """
    import json

    prompt = CHANGE_SYNTHESIS_USER.format(
        unstaged=format_file_changes(report.unstaged),
        staged=format_file_changes(report.staged),
        unpushed=format_commit_changes(report.unpushed),
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CHANGE_SYNTHESIS_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    return ChangeSummary(
        hook=data.get("hook", ""),
        what=data.get("what", ""),
        value=data.get("value", ""),
        problem=data.get("problem", ""),
        insight=data.get("insight", ""),
        show=data.get("show"),
    )
