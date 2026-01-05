"""
Local tool implementations for the agentic analysis workflow.

These tools execute locally on the CLI and return results to the server.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError

from .extractor import detect_languages, detect_dependencies, get_file_tree_flat


class ToolError(Exception):
    """Error executing a tool."""
    pass


def execute_tool(tool_name: str, args: dict[str, Any], repos_map: dict[str, Path]) -> Any:
    """
    Execute a tool by name with given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        args: Tool arguments
        repos_map: Mapping of repo names to paths
    
    Returns:
        Tool result
    
    Raises:
        ToolError: If tool execution fails
    """
    tools = {
        "get_recent_commits": get_recent_commits,
        "get_commit_detail": get_commit_detail,
        "read_file": read_file,
        "search_code": search_code,
        "get_file_tree": get_file_tree,
        "get_contributor_stats": get_contributor_stats,
        "get_languages": get_languages,
        "get_dependencies": get_dependencies,
    }
    
    if tool_name not in tools:
        raise ToolError(f"Unknown tool: {tool_name}")
    
    # Resolve repo path
    repo_name = args.get("repo")
    if repo_name and repo_name in repos_map:
        args["repo_path"] = repos_map[repo_name]
    elif repo_name:
        raise ToolError(f"Unknown repository: {repo_name}")
    
    try:
        return tools[tool_name](**args)
    except Exception as e:
        raise ToolError(f"Tool {tool_name} failed: {str(e)}")


def get_recent_commits(
    repo_path: Path,
    count: int | None = None,
    days: int = 365,
    **kwargs,
) -> list[dict[str, Any]]:
    """
    Get recent commits from a repository.
    
    Args:
        repo_path: Path to the repository
        count: Maximum number of commits to retrieve (None = unlimited within time range)
        days: Number of days to look back (default 365 for 1 year)
    
    Returns:
        List of commit objects with metadata
    """
    repo = Repo(repo_path)
    commits = []
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_timestamp = cutoff_date.timestamp()
    
    for commit in repo.iter_commits(max_count=count):
        # Stop if we've gone past the time window
        if commit.committed_date < cutoff_timestamp:
            break
            
        commits.append({
            "sha": commit.hexsha[:8],
            "full_sha": commit.hexsha,
            "message": commit.message.strip().split("\n")[0],  # First line only
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": datetime.fromtimestamp(commit.committed_date).isoformat(),
            "files_changed": len(commit.stats.files),
            "insertions": commit.stats.total["insertions"],
            "deletions": commit.stats.total["deletions"],
        })
    
    return commits


def get_commits_with_diffs(
    repo_path: Path,
    count: int = 100,
    days: int = 365,
    max_diff_lines_per_file: int = 50,
    max_files_per_commit: int = 10,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get commits with actual diff content for LLM analysis.
    
    Args:
        repo_path: Path to the repository
        count: Maximum number of commits to retrieve
        days: Number of days to look back (default 365 for 1 year)
        max_diff_lines_per_file: Maximum diff lines to include per file
        max_files_per_commit: Maximum files to include per commit
        since: Optional SHA or date string to start from (only analyze commits after this)
    
    Returns:
        List of commit objects with diffs
    """
    repo = Repo(repo_path)
    commits = []
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_timestamp = cutoff_date.timestamp()
    
    # Parse since parameter if provided
    since_timestamp: float | None = None
    since_sha: str | None = None
    if since:
        # Try to parse as date first
        try:
            since_date = datetime.fromisoformat(since.replace("Z", "+00:00"))
            since_timestamp = since_date.timestamp()
        except ValueError:
            # Treat as SHA
            since_sha = since
    
    for commit in repo.iter_commits(max_count=count):
        # Stop if we've gone past the time window
        if commit.committed_date < cutoff_timestamp:
            break
        
        # Stop if we've reached the since SHA
        if since_sha and commit.hexsha.startswith(since_sha):
            break
        
        # Skip commits before the since timestamp
        if since_timestamp and commit.committed_date <= since_timestamp:
            break
        
        # Get files changed with diffs
        files = []
        parent = commit.parents[0] if commit.parents else None
        
        try:
            # Get diff for this commit
            if parent:
                diffs = parent.diff(commit, create_patch=True)
            else:
                # Initial commit - show all files as additions
                diffs = commit.diff(None, create_patch=True)
            
            for diff_item in list(diffs)[:max_files_per_commit]:
                file_path = diff_item.b_path or diff_item.a_path
                if not file_path:
                    continue
                
                # Get the diff text
                diff_text = ""
                if diff_item.diff:
                    try:
                        diff_text = diff_item.diff.decode('utf-8', errors='ignore')
                    except:
                        diff_text = str(diff_item.diff)
                    
                    # Truncate diff if too long
                    diff_lines = diff_text.split('\n')
                    if len(diff_lines) > max_diff_lines_per_file:
                        diff_text = '\n'.join(diff_lines[:max_diff_lines_per_file])
                        diff_text += f"\n... ({len(diff_lines) - max_diff_lines_per_file} more lines)"
                
                files.append({
                    "path": file_path,
                    "change_type": diff_item.change_type,  # A=added, D=deleted, M=modified, R=renamed
                    "diff": diff_text,
                })
        except (GitCommandError, Exception):
            # If we can't get diff, just include file list
            for filename in commit.stats.files.keys():
                if len(files) >= max_files_per_commit:
                    break
                files.append({
                    "path": filename,
                    "change_type": "M",
                    "diff": "",
                })
        
        commits.append({
            "sha": commit.hexsha[:8],
            "full_sha": commit.hexsha,
            "message": commit.message.strip(),
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": datetime.fromtimestamp(commit.committed_date).isoformat(),
            "files": files,
            "insertions": commit.stats.total["insertions"],
            "deletions": commit.stats.total["deletions"],
        })
    
    return commits


