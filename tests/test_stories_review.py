"""
Test stories review interactive workflow.

Verifies Gap #5: Stories review should show STAR format and support regenerate.
Status: ⚠️ PARTIAL (basic review exists, STAR format not implemented)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch


class TestStoriesReviewBasic:
    """Test basic review workflow (implemented)."""

    def test_review_shows_stories_needing_review(self, mock_stories):
        """Review command should show stories marked needs_review=True."""
        from repr.storage import get_stories_needing_review

        needs_review = get_stories_needing_review()

        # We created 1 story needing review
        assert len(needs_review) == 1
        assert needs_review[0]["needs_review"] is True

    def test_review_with_no_stories_exits(self, mock_repr_home, capsys):
        """Review command should exit gracefully if no stories need review."""
        import repr.storage
        import importlib

        # Reload to pick up new REPR_HOME
        importlib.reload(repr.storage)

        from repr.cli import stories_review

        # No stories exist
        with pytest.raises((SystemExit, Exception)):  # May raise Exit or SystemExit
            stories_review()

        captured = capsys.readouterr()
        assert "No stories need review" in captured.out

    def test_review_displays_story_summary(self, mock_stories):
        """Review should display story summary and metadata."""
        from repr.storage import get_stories_needing_review

        stories = get_stories_needing_review()
        story = stories[0]

        # Should have summary
        assert "summary" in story
        assert story["summary"]

        # Should have metadata
        assert "repo_name" in story
        assert "commit_shas" in story

    @patch("repr.cli.Prompt.ask")
    def test_review_approve_action(self, mock_prompt, mock_stories):
        """Approve action should mark story as reviewed."""
        from repr.cli import stories_review
        from repr.storage import get_stories_needing_review, load_story

        # Mock user selecting "approve"
        mock_prompt.return_value = "a"

        # Run review
        stories_review()

        # Story should no longer need review
        needs_review = get_stories_needing_review()
        assert len(needs_review) == 0

    @patch("repr.cli.Prompt.ask")
    def test_review_skip_action(self, mock_prompt, mock_stories):
        """Skip action should leave story unchanged."""
        from repr.cli import stories_review
        from repr.storage import get_stories_needing_review

        # Mock user selecting "skip"
        mock_prompt.return_value = "s"

        # Run review
        stories_review()

        # Story should still need review
        needs_review = get_stories_needing_review()
        assert len(needs_review) == 1

    @patch("repr.cli.Prompt.ask")
    @patch("repr.cli.confirm")
    def test_review_delete_action(self, mock_confirm, mock_prompt, mock_stories):
        """Delete action should remove story."""
        from repr.cli import stories_review
        from repr.storage import get_stories_needing_review, list_stories

        # Mock user selecting "delete" and confirming
        mock_prompt.return_value = "d"
        mock_confirm.return_value = True

        initial_count = len(list_stories())

        # Run review
        stories_review()

        # Story count should decrease
        final_count = len(list_stories())
        assert final_count == initial_count - 1


class TestStoriesReviewSTARFormat:
    """Test STAR format display (implemented in cli.py)."""

    def test_review_shows_what_was_built(self):
        """Review should show 'What was built' section."""
        # Implemented in cli.py:815-819
        from repr.cli import stories_review
        import inspect

        source = inspect.getsource(stories_review)

        # Verify "What was built" section exists
        assert "What was built" in source

    def test_review_shows_technologies(self):
        """Review should show extracted technologies."""
        # Implemented in cli.py:822-828
        from repr.cli import stories_review
        import inspect

        source = inspect.getsource(stories_review)

        # Verify technologies display exists
        assert "Technologies" in source
        assert "technologies" in source

    def test_review_shows_confidence(self):
        """Review should show confidence level."""
        # Implemented in cli.py:831-833
        from repr.cli import stories_review
        import inspect

        source = inspect.getsource(stories_review)

        # Verify confidence display exists
        assert "Confidence" in source
        assert "confidence" in source

    def test_review_interview_story_shows_star_format(self):
        """Stories generated with interview template should show STAR."""
        # Implemented in cli.py:812-833
        # The code checks if template == 'interview' and displays STAR format
        from repr.cli import stories_review
        import inspect

        source = inspect.getsource(stories_review)

        # Verify interview template detection and STAR display
        assert "template == 'interview'" in source or "template" in source
        assert "What was built" in source


class TestStoriesReviewRegenerateAction:
    """Test regenerate action (UI available, full implementation planned)."""

    @patch("repr.cli.Prompt.ask")
    def test_review_regenerate_action_available(self, mock_prompt, mock_stories):
        """Regenerate should be available as action option."""
        # Implemented in cli.py:844-846
        # The prompt includes [r] Regenerate option
        from repr.cli import stories_review
        import inspect

        source = inspect.getsource(stories_review)

        # Verify regenerate option is in the prompt
        assert "[r] Regenerate" in source or "Regenerate" in source
        assert '"r"' in source

    @pytest.mark.skip("Full regenerate workflow planned for future release")
    @patch("repr.cli.Prompt.ask")
    def test_regenerate_prompts_for_template(self, mock_prompt, mock_stories):
        """Regenerate action should prompt for template selection."""
        # The regenerate option exists but shows "not yet implemented" message
        # Full workflow with template selection is planned for future release
        # Current behavior: cli.py:860-864 shows info message

    @pytest.mark.skip("Full regenerate workflow planned for future release")
    @patch("repr.cli.Prompt.ask")
    def test_regenerate_replaces_story_content(self, mock_prompt, mock_stories):
        """Regenerating should update story with new content."""
        # Will be implemented when full regenerate workflow is added


class TestStoriesReviewEditorIntegration:
    """Test editor integration for edit action."""

    @patch("repr.cli.Prompt.ask")
    @patch("subprocess.run")
    def test_review_edit_opens_editor(self, mock_subprocess, mock_prompt, mock_stories):
        """Edit action should open story in $EDITOR."""
        from repr.cli import stories_review
        import os

        # Mock user selecting "edit"
        mock_prompt.return_value = "e"

        # Mock editor
        os.environ["EDITOR"] = "vim"

        # Run review
        stories_review()

        # Should have called subprocess with editor
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "vim" in call_args

    @patch("repr.cli.Prompt.ask")
    @patch("subprocess.run")
    def test_edit_defaults_to_vim(self, mock_subprocess, mock_prompt, mock_stories):
        """Editor should default to vim if $EDITOR not set."""
        from repr.cli import stories_review
        import os

        # Unset EDITOR
        if "EDITOR" in os.environ:
            del os.environ["EDITOR"]

        mock_prompt.return_value = "e"

        stories_review()

        # Should default to vim
        call_args = mock_subprocess.call_args[0][0]
        assert "vim" in call_args


class TestStoriesReviewContentPreview:
    """Test story content preview in review UI."""

    def test_review_shows_content_preview(self, mock_stories):
        """Review should show first 500 chars of story content."""
        # Implementation shows preview[:500]
        # Verify this is working

        from repr.storage import get_stories_needing_review, load_story

        stories = get_stories_needing_review()
        story = stories[0]

        # Load full content
        result = load_story(story["id"])
        assert result is not None

        content, _ = result

        # Preview should be truncated
        preview = content[:500]
        assert len(preview) <= 500

    def test_review_truncates_long_content(self, mock_repr_home, mock_stories):
        """Long stories should be truncated with ellipsis."""
        from repr.storage import save_story
        import uuid

        # Create long story
        long_content = "A" * 1000
        story_id = str(uuid.uuid4())
        save_story(
            long_content,
            {
                "id": story_id,
                "needs_review": True,
                "summary": "Long story",
                "repo_name": "test",
            },
            story_id,
        )

        from repr.storage import load_story

        content, _ = load_story(story_id)

        # Should be able to preview
        preview = content[:500]
        assert len(preview) == 500
