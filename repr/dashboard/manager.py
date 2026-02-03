"""
Dashboard version manager.

Handles downloading and updating the Vue dashboard from GitHub releases.
Falls back to bundled dist/ if download unavailable.
"""

import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Configuration
GITHUB_REPO = "everdraft/repr-dashboard"  # Update with actual repo
RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DOWNLOAD_TIMEOUT = 30  # seconds

# Paths
USER_DASHBOARD_DIR = Path.home() / ".repr" / "dashboard"
BUNDLED_DASHBOARD_DIR = Path(__file__).parent / "dist"
VERSION_FILE = "version.json"


def get_user_dashboard_path() -> Path:
    """Get path to user-installed dashboard, or None if not installed."""
    version_file = USER_DASHBOARD_DIR / VERSION_FILE
    index_file = USER_DASHBOARD_DIR / "index.html"

    if version_file.exists() and index_file.exists():
        return USER_DASHBOARD_DIR
    return None


def get_bundled_dashboard_path() -> Path:
    """Get path to bundled dashboard."""
    if (BUNDLED_DASHBOARD_DIR / "index.html").exists():
        return BUNDLED_DASHBOARD_DIR
    return None


def get_dashboard_path() -> Path:
    """
    Get the best available dashboard path.

    Priority:
    1. User-installed dashboard (~/.repr/dashboard/) if exists
    2. Bundled dashboard (repr/dashboard/dist/) as fallback

    Returns None if neither exists.
    """
    user_path = get_user_dashboard_path()
    if user_path:
        return user_path

    return get_bundled_dashboard_path()


def get_installed_version() -> str | None:
    """Get version of user-installed dashboard."""
    version_file = USER_DASHBOARD_DIR / VERSION_FILE
    if not version_file.exists():
        return None

    try:
        data = json.loads(version_file.read_text())
        return data.get("version")
    except Exception:
        return None


def get_bundled_version() -> str | None:
    """Get version of bundled dashboard."""
    version_file = BUNDLED_DASHBOARD_DIR / VERSION_FILE
    if not version_file.exists():
        return None

    try:
        data = json.loads(version_file.read_text())
        return data.get("version")
    except Exception:
        return None


def get_latest_release_info() -> dict | None:
    """
    Fetch latest release info from GitHub.

    Returns dict with 'version' and 'download_url' or None if unavailable.
    """
    try:
        req = Request(
            RELEASE_URL,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "repr-cli"}
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        version = data.get("tag_name", "").lstrip("v")

        # Find the tarball asset
        download_url = None
        for asset in data.get("assets", []):
            if asset["name"].endswith(".tar.gz"):
                download_url = asset["browser_download_url"]
                break

        # Fallback to source tarball if no asset
        if not download_url:
            download_url = data.get("tarball_url")

        if version and download_url:
            return {"version": version, "download_url": download_url}
    except (URLError, json.JSONDecodeError, KeyError):
        pass

    return None


def download_and_install(download_url: str, version: str) -> bool:
    """
    Download and install dashboard from URL.

    Returns True on success, False on failure.
    """
    try:
        # Create temp directory for download
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tarball_path = tmpdir_path / "dashboard.tar.gz"

            # Download
            print(f"  Downloading dashboard v{version}...")
            req = Request(download_url, headers={"User-Agent": "repr-cli"})
            with urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                tarball_path.write_bytes(resp.read())

            # Extract
            print("  Extracting...")
            extract_dir = tmpdir_path / "extracted"
            extract_dir.mkdir()

            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Find the dist directory (might be nested)
            dist_dir = None
            for item in extract_dir.rglob("index.html"):
                dist_dir = item.parent
                break

            if not dist_dir:
                print("  Error: Could not find index.html in archive")
                return False

            # Install to user directory
            USER_DASHBOARD_DIR.parent.mkdir(parents=True, exist_ok=True)

            if USER_DASHBOARD_DIR.exists():
                shutil.rmtree(USER_DASHBOARD_DIR)

            shutil.copytree(dist_dir, USER_DASHBOARD_DIR)

            # Write version file
            version_data = {"version": version}
            (USER_DASHBOARD_DIR / VERSION_FILE).write_text(json.dumps(version_data))

            print(f"  Dashboard v{version} installed to {USER_DASHBOARD_DIR}")
            return True

    except Exception as e:
        print(f"  Error installing dashboard: {e}")
        return False


def check_for_updates(quiet: bool = False) -> bool:
    """
    Check for dashboard updates and install if available.

    Returns True if an update was installed.
    """
    installed = get_installed_version()

    release = get_latest_release_info()
    if not release:
        if not quiet:
            print("  Could not check for dashboard updates (offline?)")
        return False

    latest = release["version"]

    # Compare versions (simple string comparison, assumes semver)
    if installed and installed >= latest:
        if not quiet:
            print(f"  Dashboard is up to date (v{installed})")
        return False

    if not quiet:
        if installed:
            print(f"  New dashboard version available: v{installed} -> v{latest}")
        else:
            print(f"  Installing dashboard v{latest}...")

    return download_and_install(release["download_url"], latest)


def ensure_dashboard() -> Path:
    """
    Ensure dashboard is available, downloading if needed.

    Returns path to dashboard directory.
    Raises RuntimeError if no dashboard available.
    """
    # First, try user-installed
    user_path = get_user_dashboard_path()
    if user_path:
        return user_path

    # Try to download latest
    release = get_latest_release_info()
    if release:
        if download_and_install(release["download_url"], release["version"]):
            return USER_DASHBOARD_DIR

    # Fall back to bundled
    bundled_path = get_bundled_dashboard_path()
    if bundled_path:
        return bundled_path

    raise RuntimeError(
        "No dashboard available. Bundled dashboard not found and could not download from GitHub."
    )