def get_commit_detail(
    repo_path: Path,
    sha: str,
    **kwargs,
) -> dict[str, Any]:
    """
    Get detailed information about a specific commit.
    
    Args:
        repo_path: Path to the repository
        sha: Commit SHA (full or short)
    
    Returns:
        Detailed commit object with diff stats
    """
    repo = Repo(repo_path)
    commit = repo.commit(sha)
    
    # Get files changed with stats
    files = []
    for filename, stats in commit.stats.files.items():
        files.append({
            "path": filename,
            "insertions": stats["insertions"],
            "deletions": stats["deletions"],
        })
    
    return {
        "sha": commit.hexsha[:8],
        "full_sha": commit.hexsha,
        "message": commit.message.strip(),
        "author": commit.author.name,
        "author_email": commit.author.email,
        "date": datetime.fromtimestamp(commit.committed_date).isoformat(),
        "files": files,
        "total_insertions": commit.stats.total["insertions"],
        "total_deletions": commit.stats.total["deletions"],
    }


def read_file(
    repo_path: Path,
    path: str,
    max_lines: int = 500,
    **kwargs,
) -> dict[str, Any]:
    """
    Read a file from the repository.
    
    Args:
        repo_path: Path to the repository
        path: Relative path to the file
        max_lines: Maximum lines to return
    
    Returns:
        File contents and metadata
    """
    file_path = repo_path / path
    
    if not file_path.exists():
        return {"error": "File not found", "path": path}
    
    if not file_path.is_file():
        return {"error": "Not a file", "path": path}
    
    # Check file size
    size = file_path.stat().st_size
    if size > 1024 * 1024:  # 1MB limit
        return {"error": "File too large", "path": path, "size": size}
    
    try:
        content = file_path.read_text()
        lines = content.split("\n")
        truncated = len(lines) > max_lines
        
        if truncated:
            content = "\n".join(lines[:max_lines])
        
        return {
            "path": path,
            "content": content,
            "lines": min(len(lines), max_lines),
            "truncated": truncated,
            "size": size,
        }
    except UnicodeDecodeError:
        return {"error": "Binary file", "path": path}


