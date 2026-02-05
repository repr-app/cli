"""
Auto-update functionality for repr CLI.

Supports multiple installation methods:
- pipx (recommended for CLI tools)
- uv (fast Python package manager)
- pip (traditional)
- Homebrew (macOS)
- Standalone binary
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import httpx

from . import __version__
from .ui import console, print_success, print_error, print_warning, print_info

GITHUB_REPO = "repr-app/cli"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
PYPI_API_URL = "https://pypi.org/pypi/repr-cli/json"
PACKAGE_NAME = "repr-cli"


def parse_version(version: str) -> Tuple[int, ...]:
    """Parse version string into tuple for comparison."""
    # Remove 'v' prefix if present
    version = version.lstrip('v')
    # Handle versions with extra suffixes like "0.2.24.post1"
    version = version.split('.post')[0].split('-')[0].split('+')[0]
    try:
        return tuple(int(x) for x in version.split('.'))
    except ValueError:
        return (0, 0, 0)


def get_latest_version_github() -> Optional[dict]:
    """Fetch latest release info from GitHub."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(GITHUB_API_URL)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def get_latest_version_pypi() -> Optional[str]:
    """Fetch latest version from PyPI."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(PYPI_API_URL)
            response.raise_for_status()
            data = response.json()
            return data.get("info", {}).get("version")
    except Exception:
        return None


def get_latest_version() -> Optional[dict]:
    """
    Fetch latest release info, trying GitHub first then PyPI.
    Returns dict with 'version' and optionally 'release_notes' and 'assets'.
    """
    # Try GitHub first (has release notes and binary assets)
    github_release = get_latest_version_github()
    if github_release:
        version = github_release.get("tag_name", "").lstrip('v')
        return {
            "version": version,
            "release_notes": github_release.get("body", ""),
            "assets": github_release.get("assets", []),
            "source": "github"
        }
    
    # Fallback to PyPI
    pypi_version = get_latest_version_pypi()
    if pypi_version:
        return {
            "version": pypi_version,
            "release_notes": None,
            "assets": [],
            "source": "pypi"
        }
    
    print_error("Failed to check for updates (couldn't reach GitHub or PyPI)")
    return None


def check_for_update() -> Optional[str]:
    """
    Check if a newer version is available.
    Returns the new version string if available, None otherwise.
    """
    release = get_latest_version()
    if not release:
        return None
    
    latest_version = release["version"]
    current = parse_version(__version__)
    latest = parse_version(latest_version)
    
    if latest > current:
        return latest_version
    return None


def get_installation_method() -> str:
    """
    Detect how repr was installed.
    
    Returns one of: 'pipx', 'uv', 'pip', 'homebrew', 'binary', 'unknown'
    """
    repr_path = shutil.which("repr")
    
    if repr_path:
        repr_path_lower = repr_path.lower()
        
        # Check if installed via Homebrew
        if "/homebrew/" in repr_path_lower or "/cellar/" in repr_path_lower:
            return "homebrew"
        
        # Check if it's a standalone binary (PyInstaller)
        if getattr(sys, 'frozen', False):
            return "binary"
        
        # Check for pipx (usually in ~/.local/pipx/venvs/ or similar)
        if "/pipx/" in repr_path_lower or "pipx" in repr_path_lower:
            return "pipx"
        
        # Check for uv (usually in ~/.local/share/uv/ or similar)
        if "/uv/" in repr_path_lower:
            return "uv"
    
    # Try to detect via package managers
    
    # Check pipx first (preferred for CLI tools)
    if shutil.which("pipx"):
        try:
            result = subprocess.run(
                ["pipx", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and PACKAGE_NAME in result.stdout:
                return "pipx"
        except Exception:
            pass
    
    # Check uv
    if shutil.which("uv"):
        try:
            result = subprocess.run(
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and PACKAGE_NAME in result.stdout:
                return "uv"
        except Exception:
            pass
    
    # Check pip
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", PACKAGE_NAME],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return "pip"
    except Exception:
        pass
    
    return "unknown"


def update_via_pipx() -> bool:
    """Update using pipx."""
    print_info("Updating via pipx...")
    try:
        result = subprocess.run(
            ["pipx", "upgrade", PACKAGE_NAME],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return True
        # pipx might say "already up to date" with return code 0
        # or "is already at latest version" which is fine
        if "already" in result.stdout.lower() or "already" in result.stderr.lower():
            return True
        print_error(f"pipx upgrade failed: {result.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print_error("pipx upgrade timed out")
        return False
    except FileNotFoundError:
        print_error("pipx not found. Install with: brew install pipx")
        return False
    except Exception as e:
        print_error(f"pipx update failed: {e}")
        return False


def update_via_uv() -> bool:
    """Update using uv."""
    print_info("Updating via uv...")
    try:
        result = subprocess.run(
            ["uv", "tool", "upgrade", PACKAGE_NAME],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return True
        print_error(f"uv upgrade failed: {result.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print_error("uv upgrade timed out")
        return False
    except FileNotFoundError:
        print_error("uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")
        return False
    except Exception as e:
        print_error(f"uv update failed: {e}")
        return False


def update_via_homebrew() -> bool:
    """Update using Homebrew."""
    print_info("Updating via Homebrew...")
    try:
        # First update brew's knowledge of available packages
        subprocess.run(["brew", "update"], capture_output=True, timeout=60)
        # Then upgrade repr
        result = subprocess.run(
            ["brew", "upgrade", "repr"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return True
        if "already installed" in result.stderr.lower():
            return True
        print_error(f"Homebrew update failed: {result.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print_error("Homebrew upgrade timed out")
        return False
    except FileNotFoundError:
        print_error("brew not found")
        return False
    except Exception as e:
        print_error(f"Homebrew update failed: {e}")
        return False


def update_via_pip() -> bool:
    """Update using pip."""
    print_info("Updating via pip...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return True
        print_error(f"pip update failed: {result.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print_error("pip upgrade timed out")
        return False
    except Exception as e:
        print_error(f"pip update failed: {e}")
        return False


def update_via_binary(release: dict) -> bool:
    """Update standalone binary by downloading from GitHub releases."""
    system = platform.system().lower()
    
    # Determine asset name
    if system == "darwin":
        asset_name = "repr-macos.tar.gz"
    elif system == "linux":
        asset_name = "repr-linux.tar.gz"
    elif system == "windows":
        asset_name = "repr-windows.exe"
    else:
        print_error(f"Unsupported platform: {system}")
        return False
    
    assets = release.get("assets", [])
    if not assets:
        print_error("No binary assets found in release. Try: pipx install repr-cli")
        return False
    
    # Find the asset URL
    asset_url = None
    for asset in assets:
        if asset["name"] == asset_name:
            asset_url = asset["browser_download_url"]
            break
    
    if not asset_url:
        print_error(f"Could not find {asset_name} in release assets")
        return False
    
    print_info(f"Downloading {asset_name}...")
    
    try:
        # Get current executable path
        current_exe = shutil.which("repr") or sys.argv[0]
        current_exe = Path(current_exe).resolve()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Download the asset
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(asset_url)
                response.raise_for_status()
                
                download_path = tmpdir / asset_name
                download_path.write_bytes(response.content)
            
            # Extract if it's a tarball
            if asset_name.endswith(".tar.gz"):
                with tarfile.open(download_path, "r:gz") as tar:
                    tar.extractall(tmpdir)
                new_exe = tmpdir / "repr"
            else:
                new_exe = download_path
            
            # Make executable
            new_exe.chmod(0o755)
            
            # Replace current executable
            backup_path = current_exe.with_suffix(".old")
            
            # Backup current
            if current_exe.exists():
                shutil.move(str(current_exe), str(backup_path))
            
            # Install new
            try:
                shutil.move(str(new_exe), str(current_exe))
                # Remove backup on success
                if backup_path.exists():
                    backup_path.unlink()
            except Exception:
                # Restore backup on failure
                if backup_path.exists():
                    shutil.move(str(backup_path), str(current_exe))
                raise
        
        return True
        
    except Exception as e:
        print_error(f"Binary update failed: {e}")
        return False


def show_release_notes(release: dict) -> None:
    """Display release notes if available."""
    notes = release.get("release_notes")
    if notes and notes.strip():
        console.print()
        console.print("[bold]What's new:[/bold]")
        # Truncate long notes
        lines = notes.strip().split('\n')
        if len(lines) > 10:
            for line in lines[:10]:
                console.print(f"  {line}")
            console.print(f"  [dim]... and {len(lines) - 10} more lines[/dim]")
        else:
            for line in lines:
                console.print(f"  {line}")
        console.print()


def perform_update(force: bool = False) -> bool:
    """
    Check for and perform update.
    Returns True if update was successful or not needed.
    """
    print_info(f"Current version: {__version__}")
    
    release = get_latest_version()
    if not release:
        return False
    
    latest_version = release["version"]
    current = parse_version(__version__)
    latest = parse_version(latest_version)
    
    if latest <= current and not force:
        print_success(f"Already up to date (v{__version__})")
        return True
    
    print_info(f"New version available: v{latest_version}")
    show_release_notes(release)
    
    method = get_installation_method()
    print_info(f"Installation method: {method}")
    
    success = False
    
    if method == "pipx":
        success = update_via_pipx()
    elif method == "uv":
        success = update_via_uv()
    elif method == "homebrew":
        success = update_via_homebrew()
    elif method == "pip":
        success = update_via_pip()
    elif method == "binary":
        success = update_via_binary(release)
    else:
        print_warning("Could not detect installation method.")
        print_info("Try one of these manually:")
        console.print("  • pipx upgrade repr-cli  [dim](recommended)[/dim]")
        console.print("  • uv tool upgrade repr-cli")
        console.print("  • brew upgrade repr")
        console.print("  • pip install --upgrade repr-cli")
        console.print(f"  • Download from https://github.com/{GITHUB_REPO}/releases/latest")
        return False
    
    if success:
        print_success(f"Updated to v{latest_version}")
        print_info("Restart your terminal or run 'repr -v' to verify")
    
    return success
