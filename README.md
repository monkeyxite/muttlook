# Muttlook

A unified Python tool for reading, replying, and composing HTML emails in mutt/neomutt. Handles Outlook/OWA emails with Markdown composition, terminal rendering, and browser viewing.

## Features

- **TUI rendering** — styled terminal output via `html2text --colour` with Tokyo Night Storm ANSI colors (bold→purple, headers→blue, forwarded headers→dim gray, Teams boilerplate stripped)
- **Browser viewing** — full HTML with inline CID images resolved, opens in default browser
- **Markdown reply/compose** — write in markdown, send as HTML preserving Outlook thread formatting
- Obsidian-style extensions: callouts (`> [!note]`), task checkboxes (`[/]` `[-]` `[>]`), ~~strikethrough~~, definition lists, fenced code, tables
- Inline image CID handling for both replies and new messages
- Reply detection via `In-Reply-To` with `References` header fallback
- Graceful fallback to new message mode when notmuch can't find the original
- Built-in email trimming (`mutt-trim`)
- Notmuch integration for message lookup

## Installation

```bash
# From GitHub
uv tool install "muttlook @ git+https://github.com/monkeyxite/muttlook.git" --force

# From local clone
uv tool install -e . --force
```

## Dependencies

### Python (auto-installed)

click, mail-parser (>=3.9.3), mail-parser-reply, markdown (>=3.1.1), pymdown-extensions (>=10.0), rich (>=13.0), shortuuid

### System

- `html2text` — Rust crate (`cargo install html2text-cli`) for TUI rendering (`--colour` mode)
- Pandoc — HTML template processing for new messages
- Notmuch — finding original messages by Message-ID
- Neomutt — MUA integration

## Actions

| Action | Input | Output | Use case |
|--------|-------|--------|----------|
| `--action tui <file>` | Raw HTML file | Styled ANSI text to stdout | Neomutt mailcap pager, nm-html-extract |
| `--action tui` (stdin) | Full RFC822 email | Styled ANSI text to stdout | Pipe from notmuch show |
| `--action tui-rich` | Raw HTML file or RFC822 | Rich-styled ANSI text | Experimental alternative renderer |
| `--action view` (stdin) | Full RFC822 email | Opens HTML in browser | `,w` macro, nms Ctrl+O |
| `--action draft` (stdin) | Email draft from neomutt | HTML file + mutt_cmd | `,m` macro, nms Ctrl+R |
| `--action clean` | — | Removes temp files | Send hook cleanup |

## Use Cases

### 1. Neomutt pager (auto_view HTML)

Mailcap entry — renders HTML emails inline in the neomutt pager:

```mailcap
text/html; muttlook --action tui %s; nametemplate=%s.html; copiousoutput;
```

### 2. nm-search (nms) fzf preview

`nm-html-extract` extracts the HTML part via notmuch and pipes to muttlook:

```
fzf --preview → nm-html-extract → notmuch show --part=N → muttlook --action tui <file>
```

### 3. nm-search inline shortcuts

```
Ctrl+O → muttlook --action view   (browser)
Ctrl+R → muttlook --action draft  (reply via neomutt)
Ctrl+F → notmuch tag              (GTD: archive/action/waiting/defer/done)
```

### 4. Neomutt compose macros

Reply to Outlook email with markdown:

```muttrc
macro compose ,m "<first-entry>\
<pipe-entry>notmuch new 2>/dev/null; muttlook --action draft<enter>\
<enter-command>set compose_confirm_detach_first=no<enter>\
<enter-command>source ~/.cache/muttlook/mutt_cmd<enter>\
<enter-command>set compose_confirm_detach_first=yes<enter>" "reply with md→html"
```

View HTML in browser with inline images:

```muttrc
macro pager,attach ,w "<pipe-message>muttlook --action view<enter>" "view HTML in browser"
```

### 5. Markdown in replies

```markdown
# Summary

- Action item 1
- Action item 2

| Name | Task |
|------|------|
| Alice | Review |

> [!note] Reminder
> Meeting moved to Friday

- [x] Done
- [ ] Pending
- [/] In progress
- [-] Cancelled
- [>] Deferred

~~cancelled item~~

Term
:   Definition
```

## TUI Rendering Pipeline

```
Input HTML
  → Charset auto-detect (from <meta> tag)
  → Outlook MsoNormal paragraph merge
  → html2text --colour (Rust binary, 120 cols)
  → ANSI color remap:
      bold yellow (38;5;11) → purple (35)
      # headers → bold blue (1;34) / cyan (1;36)
      forwarded headers (From/Sent/To/Cc) → dim gray (90)
      Original/Forwarded separators → dim gray (90)
  → Teams/Zoom boilerplate strip
  → Blank line collapse
  → stdout
```

Colors use standard ANSI 16 codes, mapped through kitty's Tokyo Night Storm theme.

## How Draft Works

1. `mail-parser-reply` separates your reply from quoted content
2. Obsidian callouts (`> [!type]`) → styled HTML divs
3. Obsidian checkboxes (`[/]` → ◐, `[-]` → ―, `[>]` → ▷)
4. Markdown → HTML via `pymdown-extensions` (tables, tasklist, tilde, fenced_code, def_list)
5. Reply detection: `In-Reply-To` → `References` (last entry) → new message fallback
6. Original message fetched via `notmuch search --output=files`
7. Inline images → CID attachments (multipart/related)
8. HTML reply embedded into original email's HTML structure
9. `mutt_cmd` generated for neomutt to attach HTML as MIME alternative

## Development

```bash
uv tool install -e . --force    # Install editable
ruff check src/                  # Lint
ruff format src/                 # Format
uv run --with pytest pytest tests/ -v  # Test (27 tests)
```

## Credits

- [mu4e-mimelook](https://github.com/tausen/mu4e-mimelook) — Original inspiration
- [Konfekt/mutt-trim](https://github.com/Konfekt/mutt-trim) — Original Perl trimming logic
- [html2text](https://crates.io/crates/html2text) — Rust crate for HTML→ANSI terminal rendering
