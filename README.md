# Muttlook

A modern Python tool for mutt/neomutt to reply to HTML emails (mainly Outlook) with Markdown while preserving original formatting.

## Features

- Reply with Markdown while maintaining original email style
- Supported markdown: headings, bold/italic, tables, code fences, lists, ~~strikethrough~~, checklists (`- [x]`), Obsidian-style callouts (`> [!note]`)
- Support for inline images with automatic CID handling
- Built-in email trimming (replaces old Perl mutt-trim)
- Handles Gmail and Outlook HTML emails
- Notmuch integration for finding original messages
- Modern Python packaging with uv support

## Installation

### Using uv tool (recommended)
```bash
uv tool install -e .
```
This installs `muttlook` and `mutt-trim` as global CLI tools with all dependencies managed by uv.

### Via dotfiles
If using the dotfiles repo, muttlook is auto-installed by `./install` via dotbot.

## Dependencies

### Python dependencies (auto-installed by uv)
- click
- mail-parser (>=3.9.3)
- mail-parser-reply
- markdown (>=3.1.1)
- pymdown-extensions (>=10.0)
- python-magic (>=0.4.15)
- shortuuid

### System dependencies
- libmagic (macOS: `brew install libmagic`, Ubuntu: `libmagic1`)
- Neomutt with MIME support
- Pandoc (for HTML template processing on new messages)
- Notmuch (for finding original messages by Message-ID)

## Usage

### Commands
- `muttlook --action draft` — Process piped email draft, generate HTML reply + mutt commands
- `muttlook --action clean` — Clean temporary files
- `mutt-trim <mail_file>` — Trim quoted content from email

### Neomutt Configuration

In your `muttrc`, use the compose macro to convert markdown reply to HTML:
```muttrc
macro compose ,m "<first-entry>\
<pipe-entry>muttlook --action draft<enter>\
<enter-command>source ~/.cache/muttlook/mutt_cmd<enter>" "reply with md→html"
```

### Neovim Integration

In `ftplugin/mail.lua` or your nvim config:
```lua
vim.keymap.set('n', '<localleader>mm', function()
  vim.cmd('write')
  vim.fn.system('cat ' .. vim.fn.expand('%') .. ' | muttlook --action draft')
  vim.cmd('terminal neomutt -H ' .. vim.fn.expand('%'))
end, { buffer = true, desc = 'Send mail via neomutt' })
```
Then press `,m` in neomutt compose to attach the HTML.

### Markdown in Replies

Write your reply using markdown:
```
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

~~cancelled item~~
```

## How it Works

1. **Reply Parsing**: Uses `mail-parser-reply` to separate your reply from quoted content
2. **Callout Conversion**: Converts Obsidian-style callouts (`> [!type]`) to styled HTML divs
3. **Markdown → HTML**: Converts reply to HTML using Python `markdown` with extensions (tables, tasklist, strikethrough, code fences)
4. **Image Handling**: Automatically converts inline image links to CID attachments
5. **HTML Integration**: Embeds your HTML reply into the original email's HTML structure
6. **Mutt Commands**: Generates `mutt_cmd` file that attaches HTML as MIME alternative

### Temporary Files

All stored in `~/.cache/muttlook/`:
- `original.msg` — Original email for reply context
- `mimelook.html` — Generated HTML content
- `mimelook-md` — Processed Markdown content
- `mutt_cmd` — Generated mutt commands for MIME attachment

## Development

```bash
# Install in editable mode
uv tool install -e . --force

# Run linting
ruff check src/

# Format code
ruff format src/

# Run tests
uvx --with . pytest tests/ -v
```

## Credits

- [mu4e-mimelook](https://github.com/tausen/mu4e-mimelook) — Original inspiration
- [Konfekt/mutt-trim](https://github.com/Konfekt/mutt-trim) — Original Perl trimming logic
