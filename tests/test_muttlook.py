"""Basic tests for muttlook."""

from muttlook import main, CONFIG


def test_import():
    """Test that muttlook can be imported."""
    assert main is not None


def test_config():
    """Test that CONFIG has required keys."""
    assert "html_file" in CONFIG
    assert "markdown_file" in CONFIG
    assert "original_msg" in CONFIG
    assert "commands_file" in CONFIG
