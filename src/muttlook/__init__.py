#!/usr/bin/env python3
"""Tool for mutt to reply outlook html mail with markdown power."""

import base64
import html
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import click

import mailparser
import markdown
import shortuuid
import shutil
from mailparser_reply import EmailReplyParser

# Configuration
TEMP_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "muttlook"
CONFIG = {
    "commands_file": TEMP_DIR / "mutt_cmd",
    "markdown_file": TEMP_DIR / "mimelook-md",
    "original_msg": TEMP_DIR / "original.msg",
    "html_file": TEMP_DIR / "mimelook.html",
    "log_file": TEMP_DIR / "mimelog.log",
    "template": "~/.local/share/pandoc/templates/email.html",
    "languages": ["en", "de"],
}

QUOTE_ESCAPE = "MIMELOOK_QUOTES"

# Setup logging

TEMP_DIR.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=str(CONFIG["log_file"]),  # Convert Path to string
    filemode="w",
)




def export_inline_attachments(message, dstdir):
    """Export inline attachments from mail to target directory."""
    try:
        message_html = message.body.split("--- mail_boundary ---")[1]
        logging.info("org message has mail_boundary :)")
    except IndexError:
        logging.error("org message does not have mail_boundary :(")
        message_html = message.body

    # Find inline attachments in HTML
    inlines = re.findall(r'src="cid:([^"]+)"', message_html)
    if not inlines:
        return []

    ret = []
    for inline in inlines:
        # Parse attachment ID
        attachment_id = inline.replace("cid:", "")

        # Find corresponding attachment
        attachment = next(
            (
                x
                for x in message.attachments
                if attachment_id in x.get("content-id", "")
            ),
            None,
        )

        if not attachment:
            logging.error(f"{attachment_id} not found in attachments")
            continue

        if attachment.get("content_transfer_encoding") != "base64":
            logging.warning(f"Skipping non-base64 attachment: {attachment_id}")
            continue

        # Extract filename and create unique path
        attachment_name = (
            attachment_id.split("@")[0] if "@" in attachment_id else attachment_id
        )
        dstfile = Path(dstdir) / attachment_name

        counter = 1
        while dstfile.exists():
            stem, suffix = dstfile.stem, dstfile.suffix
            dstfile = dstfile.parent / f"{stem}_extra{counter}{suffix}"
            counter += 1

        # Decode and save
        try:
            content = base64.decodebytes(attachment["payload"].encode("ascii"))
            dstfile.write_bytes(content)

            att = (f"{attachment_name}@{attachment_id}", str(dstfile))
            if att not in ret:
                ret.append(att)
        except Exception as e:
            logging.error(f"Failed to save attachment {attachment_id}: {e}")

    return ret


def format_outlook_header(fromaddr, sent, to, cc, subject):
    """Format outlook-style header."""
    header_parts = [f"<b>From:</b> {fromaddr}<br>", f"<b>Sent:</b> {sent}<br>"]

    if to:
        header_parts.append(f"<b>To:</b> {to}<br>")
    if cc:
        header_parts.append(f"<b>Cc:</b> {cc}<br>")

    header_parts.append(f"<b>Subject:</b> {subject}")

    return f"""<hr style="display:inline-block;width:98%" tabindex="-1">
<div id="divRplyFwdMsg" dir="ltr">
<font face="Calibri, sans-serif" style="font-size:11pt" color="#000000">
{''.join(header_parts)}
</font>
<div>&nbsp;</div>
</div>"""


def message_from_pipe(pipe):
    """Get message from pipe."""
    return mailparser.parse_from_string(pipe)


def message_from_msgid(msgid):
    """Get message from msgid using notmuch."""
    try:
        result = subprocess.run(
            ["notmuch", "search", "--output=files", f"id:{msgid}"],
            capture_output=True,
            text=True,
            check=True,
        )
        messagefiles = [f for f in result.stdout.strip().split("\n") if f]

        if not messagefiles:
            raise ValueError(f"No messages found for id: {msgid}")

        logging.info(f"Notmuch search results: {messagefiles}")
        return mailparser.parse_from_file(messagefiles[-1])

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"notmuch search failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to parse message: {e}")


