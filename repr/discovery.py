"""
Git repository discovery - find repos recursively in directories.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from .config import get_skip_patterns, get_repo_hash, set_repo_hash


@dataclass
class RepoInfo:
    """Information about a discovered repository."""
    
    path: Path
    name: str
    commit_count: int
    user_commit_count: int  # User's own commits
    first_commit_date: datetime | None
    last_commit_date: datetime | None
    primary_language: str | None
    languages: dict[str, int] | None  # Language -> percentage mapping
    contributors: int
    is_fork: bool
    remote_url: str | None
    description: str | None  # From README first line or repo
    frameworks: list[str] | None  # Detected frameworks/libraries
    has_tests: bool  # Has test directory or test files
    has_ci: bool  # Has CI/CD config (.github/workflows, .gitlab-ci, etc.)
    
    @property
    def age_months(self) -> int:
        """Calculate repository age in months."""
        if not self.first_commit_date:
            return 0
        
        now = datetime.now()
        delta = now - self.first_commit_date
        return int(delta.days / 30)
    
    @property
    def age_display(self) -> str:
        """Human-readable age string."""
        months = self.age_months
        if months < 1:
            return "< 1 mo"
        elif months < 12:
            return f"{months} mo"
        else:
            years = months // 12
            return f"{years}+ yr"
    
    def compute_hash(self) -> str:
        """Compute a hash representing the current state of the repo."""
        try:
            repo = Repo(self.path)
            head_sha = repo.head.commit.hexsha
            commit_count = str(self.commit_count)
            hash_input = f"{head_sha}:{commit_count}".encode()
            return hashlib.sha256(hash_input).hexdigest()[:16]
        except Exception:
            return ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "path": str(self.path),
            "name": self.name,
            "commit_count": self.commit_count,
            "first_commit": self.first_commit_date.isoformat() if self.first_commit_date else None,
            "last_commit": self.last_commit_date.isoformat() if self.last_commit_date else None,
            "languages": self.languages or {},
            "contributors": self.contributors,
            "is_fork": self.is_fork,
            "remote_url": self.remote_url,
            "age_months": self.age_months,
        }


def is_git_repo(path: Path) -> bool:
    """Check if a path is a git repository."""
    return (path / ".git").is_dir()


def should_skip_directory(path: Path, skip_patterns: list[str]) -> bool:
    """Check if a directory should be skipped."""
    name = path.name
    
    # Always skip hidden directories (except .git check happens elsewhere)
    if name.startswith(".") and name != ".git":
        return True
    
    # Check against skip patterns
    for pattern in skip_patterns:
        if name == pattern or name.lower() == pattern.lower():
            return True
    
    return False


def discover_repos(
    root_paths: list[Path],
    skip_patterns: list[str] | None = None,
    min_commits: int = 10,
    use_cache: bool = True,
) -> list[RepoInfo]:
    """
    Discover git repositories recursively.
    
    Args:
        root_paths: List of directories to search
        skip_patterns: Patterns to skip (default from config)
        min_commits: Minimum commits to include repo
        use_cache: Whether to use cached repo hashes
    
    Returns:
        List of discovered repositories
    """
    if skip_patterns is None:
        skip_patterns = get_skip_patterns()
    
    repos: list[RepoInfo] = []
    visited_paths: set[Path] = set()
    
    for root_path in root_paths:
        root = Path(root_path).expanduser().resolve()
        if not root.exists():
            continue
        
        # Search for .git directories
        for git_dir in _find_git_dirs(root, skip_patterns, visited_paths):
            repo_path = git_dir.parent
            
            try:
                repo_info = analyze_repo(repo_path)
                
                # Skip repos with too few commits
                if repo_info.commit_count < min_commits:
                    continue
                
                # Check cache if enabled
                if use_cache:
                    cached_hash = get_repo_hash(str(repo_path))
                    current_hash = repo_info.compute_hash()
                    if cached_hash == current_hash:
                        repo_info._cached = True  # type: ignore
                    else:
                        set_repo_hash(str(repo_path), current_hash)
                
                repos.append(repo_info)
                
            except (InvalidGitRepositoryError, GitCommandError, Exception):
                # Skip invalid or problematic repos
                continue
    
    return repos


def _find_git_dirs(
    root: Path,
    skip_patterns: list[str],
    visited: set[Path],
) -> list[Path]:
    """Find all .git directories under root."""
    git_dirs: list[Path] = []
    
    def search(path: Path, depth: int = 0) -> None:
        if depth > 10:  # Limit recursion depth
            return
        
        if path in visited:
            return
        visited.add(path)
        
        try:
            for item in path.iterdir():
                if not item.is_dir():
                    continue
                
                if item.name == ".git":
                    git_dirs.append(item)
                    # Don't recurse into repo subdirectories
                    return
                
                if should_skip_directory(item, skip_patterns):
                    continue
                
                search(item, depth + 1)
        except PermissionError:
            pass
    
    search(root)
    return git_dirs


def analyze_repo(path: Path) -> RepoInfo:
    """
    Analyze a single repository.
    
    Args:
        path: Path to repository root
    
    Returns:
        RepoInfo with repository metadata
    """
    repo = Repo(path)
    
    # Get user's git config for identifying their commits
    user_email = None
    user_name = None
    try:
        user_email = repo.config_reader().get_value("user", "email", default=None)
        user_name = repo.config_reader().get_value("user", "name", default=None)
    except Exception:
        pass
    
    # Get commit counts (total and user's own)
    commit_count = 0
    user_commit_count = 0
    try:
        for commit in repo.iter_commits():
            commit_count += 1
            # Check if commit is by user
            if user_email and commit.author.email == user_email:
                user_commit_count += 1
            elif user_name and commit.author.name == user_name:
                user_commit_count += 1
    except Exception:
        pass
    
    # Get date range
    first_commit_date = None
    last_commit_date = None
    
    try:
        commits = list(repo.iter_commits())
        if commits:
            last_commit_date = datetime.fromtimestamp(commits[0].committed_date)
            first_commit_date = datetime.fromtimestamp(commits[-1].committed_date)
    except Exception:
        pass
    
    # Get contributors
    contributors = set()
    try:
        for commit in repo.iter_commits():
            contributors.add(commit.author.email)
    except Exception:
        pass
    
    # Get remote URL
    remote_url = None
    is_fork = False
    try:
        if repo.remotes:
            remote = repo.remotes.origin
            remote_url = remote.url
            # Simple fork detection - could be improved
            is_fork = "fork" in remote_url.lower() if remote_url else False
    except Exception:
        pass
    
    # Get description from README
    description = _get_repo_description(path)
    
    # Detect frameworks
    frameworks = _detect_frameworks(path)
    
    # Check for tests
    has_tests = _has_tests(path)
    
    # Check for CI/CD
    has_ci = _has_ci(path)
    
    # Primary language and languages will be detected by extractor
    primary_language = None
    languages = None
    
    return RepoInfo(
        path=path,
        name=path.name,
        commit_count=commit_count,
        user_commit_count=user_commit_count,
        first_commit_date=first_commit_date,
        last_commit_date=last_commit_date,
        primary_language=primary_language,
        languages=languages,
        contributors=len(contributors),
        is_fork=is_fork,
        remote_url=remote_url,
        description=description,
        frameworks=frameworks,
        has_tests=has_tests,
        has_ci=has_ci,
    )


def _get_repo_description(path: Path) -> str | None:
    """Extract description from README file."""
    readme_names = ["README.md", "README.rst", "README.txt", "README"]
    for name in readme_names:
        readme_path = path / name
        if readme_path.exists():
            try:
                content = readme_path.read_text(errors='ignore')
                lines = content.strip().split('\n')
                # Skip title (usually starts with #) and get first paragraph
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('!'):
                        # Truncate to reasonable length
                        return line[:200] if len(line) > 200 else line
            except Exception:
                pass
    return None


def _detect_frameworks(path: Path) -> list[str]:
    """Detect frameworks and major libraries used."""
    frameworks = []
    
    # Python frameworks
    requirements_files = ["requirements.txt", "requirements.in", "pyproject.toml", "setup.py"]
    python_frameworks = {
        "fastapi": "FastAPI", "django": "Django", "flask": "Flask",
        "pytorch": "PyTorch", "torch": "PyTorch", "tensorflow": "TensorFlow",
        "pandas": "Pandas", "numpy": "NumPy", "scikit-learn": "scikit-learn",
        "celery": "Celery", "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
    }
    
    for req_file in requirements_files:
        req_path = path / req_file
        if req_path.exists():
            try:
                content = req_path.read_text(errors='ignore').lower()
                for key, name in python_frameworks.items():
                    if key in content and name not in frameworks:
                        frameworks.append(name)
            except Exception:
                pass
    
    # JavaScript/TypeScript frameworks
    package_json = path / "package.json"
    if package_json.exists():
        try:
            import json
            data = json.loads(package_json.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            js_frameworks = {
                "react": "React", "next": "Next.js", "vue": "Vue",
                "angular": "Angular", "svelte": "Svelte", "express": "Express",
                "nestjs": "NestJS", "@nestjs/core": "NestJS",
                "tailwindcss": "Tailwind", "typescript": "TypeScript",
            }
            for key, name in js_frameworks.items():
                if key in deps and name not in frameworks:
                    frameworks.append(name)
        except Exception:
            pass
    
    # Rust frameworks
    cargo_toml = path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text(errors='ignore').lower()
            rust_frameworks = {
                "actix": "Actix", "axum": "Axum", "tokio": "Tokio",
                "rocket": "Rocket", "warp": "Warp",
            }
            for key, name in rust_frameworks.items():
                if key in content and name not in frameworks:
                    frameworks.append(name)
        except Exception:
            pass
    
    # Go frameworks
    go_mod = path / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text(errors='ignore').lower()
            go_frameworks = {
                "gin-gonic": "Gin", "echo": "Echo", "fiber": "Fiber",
            }
            for key, name in go_frameworks.items():
                if key in content and name not in frameworks:
                    frameworks.append(name)
        except Exception:
            pass
    
    return frameworks if frameworks else None


def _has_tests(path: Path) -> bool:
    """Check if repository has tests."""
    test_indicators = [
        "tests", "test", "__tests__", "spec", "specs",
        "pytest.ini", "jest.config.js", "jest.config.ts",
        ".pytest_cache", "conftest.py",
    ]
    for indicator in test_indicators:
        if (path / indicator).exists():
            return True
    
    # Check for test files in src
    for pattern in ["**/test_*.py", "**/*_test.py", "**/*.test.ts", "**/*.spec.ts"]:
        if list(path.glob(pattern)):
            return True
    
    return False


def _has_ci(path: Path) -> bool:
    """Check if repository has CI/CD configuration."""
    ci_paths = [
        ".github/workflows",
        ".gitlab-ci.yml",
        ".circleci",
        "Jenkinsfile",
        ".travis.yml",
        "azure-pipelines.yml",
        ".drone.yml",
        "bitbucket-pipelines.yml",
    ]
    for ci_path in ci_paths:
        if (path / ci_path).exists():
            return True
    return False


def is_config_only_repo(path: Path) -> bool:
    """
    Check if a repository only contains config files (dotfiles, etc).
    
    Args:
        path: Path to repository root
    
    Returns:
        True if repo appears to be config-only
    """
    config_indicators = {
        "dotfiles",
        ".dotfiles",
        "config",
        ".config",
    }
    
    # Check repo name
    if path.name.lower() in config_indicators:
        return True
    
    # Check file types
    code_extensions = {
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".go", ".rs", ".java", ".kt", ".swift",
        ".c", ".cpp", ".h", ".hpp",
        ".rb", ".php", ".cs", ".scala",
    }
    
    has_code = False
    try:
        for file in path.rglob("*"):
            if file.is_file() and file.suffix in code_extensions:
                # Check it's not in a hidden directory
                parts = file.relative_to(path).parts
                if not any(p.startswith(".") for p in parts[:-1]):
                    has_code = True
                    break
    except Exception:
        pass
    
    return not has_code

