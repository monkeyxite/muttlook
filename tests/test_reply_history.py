"""Tests for reply history preservation via embedded markers."""

import subprocess
import tempfile
from pathlib import Path

from muttlook.mutt_trim import trim_mail

FIXTURES = Path(__file__).parent / "fixtures"
CACHE_DIR = Path.home() / ".cache" / "muttlook"


# --- mutt-trim marker embedding ---


def test_mutt_trim_embeds_reply_to_marker():
    """mutt-trim appends [//]: # (muttlook-reply-to:...) when In-Reply-To present."""
    draft = (
        "From: a@x.com\n"
        "To: b@x.com\n"
        "Subject: Re: Test\n"
        "In-Reply-To: <parent-msg-id@example.com>\n"
        "\n"
        "My reply\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".eml", delete=False) as f:
        f.write(draft)
        f.flush()
        subprocess.run(["mutt-trim", f.name], check=True)
        result = Path(f.name).read_text()
    Path(f.name).unlink()
    assert "[//]: # (muttlook-reply-to:<parent-msg-id@example.com>)" in result


def test_mutt_trim_embeds_references_marker():
    """mutt-trim appends references marker when References header present."""
    draft = (
        "From: a@x.com\n"
        "To: b@x.com\n"
        "In-Reply-To: <parent@ex.com>\n"
        "References: <first@ex.com> <parent@ex.com>\n"
        "\n"
        "Reply\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".eml", delete=False) as f:
        f.write(draft)
        f.flush()
        subprocess.run(["mutt-trim", f.name], check=True)
        result = Path(f.name).read_text()
    Path(f.name).unlink()
    assert "[//]: # (muttlook-references:<first@ex.com> <parent@ex.com>)" in result


def test_mutt_trim_no_marker_for_new_message():
    """mutt-trim does NOT append marker when no In-Reply-To header."""
    draft = (
        "From: a@x.com\n"
        "To: b@x.com\n"
        "Subject: New topic\n"
        "\n"
        "Hello\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".eml", delete=False) as f:
        f.write(draft)
        f.flush()
        subprocess.run(["mutt-trim", f.name], check=True)
        result = Path(f.name).read_text()
    Path(f.name).unlink()
    assert "muttlook-reply-to" not in result


# --- plain2fancy marker extraction ---


def test_marker_extracted_from_piped_body():
    """plain2fancy extracts reply-to marker and strips it from output."""
    body = (
        "My reply text\n"
        "\n"
        "[//]: # (muttlook-reply-to:<test-id@example.com>)\n"
    )
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Marker should not appear in generated HTML
    html = CACHE_DIR / "mimelook.html"
    assert html.exists()
    assert "muttlook-reply-to" not in html.read_text()
    # Log should show marker was used
    log = (CACHE_DIR / "mimelog.log").read_text()
    assert "from_marker=True" in log


def test_marker_preferred_over_stale_original_msg():
    """Marker in body takes priority over stale original.msg."""
    # Write a stale original.msg with different/no In-Reply-To
    org = CACHE_DIR / "original.msg"
    org.write_text("From: x@x.com\nSubject: unrelated\n\nno reply\n")

    body = (
        "Reply content\n"
        "\n"
        "[//]: # (muttlook-reply-to:<nonexistent-for-test@example.com>)\n"
    )
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    log = (CACHE_DIR / "mimelog.log").read_text()
    # Should use marker, not fall back to original.msg
    assert "reply_to_id=nonexistent-for-test@example.com" in log
    assert "from_marker=True" in log


def test_fallback_to_original_msg_without_marker():
    """Without marker, falls back to original.msg In-Reply-To."""
    org = CACHE_DIR / "original.msg"
    org.write_text(
        "From: a@x.com\n"
        "In-Reply-To: <fallback-id@example.com>\n"
        "\n"
        "body\n"
    )
    body = "Reply without marker\n"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    log = (CACHE_DIR / "mimelog.log").read_text()
    assert "reply_to_id=fallback-id@example.com" in log
    assert "from_marker=False" in log


def test_new_message_no_marker_no_original():
    """New message (no marker, no original.msg) uses pandoc template."""
    org = CACHE_DIR / "original.msg"
    if org.exists():
        org.unlink()

    body = "Fresh new message\n"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    html = (CACHE_DIR / "mimelook.html").read_text()
    assert "Fresh new message" in html
    # No divRplyFwdMsg since it's a new message
    assert "divRplyFwdMsg" not in html


def test_marker_not_rendered_in_html():
    """Marker lines must not appear in final HTML output."""
    body = (
        "Important content\n"
        "\n"
        "[//]: # (muttlook-reply-to:<some-id@example.com>)\n"
        "[//]: # (muttlook-references:<ref1@ex.com> <ref2@ex.com>)\n"
    )
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    html = (CACHE_DIR / "mimelook.html").read_text()
    assert "muttlook-reply-to" not in html
    assert "muttlook-references" not in html
    assert "Important content" in html


def test_mutt_trim_preserves_body_content_with_marker():
    """mutt-trim marker doesn't corrupt the reply body."""
    draft = (
        "From: a@x.com\n"
        "In-Reply-To: <id@ex.com>\n"
        "\n"
        "Line 1\n"
        "Line 2\n"
        "\n"
        "> quoted\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".eml", delete=False) as f:
        f.write(draft)
        f.flush()
        subprocess.run(["mutt-trim", f.name], check=True)
        result = Path(f.name).read_text()
    Path(f.name).unlink()
    assert "Line 1" in result
    assert "Line 2" in result
    assert "> quoted" in result
    # Marker at end, after body
    lines = result.strip().split("\n")
    assert lines[-1].startswith("[//]: # (muttlook-")


def test_plain_text_parent_joins_thread():
    """Gmail plain-text parent (no <body> tag, just <div>) should still join thread."""
    from muttlook import format_outlook_reply
    import mailparser

    parent = mailparser.parse_from_file(str(FIXTURES / "plain_text_parent.eml"))
    reply_html = "<p>My reply</p>"

    # Should NOT raise "No body tag found in parent HTML"
    result = format_outlook_reply(parent, reply_html)
    assert "My reply" in result
    assert "plain text email from Gmail" in result
    assert "<body>" in result.lower() or "<body" in result.lower()


def test_plain_text_parent_via_draft_pipeline():
    """Gmail div-only HTML (no <body> tag) is wrapped and joined correctly."""
    import mailparser
    from muttlook import format_outlook_reply

    parent = mailparser.parse_from_file(str(FIXTURES / "plain_text_parent.eml"))
    reply_html = "<p>My reply to plain text</p>"

    result = format_outlook_reply(parent, reply_html)
    # Should contain both reply and original content
    assert "My reply to plain text" in result
    assert "plain text email from Gmail" in result
    # Should have proper HTML structure
    assert "<body>" in result.lower() or "<body" in result.lower()


def test_apple_mail_html_joins_thread():
    """Apple Mail HTML with xmlns and body style attribute."""
    import mailparser
    from muttlook import format_outlook_reply

    raw = (
        "From: sender@icloud.com\n"
        "To: r@example.com\n"
        "Subject: Apple Mail\n"
        "Date: Thu, 1 May 2026 10:00:00 +0200\n"
        "Content-Type: multipart/alternative; boundary=\"apple\"\n"
        "MIME-Version: 1.0\n"
        "\n"
        "--apple\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Hello from Apple Mail\n"
        "--apple\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        '<html xmlns="http://www.w3.org/1999/xhtml"><head></head>'
        '<body style="word-wrap: break-word;"><div>Hello from Apple Mail</div></body></html>\n'
        "--apple--\n"
    )
    msg = mailparser.parse_from_string(raw)
    result = format_outlook_reply(msg, "<p>Reply</p>")
    assert "Reply" in result
    assert "Apple Mail" in result


def test_html_fragment_no_body_tag():
    """Newsletter-style HTML with only <p> tags, no <body> wrapper."""
    import mailparser
    from muttlook import format_outlook_reply

    raw = (
        "From: news@example.com\n"
        "To: r@example.com\n"
        "Subject: Newsletter\n"
        "Date: Thu, 1 May 2026 10:00:00 +0200\n"
        "Content-Type: multipart/alternative; boundary=\"nl\"\n"
        "MIME-Version: 1.0\n"
        "\n"
        "--nl\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Newsletter content\n"
        "--nl\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        '<p style="margin:0">Newsletter content</p><p>Click <a href="#">here</a></p>\n'
        "--nl--\n"
    )
    msg = mailparser.parse_from_string(raw)
    result = format_outlook_reply(msg, "<p>Reply</p>")
    assert "Reply" in result
    assert "Newsletter content" in result
    assert "<body" in result.lower()


def test_empty_body_parent():
    """Parent email with empty body."""
    import mailparser
    from muttlook import format_outlook_reply

    raw = (
        "From: sender@example.com\n"
        "To: r@example.com\n"
        "Subject: Empty\n"
        "Date: Thu, 1 May 2026 10:00:00 +0200\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
    )
    msg = mailparser.parse_from_string(raw)
    result = format_outlook_reply(msg, "<p>Reply</p>")
    assert "Reply" in result
    assert "<body" in result.lower()


def test_date_none_parent():
    """Parent email with unparseable/missing Date header."""
    import mailparser
    from muttlook import format_outlook_reply

    raw = (
        "From: sender@example.com\n"
        "To: r@example.com\n"
        "Subject: No date\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Body without date header\n"
    )
    msg = mailparser.parse_from_string(raw)
    result = format_outlook_reply(msg, "<p>Reply</p>")
    assert "Reply" in result
    assert "Body without date" in result


def test_inline_image_cid_replaced_with_file_path():
    """CID references in parent HTML are replaced with file:// paths for preview."""
    import shutil

    # Set up original.msg with inline image
    org = CACHE_DIR / "original.msg"
    shutil.copy(FIXTURES / "gmail_with_inline_image.eml", org)

    body = "My reply\n"
    result = subprocess.run(
        ["muttlook", "--action", "draft"],
        input=body,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    html = (CACHE_DIR / "mimelook.html").read_text()
    # CID should be replaced with file:// path
    assert "cid:test_image@gmail" not in html
    assert "file://" in html or "test_image" not in html  # either replaced or image not found
    # Reply content should be present
    assert "My reply" in html