def format_outlook_reply(message, htmltoinsert):
    """Create outlook-style html reply from message and desired html."""
    # Extract HTML part from message body
    parts = re.split(r"--- mail_boundary ---", message.body, flags=re.IGNORECASE)

    if len(parts) == 1:
        logging.info("org message does not have mail_boundary!")
        # Check if body contains HTML tags, if not create minimal HTML structure
        if not re.search(r"<html|<body", message.body, re.IGNORECASE):
            logging.info("No HTML structure found, creating minimal HTML wrapper")
            message_html = f"<html><body>{html.escape(message.body)}</body></html>"
        else:
            message_html = message.body
    else:
        # Find part with body tag
        message_html = None
        for part in parts[1:]:
            if re.search(r"<body.*?>", part):
                message_html = part.strip()
                break
        if not message_html:
            message_html = parts[-1].strip()

    # Normalize line endings
    message_html = message_html.replace("\r\n", "\n")

    # Extract header information
    headers = message.headers
    outlook_header = format_outlook_header(
        headers.get("From", ""),
        message.date.strftime("%d %B %Y %H:%M:%S"),
        headers.get("To"),
        headers.get("CC"),
        headers.get("Subject", ""),
    )

    # Find body tag and insert reply
    body_match = re.search(r"<body.*?>", message_html)
    if not body_match:
        raise ValueError("No body tag found in parent HTML")

    return f"{message_html[:body_match.end()]}\n{htmltoinsert}\n{outlook_header}\n{message_html[body_match.end():]}"


def escape_quotes(plaintext):
    """Convert "> "-style quotes into escaped format."""
    lines = []
    for line in plaintext.split("\n"):
        if line.startswith(">"):
            quote_count = len(line) - len(line.lstrip(">"))
            lines.append(f"[[{QUOTE_ESCAPE}|{quote_count}]]" + line[quote_count:])
        else:
            lines.append(line)
    return "\n".join(lines)


def unescape_quotes(string):
    """Convert escaped quotes back to original form."""
    pattern = rf"\[\[{re.escape(QUOTE_ESCAPE)}\|(\d+)\]\]"
    return re.sub(pattern, lambda m: ">" * int(m.group(1)), string)


def escape_signature_linebreaks(plaintext):
    """Escape signature linebreaks."""
    sig_match = re.search(r"^-- ", plaintext, re.MULTILINE)
    if sig_match:
        content = plaintext[: sig_match.start()]
        signature = plaintext[sig_match.start() :].replace("\n", "  \n")
        return content + signature
    return plaintext


def find_mime_parts(plaintext):
    """Find MIME parts in plaintext. Returns text without parts and list of parts."""
    parts = re.findall(r"<#part.*?<#/part>", plaintext, re.DOTALL)
    first_part = re.search(r"<#part.*?<#/part>", plaintext, re.DOTALL)
    text = plaintext[: first_part.start()] if first_part else plaintext
    return text, parts


def html_escape(text):
    """Escape HTML, preserving code blocks (lines starting with 4 spaces)."""
    lines = []
    for line in text.split("\n"):
        if line.startswith("    "):
            lines.append(line)
        else:
            lines.append(html.escape(line))
    return "\n".join(lines)


