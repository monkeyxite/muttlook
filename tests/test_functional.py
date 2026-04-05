"""Functional tests for muttlook markdown-to-HTML conversion."""

import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_markdown_table_in_html():
    """Test that markdown tables are converted to HTML tables."""
    reply = FIXTURES / "reply_with_markdown.eml"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=reply.read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    assert "<table>" in html or "<table" in html, "Table not converted to HTML"


def test_markdown_headings_in_html():
    """Test that markdown headings are converted."""
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    if html_file.exists():
        html = html_file.read_text()
        assert "<h1>" in html or "<h1" in html, "Heading not converted to HTML"


def test_markdown_bold_in_html():
    """Test that bold text is converted."""
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    if html_file.exists():
        html = html_file.read_text()
        assert "<strong>" in html or "<b>" in html, "Bold not converted to HTML"


def test_mutt_cmd_generated():
    """Test that mutt_cmd file is generated."""
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=(FIXTURES / "reply_with_markdown.eml").read_text(),
        capture_output=True,
        text=True,
    )
    cmd_file = Path.home() / ".cache" / "muttlook" / "mutt_cmd"
    assert cmd_file.exists(), "mutt_cmd not generated"
    cmd = cmd_file.read_text()
    assert "attach-file" in cmd, "mutt_cmd missing attach-file command"
    assert "mimelook.html" in cmd, "mutt_cmd missing HTML file reference"
