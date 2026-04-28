#!/usr/bin/env python3
"""Python replacement for mutt-trim with similar functionality."""

import sys
import re
import os
from pathlib import Path

# Configuration
IND_MAX = 5  # Keep nested quotes up to this level
GAP = 0  # Blank lines between different quote levels

# Name patterns
NAME = r"[a-zA-Z]+([\'`-][a-zA-Z]+|[.])*"
FULLNAME = rf"\b({NAME}[,]?\s+)*{NAME}\b"

# Greetings patterns
GREETINGS = [
    rf"Dear\s+{FULLNAME}([,.]|\s*!)?",
    rf"[Hh](ello|i|ey)(\s+{FULLNAME})?([,.]|\s*!)?",
    rf"Sehr geehrter?\s+{FULLNAME}([,.]|\s*!)?",
    rf"Lieber?\s+{FULLNAME}([,.]|\s*!)?",
    rf"Guten Tag(\s+{FULLNAME})?([,.]|\s*!)?",
    rf"[Hh]allo(\s+{FULLNAME})?([,.]|\s*!)?",
    rf"[Mm]oin(\s+{FULLNAME})?([,.]|\s*!)?",
    rf"[Hh]ola(\s+{FULLNAME})?([,.]|\s*!)?",
    rf"[Bb]onjour(\s+{FULLNAME})?([,.]|\s*!)?",
]

# Greetouts patterns
GREETOUTS = [
    r"([Ww]ith )?(([Kk]ind|[Bb]est|[Ww]arm) )?([Rr]egards|[Ww]ishes)([,.]|\s*!)?",
    r"[Bb]est([,.]|\s*!)?",
    r"[Cc]heers([,.]|\s*!)?",
    r"[Mm]it ([Vv]iel|[Bb]est|[Ll]ieb|[Ff]reundlich)en [Gg]r(ü|ue)(ß|ss)en([,.]|\s*!)?",
    r"(([Vv]iel|[Bb]est|[Ll]ieb|[Ff]reundlich)e )?[Gg]r(ü|ue)(ß|ss)e([,.]|\s*!)?",
    r"([LV]|MF)G([,.]|\s*!)?",
    r"[Aa]tenciosamente([,.]|\s*!)?",
    r"[Cc]ordialmente([,.]|\s*!)?",
]


# ── Shared cleanup (used by both reply trim and TUI view) ──

_ANSI_RE = re.compile(r"\x1b\[[^m]*m")
_CID_RE = re.compile(r"\[cid:[^\]]*\]")
_HEADER_RE = re.compile(r"^(From|Sent|To|Cc|Subject|When|Where|Importance|Date):")
_FWD_SEP_RE = re.compile(r"^-{3,}\s*(Original|Forwarded)")
_FILLER_RE = re.compile(r"^_{10,}$")
_TEAMS_RE = re.compile(r"Microsoft Teams meeting|Meeting ID:")
_GREETING_RE = re.compile(
    r"^(" + "|".join(GREETINGS) + r")\s*$"
)
_GREETOUT_RE = re.compile(
    r"^(" + "|".join(GREETOUTS) + r")\s*$"
)


def strip_cid(line):
    """Remove [cid:...] image references."""
    return _CID_RE.sub("", line)


def strip_ansi(text):
    """Remove ANSI escape codes."""
    return _ANSI_RE.sub("", text)


def is_filler(line):
    """Check if line is a filler/separator (underscores, Teams boilerplate)."""
    stripped = strip_ansi(line).strip()
    return bool(_FILLER_RE.match(stripped) or _TEAMS_RE.search(stripped))


def is_greeting(line):
    """Check if line is a standalone greeting (Dear X, Hi X, Hallo X, etc.).

    Only matches lines that are purely a greeting — not sentences that
    happen to start with a greeting word.
    """
    stripped = strip_ansi(line).strip()
    # Must be short (greetings are typically < 60 chars) and match fully
    if len(stripped) > 60:
        return False
    return bool(_GREETING_RE.match(stripped))


def is_signoff(line):
    """Check if line is a signoff (Best regards, Cheers, MFG, etc.)."""
    stripped = strip_ansi(line).strip()
    return bool(_GREETOUT_RE.match(stripped))


def dim_line(line, width=None):
    """Wrap line in dim ANSI (grey), pre-wrapping long lines.

    Neomutt's pager resets ANSI codes at wrap points, so we pre-wrap
    dimmed lines and apply dim to each sub-line individually.
    """
    import shutil
    import textwrap

    if width is None:
        width = shutil.get_terminal_size((120, 24)).columns
    plain = strip_ansi(line)
    if len(plain) <= width:
        return f"\x1b[90m{plain}\x1b[0m"
    wrapped = textwrap.wrap(plain, width=width, break_on_hyphens=False)
    return "\n".join(f"\x1b[90m{sub}\x1b[0m" for sub in wrapped)