def plain2fancy(msg):
    """Format plaintext to outlook-style reply."""
    # Skip EmailReplyParser for new messages (no quoted lines) — it strips indentation
    has_quotes = any(line.startswith(">") for line in msg.split("\n"))
    if has_quotes:
        reply = EmailReplyParser(languages=CONFIG["languages"]).read(text=msg)
        latest_reply = reply.latest_reply or ""
    else:
        latest_reply = msg

    # Convert Obsidian callouts (> [!type] title) to HTML before markdown processing
    def convert_obsidian_callouts(text):
        lines = text.split("\n")
        result = []
        i = 0
        while i < len(lines):
            m = re.match(r"^>\s*\[!(\w+)\]\s*(.*)", lines[i])
            if m:
                ctype, title = m.group(1), m.group(2) or m.group(1).title()
                body_lines = []
                i += 1
                while i < len(lines) and lines[i].startswith(">"):
                    body_lines.append(lines[i].lstrip("> "))
                    i += 1
                body = "<br>".join(body_lines)
                result.append(
                    f'<div style="border-left:4px solid #4a9eff;padding:8px 12px;margin:8px 0;background:#f0f7ff">'
                    f"<strong>{ctype.upper()}: {title}</strong><br>{body}</div>"
                )
            else:
                result.append(lines[i])
                i += 1
        return "\n".join(result)

    latest_reply = convert_obsidian_callouts(latest_reply)

    # Ensure blank lines before top-level lists/checklists (markdown requires them)
    # Only match lines NOT indented (top-level), to preserve nested list structure
    latest_reply = re.sub(r"(\S)\n(- \[[ x]\])", r"\1\n\n\2", latest_reply)
    latest_reply = re.sub(r"(\S)\n(\* )", r"\1\n\n\2", latest_reply)
    latest_reply = re.sub(r"(\S)\n(- (?!\[))", r"\1\n\n\2", latest_reply)
    latest_reply = re.sub(r"(\S)\n(\d+\. )", r"\1\n\n\2", latest_reply)

    # Convert Obsidian-style checkboxes to standard markdown before pymdownx
    latest_reply = re.sub(r"- \[/\]", "- [x] ◐", latest_reply)   # in-progress (half circle)
    latest_reply = re.sub(r"- \[-\]", "- [x] ―", latest_reply)   # cancelled (dash)
    latest_reply = re.sub(r"- \[>\]", "- [ ] ▷", latest_reply)   # deferred (triangle)

    text2html = (
        markdown.markdown(
            latest_reply,
            extensions=[
                "tables",
                "fenced_code",
                "nl2br",
                "toc",
                "def_list",
                "sane_lists",
                "pymdownx.tasklist",
                "pymdownx.tilde",
            ],
        )
        if latest_reply
        else ""
    )

    # Get original message - check if file exists
    if not CONFIG["original_msg"].exists():
        logging.error(f"Original message file not found: {CONFIG['original_msg']}")
        logging.info("Available files in temp dir:")
        for f in TEMP_DIR.glob("*"):
            logging.info(f"  {f}")
        # Create a simple HTML message without reply context
        try:
            result = subprocess.run(
                [
                    "pandoc",
                    "-f",
                    "markdown+lists_without_preceding_blankline+hard_line_breaks",
                    "-t",
                    "html5",
                    "--standalone",
                    "--template",
                    CONFIG["template"],
                ],
                input=latest_reply,
                capture_output=True,
                text=True,
                check=True,
            )
            madness = result.stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Error generating HTML: {e}")
            madness = f"<html><body>{text2html}</body></html>"
        attachments = []
    else:
        org_reply_msg = mailparser.parse_from_file(CONFIG["original_msg"])

        # Find reply-to message ID: In-Reply-To first, then last References entry
        reply_to_id = None
        if "In-Reply-To" in org_reply_msg.headers:
            reply_to_id = org_reply_msg.headers["In-Reply-To"].strip("<>")
        elif "References" in org_reply_msg.headers:
            refs = org_reply_msg.headers["References"].strip().split()
            if refs:
                reply_to_id = refs[-1].strip("<>")

        if reply_to_id:
            try:
                message = message_from_msgid(reply_to_id)
                madness = format_outlook_reply(message, text2html)

                # Export inline attachments
                TEMP_DIR.mkdir(exist_ok=True)
                attachments = export_inline_attachments(message, str(TEMP_DIR))
            except (RuntimeError, Exception) as e:
                logging.warning(f"Could not fetch reply-to message: {e}, falling back to new message mode")
                reply_to_id = None

        if not reply_to_id:
            # New message - use pandoc template
            try:
                result = subprocess.run(
                    [
                        "pandoc",
                        "-f",
                        "markdown+lists_without_preceding_blankline+hard_line_breaks",
                        "-t",
                        "html5",
                        "--standalone",
                        "--template",
                        CONFIG["template"],
                    ],
                    input=latest_reply,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                madness = result.stdout
            except subprocess.CalledProcessError as e:
                logging.error(f"Error generating HTML: {e}")
                madness = ""
            attachments = []

    # Handle inline images in reply
    image_links = re.findall(r"!\[.*?\]\(([^)]+)\)", latest_reply)
    cid_mapping = {}
    new_reply = latest_reply

    for link in image_links:
        filename = Path(link).name.replace(" ", "_")
        destination_path = TEMP_DIR / filename

        try:
            shutil.copy(link, destination_path)
            logging.info(f"File copied to: {destination_path}")

            # Generate CID in Outlook style
            cid = f"{filename}@{shortuuid.uuid(name=filename)}"
            cid_mapping[cid] = str(destination_path)

            # Replace in markdown and HTML
            new_reply = new_reply.replace(link, f"cid:{cid}")
            madness = madness.replace(link, f"cid:{cid}")

        except Exception as e:
            logging.error(f"Error copying file: {e}")

    # Update message and attachments
    if image_links:
        new_msg = msg.replace(latest_reply, new_reply)
        attachments.extend(cid_mapping.items())
    else:
        new_msg = msg

    logging.info(f"Final attachments: {attachments}")

    # Write output files
    CONFIG["html_file"].write_text(madness)
    CONFIG["markdown_file"].write_text(new_msg)

    # Generate mutt commands - use original format
    attachment_str = ""
    if attachments:
        for attachment in attachments:
            attachment_str += f"<attach-file>'{attachment[1]}'<enter><toggle-disposition><edit-content-id>^u'{attachment[0]}'<enter><tag-entry>"

    if attachment_str:
        mutt_cmd = "push <attach-file>'{}'<enter><toggle-disposition><toggle-unlink><first-entry><detach-file><attach-file>'{}'<enter><toggle-disposition><toggle-unlink><tag-entry><previous-entry><tag-entry><group-alternatives>{}<first-entry><tag-entry><group-related>".format(
            CONFIG["markdown_file"], CONFIG["html_file"], attachment_str
        )
    else:
        mutt_cmd = "push <attach-file>'{}'<enter><toggle-disposition><toggle-unlink><tag-entry><previous-entry><tag-entry><group-alternatives>".format(
            CONFIG["html_file"]
        )

    CONFIG["commands_file"].write_text(mutt_cmd)
    logging.info(f"Mutt command written to: {CONFIG['commands_file']}")
    logging.info(f"Command: {mutt_cmd}")


def view_html(pipe):
    """View HTML email in browser with inline images resolved."""
    message = message_from_pipe(pipe)
    viewdir = TEMP_DIR / "view"
    if viewdir.exists():
        shutil.rmtree(viewdir)
    viewdir.mkdir(parents=True, exist_ok=True)

    # Get HTML body
    parts = re.split(r"--- mail_boundary ---", message.body, flags=re.IGNORECASE)
    body_html = None
    for part in parts:
        if re.search(r"<html|<body|<table|<div", part, re.IGNORECASE):
            body_html = part.strip()
            break
    if not body_html:
        body_html = f"<html><body><pre>{html.escape(message.body)}</pre></body></html>"

    # Export inline images and rewrite CID references to local files
    for att in message.attachments:
        cid = att.get("content-id", "").strip("<>")
        if not cid:
            continue
        fname = cid.split("@")[0] if "@" in cid else cid
        fpath = viewdir / fname
        try:
            content = base64.decodebytes(att["payload"].encode("ascii"))
            fpath.write_bytes(content)
            body_html = body_html.replace(f"cid:{cid}", str(fpath))
        except Exception:
            pass

    outfile = viewdir / "message.html"
    # Force UTF-8 charset — mailparser decodes to Python str (UTF-8),
    # but original HTML may declare a different charset (e.g. Windows-1252)
    body_html = re.sub(
        r'(<meta[^>]*charset=)["\']?[^"\';>\s]+["\']?',
        r'\1"utf-8"',
        body_html,
        flags=re.IGNORECASE,
    )
    if "charset" not in body_html.lower():
        body_html = f'<meta charset="utf-8">\n{body_html}'
    outfile.write_text(body_html, encoding="utf-8")

    if sys.platform == "darwin":
        subprocess.run(["open", str(outfile)])
    else:
        subprocess.run(["xdg-open", str(outfile)])


def view_tui(pipe, renderer=None, width=None):
    """View HTML email in terminal with styled ANSI output."""
    if renderer is None:
        renderer = render_html_to_ansi
    message = message_from_pipe(pipe)

    # Get HTML body
    parts = re.split(r"--- mail_boundary ---", message.body, flags=re.IGNORECASE)
    body_html = None
    for part in parts:
        if re.search(r"<html|<body|<table|<div", part, re.IGNORECASE):
            body_html = part.strip()
            break
    if not body_html:
        print(message.body)
        return

    print(renderer(body_html, width=width))


def _unwrap_layout_tables(html_text):
    """Replace layout tables with <div>s, keep data tables intact.

    A table is considered a data table if it has: <th> elements, a
    border attribute (border="1" etc.), or a first row where all cells
    are bold (common Outlook pattern). Everything else is layout.
    """
    from html.parser import HTMLParser

    class _TableFinder(HTMLParser):
        """Find table boundaries and classify as data vs layout."""

        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.tables = []  # [(start_offset, end_offset, is_data)]
            self._stack = []  # [(tag_start_offset, has_th, has_bold_hdr, has_border)]
            self._raw = ""
            self._in_first_row = False
            self._first_row_bold_cells = 0
            self._first_row_total_cells = 0
            self._first_row_done = False

        def feed(self, data):
            self._raw = data
            super().feed(data)

        def _offset(self):
            line, col = self.getpos()
            pos = 0
            for i, ln in enumerate(self._raw.split("\n"), 1):
                if i == line:
                    return pos + col
                pos += len(ln) + 1
            return pos

        def handle_starttag(self, tag, attrs):
            if tag == "table":
                has_border = any(
                    k == "border" and v and v != "0" for k, v in attrs
                )
                self._stack.append([self._offset(), False, False, has_border])
                self._in_first_row = False
                self._first_row_done = False
                self._first_row_bold_cells = 0
                self._first_row_total_cells = 0
            elif tag == "th" and self._stack:
                self._stack[-1][1] = True
            elif tag == "tr" and self._stack and not self._first_row_done:
                self._in_first_row = True
                self._first_row_bold_cells = 0
                self._first_row_total_cells = 0
            elif tag == "td" and self._in_first_row:
                self._first_row_total_cells += 1
                # Peek ahead for <b>/<strong> as first child after </td>
                pos = self._offset()
                close = self._raw.find(">", pos)
                if close != -1:
                    after = self._raw[close + 1:close + 201].lstrip()
                    if re.match(r"<(?:b|strong)\b", after, re.IGNORECASE):
                        self._first_row_bold_cells += 1

        def handle_endtag(self, tag):
            if tag == "tr" and self._in_first_row:
                self._in_first_row = False
                self._first_row_done = True
                if self._first_row_total_cells >= 2 and self._first_row_bold_cells == self._first_row_total_cells:
                    if self._stack:
                        self._stack[-1][2] = True
            elif tag == "table" and self._stack:
                start, has_th, has_bold_hdr, has_border = self._stack.pop()
                end = self._raw.find(">", self._offset())
                if end == -1:
                    end = self._offset()
                else:
                    end += 1
                self.tables.append((start, end, has_th or has_bold_hdr or has_border))

    parser = _TableFinder()
    try:
        parser.feed(html_text)
    except Exception:
        return html_text

    if not parser.tables:
        return html_text

    # Process from end to start to preserve offsets
    for start, end, is_data in reversed(sorted(parser.tables, key=lambda t: t[0])):
        if is_data:
            continue
        table_html = html_text[start:end]
        unwrapped = re.sub(
            r"</?(?:table|tbody|thead|tfoot|tr)\b[^>]*>", "", table_html, flags=re.IGNORECASE
        )
        unwrapped = re.sub(r"<td\b[^>]*>", "<div>", unwrapped, flags=re.IGNORECASE)
        unwrapped = re.sub(r"</td>", "</div>", unwrapped, flags=re.IGNORECASE)
        html_text = html_text[:start] + unwrapped + html_text[end:]

    return html_text


def render_html_to_ansi(html_text, width=None):
    """Render HTML to styled ANSI terminal text (default: html2text --colour pipeline).

    Pipeline: Outlook preprocess → layout table unwrap → html2text --colour → ANSI remap → header dim → Teams strip

    Args:
        html_text: HTML content to render.
        width: Output width in columns. Auto-detected from terminal if None.
               Callers should pass explicit width when terminal detection is
               unreliable (e.g. neomutt mailcap, fzf preview).
    """
    import shutil

    if width is None:
        width = shutil.get_terminal_size((120, 24)).columns

    # Phase 1: Outlook MsoNormal preprocessing
    html_text = re.sub(r"<o:p></o:p>", "", html_text)
    html_text = re.sub(
        r'<p\s+class="MsoNormal"[^>]*>\s*(?:<[^>]+>\s*)*&nbsp;\s*(?:<[^>]+>\s*)*</p>',
        "\n<br>\n",
        html_text,
    )
    html_text = re.sub(r'</p>\s*<p\s+class="MsoNormal"[^>]*>', " ", html_text)

    # Phase 1.5: Unwrap layout tables (keep data tables)
    html_text = _unwrap_layout_tables(html_text)

    # Phase 2: html2text --colour (Rust binary)
    h2t = shutil.which("html2text", path=os.path.expanduser("~/.local/share/cargo/bin"))
    if not h2t:
        h2t = shutil.which("html2text")
    if not h2t:
        return re.sub(r"<[^>]+>", "", html_text)

    result = subprocess.run(
        [h2t, "-w", str(width), "--colour"],
        input=html_text,
        capture_output=True,
        text=True,
    )
    text = result.stdout

    # Phase 3: ANSI remap + shared cleanup
    from .mutt_trim import classify_header_block

    lines = text.split("\n")
    # Remap bold yellow → purple, markdown headers → bold blue/cyan
    remapped = []
    for line in lines:
        line = line.replace("\x1b[38;5;11m", "\x1b[35m")
        line = re.sub(r"^### (.*)$", "\x1b[1;36m\\1\x1b[0m", line)
        line = re.sub(r"^## (.*)$", "\x1b[1;36m\\1\x1b[0m", line)
        line = re.sub(r"^# (.*)$", "\x1b[1;34m\\1\x1b[0m", line)
        remapped.append(line)

    out = classify_header_block(remapped)
    return "\n".join(out)


def render_html_rich(html_text, width=120):
    """Render HTML to styled ANSI terminal text (experimental Rich pipeline).

    Pipeline: Outlook preprocess → html2text (plain) → Rich Markdown renderer
    """
    import shutil
    from io import StringIO

    from rich.console import Console
    from rich.markdown import Markdown
    from rich.theme import Theme

    html_text = re.sub(r"<o:p></o:p>", "", html_text)
    html_text = re.sub(
        r'<p\s+class="MsoNormal"[^>]*>\s*(?:<[^>]+>\s*)*&nbsp;\s*(?:<[^>]+>\s*)*</p>',
        "\n<br>\n",
        html_text,
    )
    html_text = re.sub(r'</p>\s*<p\s+class="MsoNormal"[^>]*>', " ", html_text)
    html_text = re.sub(r'(<t[dh][^>]*>)\s*<b\b[^>]*>(.*?)</b>\s*', r'\1\2', html_text, flags=re.DOTALL | re.IGNORECASE)
    html_text = re.sub(r'(<t[dh][^>]*>)\s*<strong\b[^>]*>(.*?)</strong>\s*', r'\1\2', html_text, flags=re.DOTALL | re.IGNORECASE)

    h2t = shutil.which("html2text", path=os.path.expanduser("~/.local/share/cargo/bin"))
    if not h2t:
        h2t = shutil.which("html2text")
    if not h2t:
        return re.sub(r"<[^>]+>", "", html_text)

    result = subprocess.run([h2t, "-w", str(width)], input=html_text, capture_output=True, text=True)
    md_text = result.stdout

    from .mutt_trim import classify_header_block

    lines = md_text.split("\n")
    processed = classify_header_block(lines)

    buf = StringIO()
    tn_theme = Theme({
        "markdown.h1": "bold blue", "markdown.h2": "bold cyan",
        "markdown.h3": "bold cyan", "markdown.h4": "bold cyan",
        "markdown.code": "blue", "markdown.strong": "bold magenta",
    })
    console = Console(file=buf, width=width, force_terminal=True, theme=tn_theme)
    md_block = []
    for line in processed:
        if "\x1b[90m" in line or re.search(r"[\u2500\u2502\u253c\u252c\u2534\u251c\u2524\u250c\u2510\u2514\u2518]", line):
            if md_block:
                console.print(Markdown("\n".join(md_block)))
                md_block = []
            buf.write(line + "\n")
        else:
            md_block.append(line)
    if md_block:
        console.print(Markdown("\n".join(md_block)))

    output = buf.getvalue()
    out_lines = output.split("\n")
    cleaned = []
    prev_blank = False
    for line in out_lines:
        if re.search(r"[\u2500\u2502\u253c\u252c\u2534\u251c\u2524\u250c\u2510\u2514\u2518]", line):
            line = line.replace("**", "")
        else:
            line = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"\x1b[1;35m{m.group(1)}\x1b[0m", line)
            line = line.replace("**", "")
        line = line.rstrip()
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        prev_blank = is_blank
        cleaned.append(line)
    return "\n".join(cleaned)


