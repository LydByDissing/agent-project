# [origin ref=llm-dsl-8wy req=REQ-DESIGN-CHAT-003 c4=sdd_skills/docs_skill]
#   [intent]Test that bootstrap_sphinx.py creates design_log/index.rst with toctree directive and root index.rst contains Design Log toctree section[/intent]
# [/origin]

"""Test bootstrap_sphinx.py design log structure creation.

Tests verify that:
1. bootstrap_sphinx.py creates docs/source/design_log/index.rst with a toctree directive
2. root index.rst contains a Design Log toctree section
"""

import subprocess
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.docs.scripts.bootstrap_sphinx import main


class TestBootstrapDesignLogStructure:
    """Test suite for bootstrap_sphinx.py design log structure."""

    def setup_method(self):
        """Create a temporary directory for each test."""
        self.test_dir = tempfile.mkdtemp(prefix="test_bootstrap_")
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create a minimal pyproject.toml for project name detection
        Path("pyproject.toml").write_text('name = "test-project"\n')

    def teardown_method(self):
        """Clean up temporary directory and restore original working directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bootstrap_creates_design_log_index_file_exists(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main()
           Assert: docs/source/design_log/index.rst file is created
        """
        # Arrange
        assert not Path("docs/source/design_log/index.rst").exists()

        # Act
        main()

        # Assert
        assert Path("docs/source/design_log/index.rst").exists()
        assert Path("docs/source/design_log/index.rst").is_file()

    def test_design_log_index_contains_toctree_directive(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read design_log/index.rst
           Assert: File contains '.. toctree::' directive
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/design_log/index.rst").read_text()

        # Assert
        assert ".. toctree::" in content

    def test_design_log_index_toctree_has_maxdepth(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read design_log/index.rst
           Assert: toctree directive includes :maxdepth: option
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/design_log/index.rst").read_text()

        # Assert
        assert ":maxdepth:" in content
        # Verify it's within the design_log index, not just anywhere
        toctree_section = content[content.index(".. toctree::"):]
        assert ":maxdepth:" in toctree_section

    def test_design_log_index_has_heading(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read design_log/index.rst
           Assert: File contains 'Design Log' heading
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/design_log/index.rst").read_text()

        # Assert
        assert "Design Log" in content
        assert "==========" in content

    def test_root_index_contains_design_log_section(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read root index.rst
           Assert: Root index.rst contains 'Design Log' toctree section
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/index.rst").read_text()

        # Assert
        assert "Design Log" in content

    def test_root_index_design_log_section_has_caption(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read root index.rst
           Assert: Design Log toctree has :caption: Design Log
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/index.rst").read_text()

        # Assert
        assert ":caption: Design Log" in content

    def test_root_index_includes_design_log_reference(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read root index.rst
           Assert: Root index references design_log/index in toctree
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/index.rst").read_text()

        # Assert
        # Find the Design Log section in the toctree
        design_log_caption_idx = content.find(":caption: Design Log")
        assert design_log_caption_idx != -1, "Design Log caption not found"

        # Look for design_log/index reference after the caption
        section_after_caption = content[design_log_caption_idx:]
        next_caption_idx = section_after_caption.find(":caption:", 1)
        if next_caption_idx == -1:
            section_text = section_after_caption
        else:
            section_text = section_after_caption[:next_caption_idx]

        assert "design_log/index" in section_text

    def test_design_log_idempotent_content_unchanged(self):
        """Arrange: Bootstrap once
           Act: Bootstrap again
           Assert: design_log/index.rst content is identical after second run
        """
        main()
        first_content = Path("docs/source/design_log/index.rst").read_text()

        main()

        assert Path("docs/source/design_log/index.rst").read_text() == first_content

    def test_design_log_idempotent_file_not_recreated(self):
        """Arrange: Bootstrap once, record mtime
           Act: Bootstrap again
           Assert: design_log/index.rst mtime is unchanged (write_if_missing skipped it)
        """
        main()
        first_mtime = Path("docs/source/design_log/index.rst").stat().st_mtime

        main()

        assert Path("docs/source/design_log/index.rst").stat().st_mtime == first_mtime

    def test_design_log_index_structure_matches_template(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read design_log/index.rst
           Assert: File structure matches expected template
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/design_log/index.rst").read_text()

        # Assert
        # Should have Design Log heading
        assert "Design Log" in content
        # Should have description about design decisions
        assert "design decisions" in content.lower() or "decisions made" in content.lower()
        # Should have toctree for entries
        assert ".. toctree::" in content
        # Should document the naming convention
        assert "FEAT-" in content or "revision" in content.lower()

    def test_root_and_design_log_both_created(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main()
           Assert: Both root index.rst and design_log/index.rst are created
                   with expected structural content
        """
        main()

        root_content = Path("docs/source/index.rst").read_text()
        design_log_content = Path("docs/source/design_log/index.rst").read_text()

        assert ".. toctree::" in root_content
        assert ":caption: Design Log" in root_content
        assert ".. toctree::" in design_log_content
        assert "Design Log" in design_log_content

    def test_design_log_toctree_section_placement(self):
        """Arrange: Fresh project directory
           Act: Run bootstrap_sphinx.main() and read root index.rst
           Assert: Design Log toctree is properly placed in root index structure
        """
        # Arrange

        # Act
        main()
        content = Path("docs/source/index.rst").read_text()

        # Assert
        # Check that Design Log section comes after Architecture and Specifications
        arch_idx = content.find(":caption: Architecture")
        specs_idx = content.find(":caption: Specifications")
        design_idx = content.find(":caption: Design Log")

        assert arch_idx != -1, "Architecture section not found"
        assert specs_idx != -1, "Specifications section not found"
        assert design_idx != -1, "Design Log section not found"

        # Design Log should come after both Architecture and Specifications
        assert arch_idx < specs_idx < design_idx


def test_design_log_index_entry_added_after_append():
    """Arrange: Bootstrap and write design_log/index.rst, then simulate a new
                design log entry being appended to the toctree
       Act: Append an entry to design_log/index.rst
       Assert: The entry appears in the toctree and the file is valid RST
    """
    test_dir = tempfile.mkdtemp(prefix="test_bootstrap_entry_")
    original_cwd = os.getcwd()
    try:
        os.chdir(test_dir)
        Path("pyproject.toml").write_text('name = "entry-test"\n')
        main()

        design_log_index = Path("docs/source/design_log/index.rst")
        original = design_log_index.read_text()

        # Simulate Docs Skill appending a new entry (REQ-DESIGN-CHAT-003 acceptance)
        updated = original.rstrip() + "\n   FEAT-AUTH-a1b2c3d4\n"
        design_log_index.write_text(updated)

        content = design_log_index.read_text()
        assert "FEAT-AUTH-a1b2c3d4" in content
        assert ".. toctree::" in content

    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_bootstrap_sphinx_design_log_acceptance():
    """Integration test: Verify the acceptance criterion is met.

    Arrange: Create a test project environment
    Act: Run bootstrap_sphinx.main()
    Assert: design_log/index.rst exists with toctree, and root index contains Design Log section
    """
    # Arrange
    test_dir = tempfile.mkdtemp(prefix="test_bootstrap_integration_")
    original_cwd = os.getcwd()
    try:
        os.chdir(test_dir)
        Path("pyproject.toml").write_text('name = "integration-test"\n')

        # Act
        main()

        # Assert
        design_log_path = Path("docs/source/design_log/index.rst")
        root_index_path = Path("docs/source/index.rst")

        assert design_log_path.exists(), "design_log/index.rst not created"

        design_log_content = design_log_path.read_text()
        assert ".. toctree::" in design_log_content, "design_log/index.rst missing toctree directive"

        root_index_content = root_index_path.read_text()
        assert ":caption: Design Log" in root_index_content, "root index.rst missing Design Log caption"
        assert "design_log/index" in root_index_content, "root index.rst missing design_log/index reference"

    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)
