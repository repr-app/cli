"""
Session loader for Gemini Antigravity format.

Gemini Antigravity stores conversations as:
- Protobuf files (.pb) in ~/.gemini/antigravity/conversations/
- Artifacts in ~/.gemini/antigravity/brain/<conversation-id>/
  - task.md - Task checklist
  - implementation_plan.md - Technical plan
  - walkthrough.md - Completion summary
  - *.metadata.json - Timestamps and metadata

Since parsing protobuf requires schema definitions, we extract context
from the markdown artifacts instead, which contain rich information about
the work done, files modified, and decisions made.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..models import (
    ContentBlock,
    ContentBlockType,
    MessageRole,
    Session,
    SessionMessage,
)
from .base import SessionLoader


class GeminiAntigravityLoader(SessionLoader):
    """Loader for Gemini Antigravity session artifacts."""
    
    GEMINI_HOME = Path.home() / ".gemini" / "antigravity" / "brain"
    
    @property
    def name(self) -> str:
        return "gemini_antigravity"
    
    def _extract_project_paths(self, content: str) -> set[str]:
        """
        Extract project paths from markdown file links.
        
        Looks for patterns like: file:///Users/mendrika/Projects/...
        
        Args:
            content: Markdown content
            
        Returns:
            Set of unique project paths
        """
        paths = set()
        # Match file:// links
        file_links = re.findall(r'file://(/[^)]+)', content)
        for link in file_links:
            # Remove line number anchors (#L123-L456)
            path = re.sub(r'#L\d+(-L\d+)?$', '', link)
            paths.add(path)
        return paths
    
    def _find_common_project_root(self, file_paths: set[str]) -> str | None:
        """
        Find the common project root from a set of file paths.
        
        Looks for common git repository roots or project directories.
        
        Args:
            file_paths: Set of file paths
            
        Returns:
            Common project root path or None
        """
        if not file_paths:
            return None
        
        # Convert to Path objects
        paths = [Path(p) for p in file_paths]
        
        # Find common parent
        if len(paths) == 1:
            # Single file - find its git root or parent directory
            path = paths[0]
            current = path.parent if path.is_file() else path
            while current != current.parent:
                if (current / ".git").exists():
                    return str(current)
                current = current.parent
            return str(path.parent)
        
        # Multiple files - find common ancestor
        common = paths[0]
        for path in paths[1:]:
            try:
                # Find common parts
                common_parts = []
                for p1, p2 in zip(common.parts, path.parts):
                    if p1 == p2:
                        common_parts.append(p1)
                    else:
                        break
                if common_parts:
                    common = Path(*common_parts)
                else:
                    return None
            except (ValueError, TypeError):
                continue
        
        # Check if common path has .git
        current = Path(common)
        while current != current.parent:
            if (current / ".git").exists():
                return str(current)
            current = current.parent
        
        return str(common) if common != Path("/") else None
    
    def _matches_project(self, session_dir: Path, project_path: Path) -> bool:
        """
        Check if a session directory contains artifacts related to a project.
        
        Args:
            session_dir: Path to session artifact directory
            project_path: Path to project to match
            
        Returns:
            True if session is related to project
        """
        project_path = project_path.resolve()
        
        # Read all markdown artifacts
        content = ""
        for artifact in ["task.md", "implementation_plan.md", "walkthrough.md"]:
            artifact_path = session_dir / artifact
            if artifact_path.exists():
                try:
                    content += artifact_path.read_text(encoding="utf-8")
                except Exception:
                    continue
        
        if not content:
            return False
        
        # Extract file paths from content
        file_paths = self._extract_project_paths(content)
        if not file_paths:
            return False
        
        # Check if any path is within the project
        for file_path in file_paths:
            try:
                file_path_obj = Path(file_path)
                if file_path_obj == project_path:
                    return True
                if file_path_obj.is_relative_to(project_path):
                    return True
                if project_path.is_relative_to(file_path_obj):
                    return True
            except (ValueError, TypeError):
                continue
        
        return False
    
    def _get_session_timestamps(self, session_dir: Path) -> tuple[datetime | None, datetime | None]:
        """
        Extract start and end timestamps from metadata files.
        
        Args:
            session_dir: Path to session artifact directory
            
        Returns:
            Tuple of (started_at, ended_at)
        """
        timestamps = []
        
        # Read all metadata.json files
        for metadata_file in session_dir.glob("*.metadata.json"):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    if "updatedAt" in metadata:
                        ts_str = metadata["updatedAt"]
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamps.append(ts)
            except Exception:
                continue
        
        if not timestamps:
            # Fallback to directory modification time
            try:
                mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)
                return (mtime, mtime)
            except Exception:
                return (None, None)
        
        timestamps.sort()
        return (timestamps[0], timestamps[-1])
    
    def find_sessions(
        self,
        project_path: str | Path,
        since: datetime | None = None,
    ) -> list[Path]:
        """Find Gemini Antigravity session directories for a project."""
        project_path = Path(project_path).resolve()
        
        if not self.GEMINI_HOME.exists():
            return []
        
        session_dirs = []
        
        # Scan all conversation directories
        for session_dir in self.GEMINI_HOME.iterdir():
            if not session_dir.is_dir():
                continue
            
            # Check if session matches project
            if not self._matches_project(session_dir, project_path):
                continue
            
            # Check timestamp filter
            if since is not None:
                started_at, ended_at = self._get_session_timestamps(session_dir)
                if ended_at is not None:
                    # Handle timezone-aware vs timezone-naive comparison
                    if since.tzinfo is not None and ended_at.tzinfo is None:
                        from datetime import timezone
                        ended_at = ended_at.replace(tzinfo=timezone.utc)
                    elif since.tzinfo is None and ended_at.tzinfo is not None:
                        from datetime import timezone
                        since = since.replace(tzinfo=timezone.utc)
                    
                    if ended_at < since:
                        continue

            
            session_dirs.append(session_dir)
        
        return sorted(session_dirs, key=lambda p: p.name)
    
    def load_session(self, path: Path) -> Session | None:
        """Load a Gemini Antigravity session from an artifact directory."""
        try:
            session_id = path.name
            
            # Get timestamps
            started_at, ended_at = self._get_session_timestamps(path)
            if started_at is None:
                started_at = datetime.now()
            
            # Read artifacts
            task_content = ""
            plan_content = ""
            walkthrough_content = ""
            
            task_path = path / "task.md"
            if task_path.exists():
                try:
                    task_content = task_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            
            plan_path = path / "implementation_plan.md"
            if plan_path.exists():
                try:
                    plan_content = plan_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            
            walkthrough_path = path / "walkthrough.md"
            if walkthrough_path.exists():
                try:
                    walkthrough_content = walkthrough_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            
            # Extract project path
            all_content = task_content + plan_content + walkthrough_content
            file_paths = self._extract_project_paths(all_content)
            cwd = self._find_common_project_root(file_paths)
            
            # Create messages from artifacts
            messages = []
            
            # Extract goal/problem from plan or first task
            goal = self._extract_goal(plan_content, task_content)
            if goal:
                messages.append(SessionMessage(
                    timestamp=started_at,
                    role=MessageRole.USER,
                    content=[ContentBlock(
                        type=ContentBlockType.TEXT,
                        text=goal,
                    )],
                ))
            
            # Extract summary from walkthrough or completed tasks
            summary = self._extract_summary(walkthrough_content, task_content)
            if summary:
                messages.append(SessionMessage(
                    timestamp=ended_at or started_at,
                    role=MessageRole.ASSISTANT,
                    content=[ContentBlock(
                        type=ContentBlockType.TEXT,
                        text=summary,
                    )],
                ))
            
            if not messages:
                # No extractable content
                return None
            
            return Session(
                id=session_id,
                started_at=started_at,
                ended_at=ended_at,
                channel="gemini_antigravity",
                messages=messages,
                cwd=cwd,
                git_branch=None,  # Not available in artifacts
                model="gemini-2.0-flash-thinking-exp",  # Gemini model
            )
            
        except Exception as e:
            import sys
            print(f"Error loading Gemini session {path}: {e}", file=sys.stderr)
            return None
    
    def _extract_goal(self, plan_content: str, task_content: str) -> str | None:
        """Extract the goal/problem from implementation plan or tasks."""
        # Try to extract from implementation plan
        if plan_content:
            # Look for ## Goal section
            goal_match = re.search(r'##\s+Goal\s*\n(.+?)(?:\n##|\Z)', plan_content, re.DOTALL)
            if goal_match:
                goal = goal_match.group(1).strip()
                # Clean up markdown
                goal = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', goal)  # Remove links
                return goal[:500]  # Limit length
            
            # Try first heading
            first_heading = re.search(r'^#\s+(.+)$', plan_content, re.MULTILINE)
            if first_heading:
                return first_heading.group(1).strip()
        
        # Fallback to first task
        if task_content:
            # Find first unchecked or checked task
            task_match = re.search(r'-\s+\[[ x]\]\s+(.+?)(?:\n|$)', task_content)
            if task_match:
                task = task_match.group(1).strip()
                # Remove HTML comments
                task = re.sub(r'<!--.*?-->', '', task).strip()
                return f"Task: {task}"
        
        return None
    
    def _extract_summary(self, walkthrough_content: str, task_content: str) -> str | None:
        """Extract summary from walkthrough or completed tasks."""
        # Try walkthrough first
        if walkthrough_content:
            # Remove title
            content = re.sub(r'^#\s+.+?\n', '', walkthrough_content, count=1)
            # Get first paragraph or section
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.strip().startswith('#')]
            if paragraphs:
                summary = paragraphs[0]
                # Clean up markdown
                summary = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', summary)
                return summary[:1000]
        
        # Fallback to completed tasks summary
        if task_content:
            completed = re.findall(r'-\s+\[x\]\s+(.+?)(?:\n|$)', task_content)
            if completed:
                # Remove HTML comments
                completed = [re.sub(r'<!--.*?-->', '', t).strip() for t in completed]
                return "Completed: " + "; ".join(completed[:5])
        
        return None