def classify_header_block(lines):
    """Process lines: dim forwarded header blocks, strip CID, remove filler.

    Returns cleaned lines with:
    - CID references removed
    - Forwarded headers (From/Sent/To/Subject blocks) dimmed
    - Forwarded separators dimmed
    - Filler/Teams boilerplate removed
    - Consecutive blank lines squeezed
    - Greetings/signoffs stripped from non-quoted text
    """
    out = []
    in_hdr = False
    prev_blank = False

    for line in lines:
        line = strip_cid(line)
        stripped = strip_ansi(line)

        # Forwarded header block detection
        if _HEADER_RE.match(stripped):
            in_hdr = True
        elif in_hdr and stripped.strip() == "":
            in_hdr = False

        # Filler / Teams boilerplate
        if is_filler(line):
            continue

        # Dim forwarded headers
        if in_hdr:
            line = dim_line(line)
        elif _FWD_SEP_RE.match(stripped):
            line = dim_line(line)

        # Squeeze blanks
        is_blank = stripped.strip() == ""
        if is_blank and prev_blank:
            continue
        prev_blank = is_blank

        out.append(line)

    return out


def trim_mail(mail_lines):
    """Trim quoted mail content similar to Perl mutt-trim."""
    purged_mail = []
    saw_blank_line = False
    prev_inds = 0
    saw_own_sig = False
    inds_other_sig = 0
    quote_header = False
    extra_pref = ""

    for line in mail_lines:
        # Keep non-quoted lines as is
        if not line.startswith(">"):
            purged_mail.append(line)
            continue

        # Keep all lines after own signature unmodified
        if line.strip() == "--" or saw_own_sig:
            saw_own_sig = True
            purged_mail.append(line)
            continue

        # Normalize quote prefixes: tighten "> > " to ">> "
        match = re.match(r"^([>\s]+)(.*)$", line)
        if match:
            pref, suff = match.groups()
            pref = re.sub(r">\s*(?!$)", ">", pref)
            pref = re.sub(r"^\s*(>+)\s*", r"\1 ", pref)
            line = pref + suff + "\n"

        # Handle Outlook quote headers
        word = r"[a-zA-Z]+([\'`-][a-zA-Z]+)*"
        if re.match(rf"^>+ [-_=]{{3,}}\s*{word}(\s+{word})*\s*[-_=]{{3,}}$", line):
            quote_header = True
            continue

        if quote_header and not re.match(
            rf"^>+ ([-*]\s*)?{word}(\s+{word})*\s*:\s+", line
        ):
            extra_pref = ">" + extra_pref
            quote_header = False

        pref = extra_pref + (match.group(1) if match else "")
        line = pref + (match.group(2) if match else line.lstrip(">").lstrip()) + "\n"

        # Skip if too many quote levels
        inds = pref.count(">")
        if inds > IND_MAX:
            continue

        # Remove other signatures
        if re.match(r"^>+ -- $", line):
            inds_other_sig = inds
        if inds == inds_other_sig and inds_other_sig > 0:
            continue
        elif inds != inds_other_sig:
            inds_other_sig = 0

        # Remove quoted greetings
        skip_line = False
        for greeting in GREETINGS:
            if re.match(rf"^>+ {greeting}$", line):
                skip_line = True
                break
        if skip_line:
            continue

        # Remove quoted greetouts
        for greetout in GREETOUTS:
            if re.match(rf"^>+ {greetout}$", line):
                skip_line = True
                break
        if skip_line:
            continue

        # Remove quoted filler lines
        if re.match(r"^>+ \s*[-_=+#*]+$", line):
            continue

        # Insert gap between different quote levels
        if GAP > 0 and prev_inds != inds:
            line = "\n" * GAP + line
        prev_inds = inds

        # Squeeze multiple blank lines
        if re.match(r"^>+ \s*$", line):
            if saw_blank_line:
                continue
            saw_blank_line = True
        else:
            saw_blank_line = False

        purged_mail.append(line)

    return purged_mail


def main():
    """Main function."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} MAIL", file=sys.stderr)
        sys.exit(1)

    mail_file = sys.argv[1]

    try:
        with open(mail_file, encoding="utf-8") as f:
            mail_lines = f.readlines()
    except Exception as e:
        print(f"Error reading {mail_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Save original message for muttlook
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    org_msg_path = cache_dir / "muttlook" / "original.msg"
    org_msg_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(org_msg_path, "w", encoding="utf-8") as f:
            f.writelines(mail_lines)
    except Exception as e:
        print(f"Warning: Could not save original message: {e}", file=sys.stderr)

    # Trim and write back
    purged_lines = trim_mail(mail_lines)

    try:
        with open(mail_file, "w", encoding="utf-8") as f:
            f.writelines(purged_lines)
    except Exception as e:
        print(f"Error writing {mail_file}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