def send_hook_cleaner(path):
    """Clean temp files called by send hook."""
    temp_path = Path(path)
    if not temp_path.exists():
        return

    for item in temp_path.rglob("*"):
        if item.is_file():
            # Keep log files, command files, and original files
            if not any(ext in item.name for ext in [".log", "_cmd", "original"]):
                try:
                    item.unlink()
                    logging.info(f"Deleted file: {item}")
                except Exception as e:
                    logging.error(f"Failed to delete {item}: {e}")
        elif item.is_dir() and item != temp_path:
            try:
                shutil.rmtree(item)
                logging.info(f"Deleted folder: {item}")
            except Exception as e:
                logging.error(f"Failed to delete {item}: {e}")


@click.command()
@click.option(
    "--action",
    type=click.Choice(["clean", "draft", "view", "tui", "tui-rich"]),
    help="Specify the action to perform.",
    required=True,
)
@click.option("--width", "-w", type=int, default=None, help="Output width in columns (auto-detect if omitted).")
@click.argument("file", required=False, type=click.Path(exists=True))
def main(action, width, file):
    """Main function with click interface."""
    if action == "clean":
        send_hook_cleaner(str(TEMP_DIR))
    elif action == "draft":
        plain2fancy(sys.stdin.read())
    elif action == "view":
        view_html(sys.stdin.read())
    elif action in ("tui", "tui-rich"):
        renderer = render_html_rich if action == "tui-rich" else render_html_to_ansi
        if file:
            with open(file, "rb") as f:
                raw = f.read()
            charset_m = re.search(rb'charset=([^\s"\'>;]+)', raw)
            charset = charset_m.group(1).decode("ascii", errors="ignore") if charset_m else "utf-8"
            try:
                html_text = raw.decode(charset)
            except (UnicodeDecodeError, LookupError):
                html_text = raw.decode("utf-8", errors="replace")
            print(renderer(html_text, width=width))
        else:
            view_tui(sys.stdin.read(), renderer=renderer, width=width)


if __name__ == "__main__":
    # send_hook_cleaner(str(TEMP_DIR))  # Temporarily disabled to check logs
    try:
        main()
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise
