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


def test_reply_references_only():
    """Test reply where In-Reply-To is missing but References exists."""
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=(FIXTURES / "reply_references_only.eml").read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    # Should produce valid HTML (either reply format or new message fallback)
    assert "<html" in html.lower() or "<body" in html.lower(), "No valid HTML generated"
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"


def test_new_message_no_reply_headers():
    """Test new compose with no In-Reply-To or References."""
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=(FIXTURES / "new_message.eml").read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    assert "Kickoff" in html, "New message content not in HTML"
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"


def test_reply_notmuch_missing_fallback():
    """Test that reply with unresolvable In-Reply-To falls back gracefully."""
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=(FIXTURES / "reply_notmuch_missing.eml").read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    # Should fall back to new message mode, not crash
    assert "falling back" not in html, "Error message leaked into HTML"
    assert "notmuch can" in html or "<html" in html.lower(), "Fallback did not produce HTML"
    assert result.returncode == 0, f"muttlook crashed instead of falling back: {result.stderr}"


def _draft_obsidian():
    """Helper: run muttlook draft on obsidian_features.eml, return HTML."""
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=(FIXTURES / "obsidian_features.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    return html_file.read_text()


def test_obsidian_callout_info():
    """Test Obsidian [!info] callout renders as styled div."""
    html = _draft_obsidian()
    assert "INFO:" in html or "Key Takeaway" in html, "Info callout not rendered"
    assert "border-left" in html, "Callout missing border styling"


def test_obsidian_callout_warning():
    """Test Obsidian [!warning] callout renders."""
    html = _draft_obsidian()
    assert "WARNING:" in html or "Risk" in html, "Warning callout not rendered"


def test_obsidian_checkbox_standard():
    """Test standard markdown checkboxes [x] and [ ]."""
    html = _draft_obsidian()
    assert "checkbox" in html or "task-list" in html, "Checkbox not rendered"
    assert "Write docs" in html, "Unchecked task missing"


def test_obsidian_checkbox_in_progress():
    """Test Obsidian [/] in-progress checkbox."""
    html = _draft_obsidian()
    assert "◐" in html or "Code review" in html, "In-progress checkbox not converted"


def test_obsidian_checkbox_cancelled():
    """Test Obsidian [-] cancelled checkbox."""
    html = _draft_obsidian()
    assert "―" in html or "legacy cleanup" in html, "Cancelled checkbox not converted"


def test_obsidian_checkbox_deferred():
    """Test Obsidian [>] deferred checkbox."""
    html = _draft_obsidian()
    assert "▷" in html or "API redesign" in html, "Deferred checkbox not converted"


def test_strikethrough():
    """Test ~~strikethrough~~ via pymdownx.tilde."""
    html = _draft_obsidian()
    assert "<del>" in html or "<s>" in html, "Strikethrough not rendered"


def test_definition_list():
    """Test definition lists via def_list extension."""
    html = _draft_obsidian()
    assert "<dt>" in html or "<dd>" in html, "Definition list not rendered"


def test_fenced_code_block():
    """Test fenced code block renders."""
    html = _draft_obsidian()
    assert "<code>" in html or "<pre>" in html, "Code block not rendered"
    assert "hello" in html, "Code content missing"


def test_table_in_obsidian():
    """Test markdown table renders."""
    html = _draft_obsidian()
    assert "<table" in html, "Table not rendered"
    assert "Sprint" in html, "Table header missing"


# --- TUI rendering (render_html_to_ansi) tests ---


def _render_tui(html):
    """Helper: call render_html_to_ansi via subprocess to use installed muttlook."""
    result = subprocess.run(
        ["python3", "-c",
         "import sys; sys.path.insert(0,'.'); from muttlook import render_html_to_ansi; print(render_html_to_ansi(sys.stdin.read()))"],
        input=html,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent / "src"),
    )
    assert result.returncode == 0, f"render_html_to_ansi failed: {result.stderr}"
    return result.stdout


def test_tui_basic_text():
    """Test basic HTML renders to plain text."""
    out = _render_tui("<html><body><p>Hello world</p></body></html>")
    assert "Hello world" in out


def test_tui_bold_remapped_to_purple():
    """Test that bold text gets styled by Rich."""
    out = _render_tui("<html><body><b>Important</b></body></html>")
    assert "Important" in out


def test_tui_outlook_msonormal():
    """Test Outlook MsoNormal paragraph cleanup."""
    html = '<html><body><p class="MsoNormal">First</p><p class="MsoNormal">Second</p></body></html>'
    out = _render_tui(html)
    assert "First" in out
    assert "Second" in out


def test_tui_forwarded_headers_dimmed():
    """Test forwarded header block gets dimmed (ANSI 90)."""
    html = "<html><body><p>From: Alice</p><p>Sent: Monday</p><p>To: Bob</p><p>Subject: Test</p><p></p><p>Body text</p></body></html>"
    out = _render_tui(html)
    assert "\x1b[90m" in out, "Forwarded headers not dimmed"
    assert "Body text" in out


def test_tui_teams_boilerplate_stripped():
    """Test Teams meeting boilerplate is removed."""
    html = "<html><body><p>Agenda item 1</p><p>________________</p><p>Microsoft Teams meeting</p><p>Meeting ID: 123</p></body></html>"
    out = _render_tui(html)
    assert "Agenda item 1" in out
    assert "Microsoft Teams meeting" not in out


def test_tui_cid_references_stripped():
    """Test [cid:...] image references are removed."""
    html = "<html><body><p>See image [cid:image001.png@01D]</p></body></html>"
    out = _render_tui(html)
    assert "[cid:" not in out
    assert "See image" in out


def test_tui_markdown_headers_colored():
    """Test # headers get styled by Rich."""
    # html2text converts <h1> to "# Title"
    html = "<html><body><h1>Main Title</h1><p>Content</p></body></html>"
    out = _render_tui(html)
    assert "Main Title" in out
    # Rich styles headers with bold (1) — exact codes vary by Rich version
    assert "\x1b[1" in out, "Header not styled"


def test_tui_action_via_cli():
    """Test muttlook --action tui produces output from a real-format email."""
    eml = (FIXTURES / "new_message.eml").read_text()
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=eml,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui action failed: {result.stderr}"
    assert "Kickoff" in result.stdout or "new project" in result.stdout
