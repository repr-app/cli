"""
Auto-update functionality for repr CLI.
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


def parse_version(version: str) -> Tuple[int, ...]:
    """Parse version string into tuple for comparison."""
    # Remove 'v' prefix if present
    version = version.lstrip('v')
    try:
        return tuple(int(x) for x in version.split('.'))
    except ValueError:
        return (0, 0, 0)


def get_latest_version() -> Optional[dict]:
    """Fetch latest release info from GitHub."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(GITHUB_API_URL)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print_error(f"Failed to check for updates: {e}")
        return None


def check_for_update() -> Optional[str]:
    """
    Check if a newer version is available.
    Returns the new version string if available, None otherwise.
    """
    release = get_latest_version()
    if not release:
        return None
    
    latest_version = release.get("tag_name", "").lstrip('v')
    current = parse_version(__version__)
    latest = parse_version(latest_version)
    
    if latest > current:
        return latest_version
    return None


def get_installation_method() -> str:
    """Detect how repr was installed."""
    executable = sys.executable
    repr_path = shutil.which("repr")
    
    if repr_path:
        # Check if installed via Homebrew
        if "/homebrew/" in repr_path.lower() or "/cellar/" in repr_path.lower():
            return "homebrew"
        
        # Check if it's a standalone binary (PyInstaller)
        if getattr(sys, 'frozen', False):
            return "binary"
    
    # Check if installed via pip
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "repr-cli"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return "pip"
    except Exception:
        pass
    
    return "unknown"


def update_via_homebrew() -> bool:
    """Update using Homebrew."""
    print_info("Updating via Homebrew...")
    try:
        subprocess.run(["brew", "update"], check=True)
        subprocess.run(["brew", "upgrade", "repr"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Homebrew update failed: {e}")
        return False


def update_via_pip() -> bool:
    """Update using pip."""
    print_info("Updating via pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "repr-cli"],
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
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
    
    # Find the asset URL
    asset_url = None
    for asset in release.get("assets", []):
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


def perform_update(force: bool = False) -> bool:
    """
    Check for and perform update.
    Returns True if update was successful or not needed.
    """
    print_info(f"Current version: {__version__}")
    
    release = get_latest_version()
    if not release:
        return False
    
    latest_version = release.get("tag_name", "").lstrip('v')
    current = parse_version(__version__)
    latest = parse_version(latest_version)
    
    if latest <= current and not force:
        print_success(f"Already up to date (v{__version__})")
        return True
    
    print_info(f"New version available: v{latest_version}")
    
    method = get_installation_method()
    print_info(f"Installation method: {method}")
    
    success = False
    
    if method == "homebrew":
        success = update_via_homebrew()
    elif method == "pip":
        success = update_via_pip()
    elif method == "binary":
        success = update_via_binary(release)
    else:
        print_warning("Could not detect installation method.")
        print_info("Try one of these manually:")
        console.print("  • brew upgrade repr")
        console.print("  • pip install --upgrade repr-cli")
        console.print(f"  • Download from https://github.com/{GITHUB_REPO}/releases/latest")
        return False
    
    if success:
        print_success(f"Updated to v{latest_version}")
        print_info("Restart your terminal or run 'repr -v' to verify")
    
    return success






































