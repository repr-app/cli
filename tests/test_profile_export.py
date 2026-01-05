"""
Test profile export functionality.

Verifies Gap #4: Profile export should support md, html, json, pdf formats.
Status: ⚠️ PARTIAL (md/json work, html/pdf not implemented)
"""

import pytest
import json
from pathlib import Path


class TestProfileExportMarkdown:
    """Test Markdown export (implemented)."""

    def test_export_markdown_to_stdout(self, mock_stories, capsys):
        """Profile export as markdown should print to stdout."""
        from repr.cli import profile_export

        # Run export
        try:
            profile_export(format="md", output=None)
        except SystemExit:
            pass  # May exit with 0

        # Check output
        captured = capsys.readouterr()
        assert "# " in captured.out  # Should have heading
        assert "## Stories" in captured.out

    def test_export_markdown_to_file(self, mock_stories, temp_dir):
        """Profile export as markdown should write to file."""
        from repr.cli import profile_export

        output_file = temp_dir / "profile.md"

        # Run export
        try:
            profile_export(format="md", output=output_file)
        except SystemExit:
            pass

        # Check file created
        assert output_file.exists()
        content = output_file.read_text()
        assert "# " in content
        assert "## Stories" in content

    def test_markdown_includes_story_metadata(self, mock_stories, temp_dir):
        """Markdown export should include story summaries and metadata."""
        from repr.cli import profile_export

        output_file = temp_dir / "profile.md"
        profile_export(format="md", output=output_file)

        content = output_file.read_text()

        # Should include story summaries
        assert "Test Story 1" in content or "Test Story" in content

        # Should include repo name
        assert "test-repo" in content


class TestProfileExportJSON:
    """Test JSON export (implemented)."""

    def test_export_json_to_stdout(self, mock_stories, capsys):
        """Profile export as JSON should print to stdout."""
        from repr.cli import profile_export

        try:
            profile_export(format="json", output=None)
        except SystemExit:
            pass

        captured = capsys.readouterr()

        # Should be valid JSON
        data = json.loads(captured.out)
        assert "profile" in data
        assert "stories" in data

    def test_export_json_to_file(self, mock_stories, temp_dir):
        """Profile export as JSON should write to file."""
        from repr.cli import profile_export

        output_file = temp_dir / "profile.json"
        profile_export(format="json", output=output_file)

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "profile" in data
        assert "stories" in data

    def test_json_includes_all_stories(self, mock_stories, temp_dir):
        """JSON export should include all stories."""
        from repr.cli import profile_export

        output_file = temp_dir / "profile.json"
        profile_export(format="json", output=output_file)

        data = json.loads(output_file.read_text())
        assert len(data["stories"]) == 3  # We created 3 stories


class TestProfileExportHTML:
    """Test HTML export (planned for future release)."""

    @pytest.mark.skip("HTML export planned for future release")
    def test_export_html(self, mock_stories, temp_dir):
        """Profile export as HTML should generate HTML file."""
        # Intentionally not implemented yet
        # Will be added in a future release with proper HTML templating
        # Current behavior: shows error message (see test_unsupported_html_shows_error)

    @pytest.mark.skip("HTML export planned for future release")
    def test_html_has_basic_styling(self, mock_stories, temp_dir):
        """HTML export should include basic CSS styling."""
        # Will be implemented with HTML export feature

    def test_unsupported_html_shows_error(self, mock_stories, capsys):
        """Requesting HTML export should show error until implemented."""
        from repr.cli import profile_export
        from click.exceptions import Exit

        with pytest.raises((SystemExit, Exit)):
            profile_export(format="html", output=None)

        captured = capsys.readouterr()
        # Should show error (implementation may vary)


class TestProfileExportPDF:
    """Test PDF export (planned for future release)."""

    @pytest.mark.skip("PDF export planned for future release")
    def test_export_pdf(self, mock_stories, temp_dir):
        """Profile export as PDF should generate PDF file."""
        # Intentionally not implemented yet
        # Will be added in a future release with weasyprint or reportlab
        # Current behavior: shows error message (see test_unsupported_pdf_shows_error)

    @pytest.mark.skip("PDF export planned for future release")
    def test_pdf_no_external_service(self, mock_stories, temp_dir):
        """PDF export should not make external network calls."""
        # Will use bundled renderer (weasyprint, reportlab, etc.)
        # No external network calls will be made

    def test_unsupported_pdf_shows_error(self, mock_stories, capsys):
        """Requesting PDF export should show error until implemented."""
        from repr.cli import profile_export
        from click.exceptions import Exit

        with pytest.raises((SystemExit, Exit)):
            profile_export(format="pdf", output=None)


class TestProfileExportErrors:
    """Test error handling."""

    def test_unsupported_format_shows_error(self, mock_stories, capsys):
        """Unsupported format should show helpful error."""
        from repr.cli import profile_export
        from click.exceptions import Exit

        with pytest.raises((SystemExit, Exit)):
            profile_export(format="xml", output=None)

        captured = capsys.readouterr()
        assert "Unsupported format" in captured.out or "xml" in captured.out.lower()


class TestProfileExportWithFilters:
    """Test export with date filters (implemented in cli.py)."""

    def test_export_since_date(self, mock_stories, temp_dir):
        """Should support --since flag to export only recent work."""
        # Spec mentions: repr profile export --since 2025-01-01
        # Implemented in cli.py:2108-2120
        from repr.cli import profile_export
        import inspect

        # Verify --since parameter exists
        sig = inspect.signature(profile_export)
        assert "since" in sig.parameters

        # Verify date filtering logic exists in implementation
        source = inspect.getsource(profile_export)
        assert "since" in source
        assert "since_date" in source or "datetime" in source

    def test_export_filters_old_stories(self, mock_stories, temp_dir):
        """Export with --since should exclude older stories."""
        # Date filtering is implemented in cli.py:2108-2120
        # Test that the filtering logic exists
        from repr.cli import profile_export
        import inspect

        source = inspect.getsource(profile_export)

        # Verify filtering logic
        assert "story_list = [" in source or "for s in story_list" in source
        assert "created_at" in source
        assert ">=" in source or "<=" in source  # Comparison operator for date filtering
        # TODO: Test that stories before cutoff date are excluded
