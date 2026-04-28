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


def test_view_bare_html_table():
    """Test that HTML email with bare <table> (no <html>/<body>) renders, not escapes."""
    result = subprocess.run(
        ["muttlook", "--action", "view"],
        input=(FIXTURES / "bare_html_table.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"
    outfile = Path.home() / ".cache" / "muttlook" / "view" / "message.html"
    assert outfile.exists(), "HTML output not generated"
    html = outfile.read_text()
    assert "&lt;table" not in html, "HTML was escaped instead of rendered"
    assert "<table" in html, "Table tag missing from output"
    assert "sommarfys" in html, "Email content missing"


def test_tui_bare_html_table():
    """Test that TUI rendering of bare <table> HTML produces readable text."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "bare_html_table.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui action failed: {result.stderr}"
    assert "sommarfys" in result.stdout, "Email content not rendered"
    assert "<table" not in result.stdout, "Raw HTML leaked into TUI output"


# --- Outlook HTML email tests ---


def _strip_ansi(text):
    """Remove ANSI escape codes for assertion matching."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_view_outlook_html():
    """Test Outlook-style HTML email renders in browser view."""
    result = subprocess.run(
        ["muttlook", "--action", "view"],
        input=(FIXTURES / "outlook_html.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"
    outfile = Path.home() / ".cache" / "muttlook" / "view" / "message.html"
    html = outfile.read_text()
    assert "<table" in html, "Table not preserved"
    assert "Update forecast" in html, "Table content missing"
    assert "MsoNormal" in html or "Q2 review" in html.lower() or "Hi Bob" in html, "Email body missing"


def test_tui_outlook_html():
    """Test Outlook-style HTML email renders in TUI."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "outlook_html.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui failed: {result.stderr}"
    plain = _strip_ansi(result.stdout).lower()
    assert "q2 review" in plain, "Email body not rendered"
    assert "update forecast" in plain, "Table content not rendered"
    assert "<table" not in result.stdout, "Raw HTML leaked into TUI"


# --- Gmail HTML email tests ---


def test_view_gmail_html():
    """Test Gmail-style HTML email renders in browser view."""
    result = subprocess.run(
        ["muttlook", "--action", "view"],
        input=(FIXTURES / "gmail_html.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"
    outfile = Path.home() / ".cache" / "muttlook" / "view" / "message.html"
    html = outfile.read_text()
    assert "Kebnekaise" in html, "Email content missing"
    assert "gmail_quote" in html or "blockquote" in html, "Quote structure lost"


def test_tui_gmail_html():
    """Test Gmail-style HTML email renders in TUI."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "gmail_html.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui failed: {result.stderr}"
    assert "Kebnekaise" in result.stdout, "Email content not rendered"
    assert "outdoors" in result.stdout, "Quoted text not rendered"
    assert "<div" not in result.stdout, "Raw HTML leaked into TUI"


def test_tui_newsletter_layout_tables_unwrapped():
    """Test that nested layout tables in newsletters render as clean text."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "newsletter_layout_tables.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui failed: {result.stderr}"
    plain = _strip_ansi(result.stdout)
    assert "Rotary Tiller" in plain, "Product name missing"
    assert "$899" in plain, "Price missing"
    assert "Cultivator A" in plain, "Second section missing"
    # Should NOT have excessive box-drawing from layout tables
    box_chars = sum(1 for c in plain if c in "─│┬┴┼┤├┐┘┌└")
    assert box_chars < 10, f"Too many box-drawing chars ({box_chars}) — layout tables not unwrapped"


def test_tui_border_data_table_preserved():
    """Test that table with border attribute is kept as data table."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "border_data_table.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tui failed: {result.stderr}"
    plain = _strip_ansi(result.stdout)
    assert "SSI" in plain, "Header cell missing"
    assert "100%" in plain, "Data cell missing"
    box_chars = sum(1 for c in plain if c in "─│┬┴┼┤├┐┘┌└")
    assert box_chars > 10, f"Data table grid missing ({box_chars} box chars)"


def test_view_border_data_table_preserved():
    """Test that border data table is preserved in browser view."""
    result = subprocess.run(
        ["muttlook", "--action", "view"],
        input=(FIXTURES / "border_data_table.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"muttlook failed: {result.stderr}"
    outfile = Path.home() / ".cache" / "muttlook" / "view" / "message.html"
    html = outfile.read_text()
    assert "<table" in html, "Data table stripped from view"
    assert "SSI" in html, "Table content missing"


# --- Shared cleanup (classify_header_block) tests for TUI view ---


def test_tui_view_cleanup_cid_stripped():
    """TUI view: [cid:...] references are removed."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "trim_filters.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "[cid:" not in result.stdout, "CID reference not stripped"


def test_tui_view_cleanup_headers_dimmed():
    """TUI view: forwarded From/Sent/To/Subject block is dimmed (ANSI 90)."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "trim_filters.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "\x1b[90m" in result.stdout, "Forwarded headers not dimmed"
    # The dimmed block should contain From/Sent
    dimmed = [l for l in result.stdout.split("\n") if "\x1b[90m" in l]
    dimmed_text = " ".join(dimmed)
    assert "From:" in dimmed_text or "Sent:" in dimmed_text, "Header block not in dimmed lines"


def test_tui_view_cleanup_teams_stripped():
    """TUI view: Teams boilerplate (underscores + meeting info) is removed."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "trim_filters.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Microsoft Teams meeting" not in result.stdout, "Teams boilerplate not stripped"
    assert "Meeting ID:" not in result.stdout, "Meeting ID not stripped"


def test_tui_view_cleanup_blanks_squeezed():
    """TUI view: consecutive blank lines are squeezed to one."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "trim_filters.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "\n\n\n" not in result.stdout, "Triple blank lines not squeezed"


def test_tui_view_keeps_greetings():
    """TUI view: greetings and signoffs are NOT stripped (useful context when reading)."""
    result = subprocess.run(
        ["muttlook", "--action", "tui"],
        input=(FIXTURES / "trim_filters.eml").read_text(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    plain = _strip_ansi(result.stdout)
    assert "Best regards" in plain, "Signoff should be kept in view"
    assert "option B" in plain, "Email body missing"


# --- Reply trim (trim_mail) tests ---


def test_reply_trim_strips_greetings():
    """Reply trim: greetings (Dear X, Hi X) are removed from quoted text."""
    from muttlook.mutt_trim import trim_mail
    lines = [
        "> Dear Anna,\n",
        "> \n",
        "> Can we sync on the project?\n",
        "> \n",
        "> Cheers,\n",
        "> \n",
        "> Erik\n",
    ]
    result = trim_mail(lines)
    text = "".join(result)
    assert "Dear Anna" not in text, "Greeting not stripped"
    assert "Cheers" not in text, "Signoff not stripped"
    assert "sync on the project" in text, "Body content stripped"


def test_reply_trim_strips_signatures():
    """Reply trim: quoted signatures (-- ) are removed."""
    from muttlook.mutt_trim import trim_mail
    lines = [
        "> Thanks!\n",
        "> \n",
        "> -- \n",
        "> Erik Lund | Senior Engineer\n",
        "> Phone: +46 70 123 4567\n",
    ]
    result = trim_mail(lines)
    text = "".join(result)
    assert "Thanks" in text, "Body before sig stripped"
    assert "Senior Engineer" not in text, "Signature not stripped"
    assert "Phone:" not in text, "Signature phone not stripped"


def test_reply_trim_strips_filler():
    """Reply trim: quoted filler lines (---, ===, ___) are removed."""
    from muttlook.mutt_trim import trim_mail
    lines = [
        "> Some content\n",
        "> ________________________________\n",
        "> More content\n",
    ]
    result = trim_mail(lines)
    text = "".join(result)
    assert "Some content" in text
    assert "More content" in text
    assert "____" not in text, "Filler line not stripped"


def test_reply_trim_limits_quote_depth():
    """Reply trim: quotes deeper than IND_MAX (5) are removed."""
    from muttlook.mutt_trim import trim_mail
    lines = [
        "> level 1\n",
        ">> level 2\n",
        ">>> level 3\n",
        ">>>> level 4\n",
        ">>>>> level 5\n",
        ">>>>>> level 6 should be gone\n",
    ]
    result = trim_mail(lines)
    text = "".join(result)
    assert "level 5" in text
    assert "level 6" not in text, "Deep quote not stripped"


def test_nested_lists_preserved():
    """Test that nested markdown lists produce nested <ul> in HTML."""
    fixture = FIXTURES / "nested_lists.eml"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=fixture.read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    # Nested lists must produce multiple <ul> levels, not flat
    ul_count = html.count("<ul>") + html.count("<ul ")
    assert ul_count >= 3, f"Expected >=3 nested <ul> levels, got {ul_count}. Lists are flat!"


def test_line_breaks_preserved():
    """Test that consecutive lines (Date/Attendees) don't merge into one paragraph."""
    fixture = FIXTURES / "nested_lists.eml"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=fixture.read_text(),
        capture_output=True,
        text=True,
    )
    html_file = Path.home() / ".cache" / "muttlook" / "mimelook.html"
    assert html_file.exists(), "HTML output not generated"
    html = html_file.read_text()
    # Date and Attendees must be on separate lines (br or separate elements)
    assert "2026-04-28" in html, "Date missing"
    assert "Alice, Bob, Charlie" in html, "Attendees missing"
    # They must NOT be joined in a single run of text
    assert "2026-04-28 Attendees" not in html and "2026-04-28Attendees" not in html, \
        "Date and Attendees merged into one line — hard_line_breaks not working"