def search_code(
    repo_path: Path,
    pattern: str,
    max_results: int = 50,
    **kwargs,
) -> list[dict[str, Any]]:
    """
    Search for a pattern in repository code.
    
    Args:
        repo_path: Path to the repository
        pattern: Regex pattern to search for
        max_results: Maximum number of results
    
    Returns:
        List of matching lines with context
    """
    results = []
    skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return [{"error": f"Invalid regex pattern: {pattern}"}]
    
    for file_path in repo_path.rglob("*"):
        if len(results) >= max_results:
            break
        
        if not file_path.is_file():
            continue
        
        # Skip binary-like extensions and directories
        rel_parts = file_path.relative_to(repo_path).parts
        if any(skip in rel_parts for skip in skip_dirs):
            continue
        
        if file_path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz"}:
            continue
        
        try:
            content = file_path.read_text()
            for line_num, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    results.append({
                        "path": str(file_path.relative_to(repo_path)),
                        "line": line_num,
                        "content": line.strip()[:200],  # Truncate long lines
                    })
                    if len(results) >= max_results:
                        break
        except (UnicodeDecodeError, PermissionError):
            continue
    
    return results


def get_file_tree(
    repo_path: Path,
    depth: int = 3,
    **kwargs,
) -> list[str]:
    """
    Get the file tree structure of a repository.
    
    Args:
        repo_path: Path to the repository
        depth: Maximum depth to traverse
    
    Returns:
        List of file/directory paths
    """
    return get_file_tree_flat(repo_path, max_depth=depth)


def get_contributor_stats(
    repo_path: Path,
    **kwargs,
) -> list[dict[str, Any]]:
    """
    Get contributor statistics for a repository.
    
    Args:
        repo_path: Path to the repository
    
    Returns:
        List of contributors with commit counts
    """
    repo = Repo(repo_path)
    contributors: dict[str, dict[str, Any]] = {}
    
    for commit in repo.iter_commits():
        email = commit.author.email
        if email not in contributors:
            contributors[email] = {
                "name": commit.author.name,
                "email": email,
                "commits": 0,
                "first_commit": datetime.fromtimestamp(commit.committed_date),
                "last_commit": datetime.fromtimestamp(commit.committed_date),
            }
        
        contributors[email]["commits"] += 1
        commit_date = datetime.fromtimestamp(commit.committed_date)
        
        if commit_date < contributors[email]["first_commit"]:
            contributors[email]["first_commit"] = commit_date
        if commit_date > contributors[email]["last_commit"]:
            contributors[email]["last_commit"] = commit_date
    
    # Sort by commit count and format
    result = []
    for email, data in sorted(contributors.items(), key=lambda x: x[1]["commits"], reverse=True):
        result.append({
            "name": data["name"],
            "email": data["email"],
            "commits": data["commits"],
            "first_commit": data["first_commit"].isoformat(),
            "last_commit": data["last_commit"].isoformat(),
        })
    
    return result


def get_languages(
    repo_path: Path,
    **kwargs,
) -> dict[str, float]:
    """
    Get language breakdown for a repository.
    
    Args:
        repo_path: Path to the repository
    
    Returns:
        Dictionary of language -> percentage
    """
    return detect_languages(repo_path)


def get_dependencies(
    repo_path: Path,
    **kwargs,
) -> dict[str, list[str]]:
    """
    Get dependencies for a repository.
    
    Args:
        repo_path: Path to the repository
    
    Returns:
        Dictionary of ecosystem -> list of dependencies
    """
    return detect_dependencies(repo_path)


