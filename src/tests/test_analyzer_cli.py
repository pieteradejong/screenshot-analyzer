"""Tests for the analyzer CLI."""

import subprocess
import sys
from pathlib import Path


class TestCLI:
    """Tests for command-line interface."""

    def test_help_flag(self):
        """Test that --help works and shows usage."""
        result = subprocess.run(
            [sys.executable, "src/analyzer.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "--backend" in result.stdout
        assert "--limit" in result.stdout

    def test_backend_choices(self):
        """Test that only valid backends are accepted."""
        result = subprocess.run(
            [sys.executable, "src/analyzer.py", "/tmp", "--backend", "invalid"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower()

    def test_dry_run_no_directory_error(self):
        """Test that missing directory gives error."""
        result = subprocess.run(
            [sys.executable, "src/analyzer.py", "/nonexistent/path/12345"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode != 0
        assert (
            "not a directory" in result.stdout.lower()
            or "error" in result.stderr.lower()
        )

    def test_dry_run_mode(self, temp_dir):
        """Test that --dry-run doesn't process anything."""
        result = subprocess.run(
            [sys.executable, "src/analyzer.py", str(temp_dir), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0
        assert "dry run" in result.stdout.lower()

        # Should not create output directory in dry-run
        analysis_dir = temp_dir / "_analysis"
        assert not analysis_dir.exists()


class TestBackendImports:
    """Test that backend modules can be imported."""

    def test_import_base(self):
        """Test base module imports."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from backends.base import AnalysisBackend, get_device

        assert AnalysisBackend is not None
        assert callable(get_device)

    def test_import_ocr_backend(self):
        """Test OCR backend module structure."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from backends.ocr import OCRBackend

        backend = OCRBackend()
        assert hasattr(backend, "analyze")
        assert hasattr(backend, "initialize")

    def test_import_vlm_backend(self):
        """Test VLM backend module structure."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from backends.vlm import VLMBackend, VLM_AVAILABLE

        assert isinstance(VLM_AVAILABLE, bool)
        backend = VLMBackend()
        assert hasattr(backend, "analyze")
        assert hasattr(backend, "initialize")
