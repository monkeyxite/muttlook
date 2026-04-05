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