def get_commits_by_shas(
    repo_path: Path,
    shas: list[str],
    max_diff_lines_per_file: int = 50,
    max_files_per_commit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get specific commits by their SHAs with diffs.
    
    Args:
        repo_path: Path to the repository
        shas: List of commit SHAs (full or short)
        max_diff_lines_per_file: Maximum diff lines to include per file
        max_files_per_commit: Maximum files to include per commit
    
    Returns:
        List of commit objects with diffs in the order of SHAs provided
    """
    repo = Repo(repo_path)
    commits = []
    
    for sha in shas:
        try:
            commit = repo.commit(sha)
        except Exception:
            # Skip invalid SHAs
            continue
        
        # Get files changed with diffs
        files = []
        parent = commit.parents[0] if commit.parents else None
        
        try:
            # Get diff for this commit
            if parent:
                diffs = parent.diff(commit, create_patch=True)
            else:
                # Initial commit - show all files as additions
                diffs = commit.diff(None, create_patch=True)
            
            for diff_item in list(diffs)[:max_files_per_commit]:
                file_path = diff_item.b_path or diff_item.a_path
                if not file_path:
                    continue
                
                # Get the diff text
                diff_text = ""
                if diff_item.diff:
                    try:
                        diff_text = diff_item.diff.decode('utf-8', errors='ignore')
                    except:
                        diff_text = str(diff_item.diff)
                    
                    # Truncate diff if too long
                    diff_lines = diff_text.split('\n')
                    if len(diff_lines) > max_diff_lines_per_file:
                        diff_text = '\n'.join(diff_lines[:max_diff_lines_per_file])
                        diff_text += f"\n... ({len(diff_lines) - max_diff_lines_per_file} more lines)"
                
                files.append({
                    "path": file_path,
                    "change_type": diff_item.change_type,  # A=added, D=deleted, M=modified, R=renamed
                    "diff": diff_text,
                })
        except (GitCommandError, Exception):
            # If we can't get diff, just include file list
            for filename in commit.stats.files.keys():
                if len(files) >= max_files_per_commit:
                    break
                files.append({
                    "path": filename,
                    "change_type": "M",
                    "diff": "",
                })
        
        commits.append({
            "sha": commit.hexsha[:8],
            "full_sha": commit.hexsha,
            "message": commit.message.strip(),
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": datetime.fromtimestamp(commit.committed_date).isoformat(),
            "files": files,
            "insertions": commit.stats.total["insertions"],
            "deletions": commit.stats.total["deletions"],
        })
    
    return commits


def suggest_related_commits(
    repo_path: Path,
    limit: int = 50,
    min_overlap: int = 2,
) -> list[dict[str, Any]]:
    """
    Suggest groups of related commits based on file overlap.
    
    Args:
        repo_path: Path to the repository
        limit: Maximum commits to analyze
        min_overlap: Minimum number of overlapping files to consider commits related
    
    Returns:
        List of suggested commit groups with overlap info
    """
    from collections import defaultdict
    
    # Get recent commits with file info
    commits = get_commits_with_diffs(repo_path, count=limit, days=90)
    
    if len(commits) < 2:
        return []
    
    # Build file -> commits mapping
    file_commits: dict[str, list[int]] = defaultdict(list)
    for idx, commit in enumerate(commits):
        files = commit.get('files', [])
        for file_info in files:
            file_path = file_info.get('path', '')
            if file_path:
                file_commits[file_path].append(idx)
    
    # Find commit pairs with overlapping files
    overlap_scores: dict[tuple[int, int], int] = defaultdict(int)
    overlapping_files: dict[tuple[int, int], set[str]] = defaultdict(set)
    
    for file_path, commit_indices in file_commits.items():
        if len(commit_indices) > 1:
            # These commits touch the same file
            for i in range(len(commit_indices)):
                for j in range(i + 1, len(commit_indices)):
                    idx1, idx2 = commit_indices[i], commit_indices[j]
                    pair = (min(idx1, idx2), max(idx1, idx2))
                    overlap_scores[pair] += 1
                    overlapping_files[pair].add(file_path)
    
    # Filter by minimum overlap and create suggestions
    suggestions = []
    seen_commits = set()
    
    for (idx1, idx2), score in sorted(overlap_scores.items(), key=lambda x: -x[1]):
        if score < min_overlap:
            continue
        
        # Skip if commits already in a group
        if idx1 in seen_commits or idx2 in seen_commits:
            continue
        
        # Find other related commits
        related = [idx1, idx2]
        for idx3 in range(len(commits)):
            if idx3 in seen_commits or idx3 == idx1 or idx3 == idx2:
                continue
            
            # Check overlap with any commit in the group
            overlap_with_group = False
            for group_idx in related:
                pair = (min(idx3, group_idx), max(idx3, group_idx))
                if pair in overlap_scores and overlap_scores[pair] >= min_overlap:
                    overlap_with_group = True
                    break
            
            if overlap_with_group:
                related.append(idx3)
        
        if len(related) >= 2:
            suggestion = {
                'commit_shas': [commits[i]['full_sha'] for i in related],
                'commit_count': len(related),
                'overlap_score': score,
                'overlapping_files': list(overlapping_files[(idx1, idx2)]),
                'summary': f"{len(related)} related commits on {', '.join(list(overlapping_files[(idx1, idx2)])[:3])}",
                'first_commit_message': commits[related[0]]['message'].split('\n')[0],
            }
            suggestions.append(suggestion)
            seen_commits.update(related)
    
    return suggestions[:10]  # Return top 10 suggestions
