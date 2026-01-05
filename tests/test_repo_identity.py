"""
Test repo identity (stable UUID in .git/repr/repo_id).

Verifies Gap #2: Repo identity should use stable UUID for cross-device sync.
Status: ✅ IMPLEMENTED
"""

import pytest
import uuid
from pathlib import Path


class TestRepoIdentity:
    """Test stable repo ID generation and usage."""

    def test_repo_id_generated_on_hook_install(self, mock_git_repo):
        """Installing hook should generate repo ID if not exists."""
        from repr.hooks import install_hook, get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)

        # Initially no repo ID
        repo_id_path = get_repo_id_path(repo_path)
        assert not repo_id_path.exists()

        # Install hook
        result = install_hook(repo_path)
        assert result["success"]

        # Repo ID should now exist
        assert repo_id_path.exists()

        # Should be valid UUID
        repo_id = repo_id_path.read_text().strip()
        try:
            uuid.UUID(repo_id)
        except ValueError:
            pytest.fail(f"Repo ID '{repo_id}' is not a valid UUID")

    def test_repo_id_stable_across_hook_reinstalls(self, mock_git_repo):
        """Repo ID should not change when reinstalling hook."""
        from repr.hooks import install_hook, get_repo_id, get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)

        # First install
        install_hook(repo_path)
        first_id = get_repo_id(repo_path)

        # Remove hook (but not repo_id file)
        hook_path = repo_path / ".git" / "hooks" / "post-commit"
        hook_path.unlink()

        # Second install
        install_hook(repo_path)
        second_id = get_repo_id(repo_path)

        # ID should be the same
        assert first_id == second_id

    def test_get_repo_id_returns_existing_id(self, mock_git_repo):
        """get_repo_id should return existing ID if present."""
        from repr.hooks import get_repo_id, get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)

        # Manually create repo ID
        repo_id_path = get_repo_id_path(repo_path)
        repo_id_path.parent.mkdir(parents=True, exist_ok=True)
        expected_id = str(uuid.uuid4())
        repo_id_path.write_text(expected_id)

        # get_repo_id should return it
        actual_id = get_repo_id(repo_path)
        assert actual_id == expected_id

    def test_get_repo_id_returns_none_if_not_exists(self, mock_git_repo):
        """get_repo_id should return None if repo ID doesn't exist."""
        from repr.hooks import get_repo_id

        repo_path = Path(mock_git_repo.working_dir)

        # No repo ID yet
        repo_id = get_repo_id(repo_path)
        assert repo_id is None

    def test_ensure_repo_id_creates_if_missing(self, mock_git_repo):
        """ensure_repo_id should create ID if it doesn't exist."""
        from repr.hooks import ensure_repo_id, get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)

        # Ensure repo ID
        repo_id = ensure_repo_id(repo_path)

        # Should be valid UUID
        try:
            uuid.UUID(repo_id)
        except ValueError:
            pytest.fail(f"Repo ID '{repo_id}' is not a valid UUID")

        # Should be saved to file
        repo_id_path = get_repo_id_path(repo_path)
        assert repo_id_path.exists()
        assert repo_id_path.read_text().strip() == repo_id

    def test_ensure_repo_id_returns_existing_if_present(self, mock_git_repo):
        """ensure_repo_id should return existing ID without changing it."""
        from repr.hooks import ensure_repo_id, get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)

        # Create existing ID
        repo_id_path = get_repo_id_path(repo_path)
        repo_id_path.parent.mkdir(parents=True, exist_ok=True)
        existing_id = str(uuid.uuid4())
        repo_id_path.write_text(existing_id)

        # ensure_repo_id should return same ID
        repo_id = ensure_repo_id(repo_path)
        assert repo_id == existing_id

    def test_repo_id_path_location(self, mock_git_repo):
        """Repo ID should be stored in .git/repr/repo_id."""
        from repr.hooks import get_repo_id_path

        repo_path = Path(mock_git_repo.working_dir)
        repo_id_path = get_repo_id_path(repo_path)

        expected_path = repo_path / ".git" / "repr" / "repo_id"
        assert repo_id_path == expected_path


class TestRepoIdentityPrivacy:
    """Test privacy properties of repo ID."""

    def test_repo_id_is_random_uuid_not_path_based(self, mock_git_repo):
        """Repo ID should be random UUID, not derived from path."""
        from repr.hooks import ensure_repo_id

        repo_path = Path(mock_git_repo.working_dir)

        # Generate ID
        repo_id = ensure_repo_id(repo_path)

        # Should be valid UUID (random)
        uuid_obj = uuid.UUID(repo_id)

        # Should be version 4 (random)
        assert uuid_obj.version == 4

        # Should not contain path info
        path_str = str(repo_path)
        assert path_str not in repo_id
        assert repo_path.name not in repo_id

    def test_repo_id_not_leaked_in_config(self, mock_git_repo, mock_config):
        """Repo ID should stay in .git/repr/, not in ~/.repr/config.json."""
        from repr.hooks import ensure_repo_id
        from repr.config import load_config

        repo_path = Path(mock_git_repo.working_dir)

        # Generate ID
        repo_id = ensure_repo_id(repo_path)

        # Config should not contain repo ID
        config = load_config()
        config_str = str(config)
        assert repo_id not in config_str


class TestRepoIdentityCrossDevice:
    """Test repo ID behavior across devices."""

    def test_repo_id_stored_in_git_dir_travels_with_repo(self, temp_dir, mock_git_repo):
        """Repo ID is in .git/ so it travels when repo is cloned."""
        from repr.hooks import ensure_repo_id, get_repo_id

        repo_path = Path(mock_git_repo.working_dir)

        # Generate ID
        original_id = ensure_repo_id(repo_path)

        # Simulate clone (copy .git directory)
        clone_path = temp_dir / "clone"
        import shutil
        shutil.copytree(repo_path, clone_path)

        # Cloned repo should have same ID
        cloned_id = get_repo_id(clone_path)
        assert cloned_id == original_id

    def test_different_repos_get_different_ids(self, temp_dir):
        """Different repos should get different UUIDs."""
        from git import Repo
        from repr.hooks import ensure_repo_id

        # Create two repos
        repo1_path = temp_dir / "repo1"
        repo1_path.mkdir()
        Repo.init(repo1_path)

        repo2_path = temp_dir / "repo2"
        repo2_path.mkdir()
        Repo.init(repo2_path)

        # Generate IDs
        id1 = ensure_repo_id(repo1_path)
        id2 = ensure_repo_id(repo2_path)

        # Should be different
        assert id1 != id2
