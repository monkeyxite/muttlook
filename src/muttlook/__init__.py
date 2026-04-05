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
import magic
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

mime = magic.Magic(mime=True)


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
    # Parse reply content
    reply = EmailReplyParser(languages=CONFIG["languages"]).read(text=msg)
    latest_reply = reply.latest_reply or ""

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

    # Ensure blank lines before lists/checklists (markdown requires them)
    latest_reply = re.sub(r"(\S)\n(- \[[ x]\])", r"\1\n\n\2", latest_reply)
    latest_reply = re.sub(r"(\S)\n(- )", r"\1\n\n\2", latest_reply)
    latest_reply = re.sub(r"(\S)\n(\d+\. )", r"\1\n\n\2", latest_reply)

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
                    "markdown",
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

        # Handle reply-to message
        if "In-Reply-To" in org_reply_msg.headers:
            reply_to_id = org_reply_msg.headers["In-Reply-To"].strip("<>")
            message = message_from_msgid(reply_to_id)
            madness = format_outlook_reply(message, text2html)

            # Export inline attachments
            TEMP_DIR.mkdir(exist_ok=True)
            attachments = export_inline_attachments(message, str(TEMP_DIR))
        else:
            # New message - use pandoc template
            try:
                result = subprocess.run(
                    [
                        "pandoc",
                        "-f",
                        "markdown",
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
            attachment_str += "<attach-file>'{}'<enter><toggle-disposition><edit-content-id>^u'{}'<enter><tag-entry>".format(
                attachment[1], attachment[0]
            )

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
    type=click.Choice(["clean", "draft"]),
    help="Specify the action to perform.",
    required=True,
)
def main(action):
    """Main function with click interface."""
    if action == "clean":
        send_hook_cleaner(str(TEMP_DIR))
    elif action == "draft":
        plain2fancy(sys.stdin.read())


if __name__ == "__main__":
    # send_hook_cleaner(str(TEMP_DIR))  # Temporarily disabled to check logs
    try:
        main()
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise
