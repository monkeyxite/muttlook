# Muttlook

A modern Python tool for mutt to reply to HTML emails (mainly Outlook) with Markdown while preserving original formatting.

## Features

- Reply with Markdown while maintaining original email style
- Support for inline images with automatic CID handling
- Built-in email trimming (replaces old Perl mutt-trim)
- Handles Gmail and Outlook HTML emails
- Modern Python packaging with uv support

## Installation

### Using uv tool (recommended)
```bash
uv tool install -e .
```
This installs `muttlook` and `mutt-trim` as global CLI tools with all dependencies managed by uv.

### Via dotfiles
If using the dotfiles repo, muttlook is auto-installed by `./install` via dotbot.

### Using pip
```bash
pip install -e .
```

## Dependencies

- Python 3.8+
- mailparser (>=3.9.3)
- mail-parser-reply
- markdown (>=3.1.1)
- python-magic (>=0.4.15)
- shortuuid
- click

### System dependencies
- libmagic (macOS: `brew install libmagic`, Ubuntu: `libmagic1`)
- Neomutt with MIME support
- Pandoc (for HTML template processing)

## Usage

### Commands
- `muttlook --action draft` - Process draft email
- `muttlook --action clean` - Clean temporary files
- `mutt-trim <mail_file>` - Trim quoted content from email

### Mutt Configuration

Add to your `.muttrc`:
```
# Use muttlook for HTML replies
set editor = "muttlook --action draft"
send-hook . "muttlook --action clean"

# Use Python mutt-trim instead of Perl version
set display_filter = "mutt-trim"
```

### File Structure
- `~/.cache/muttlook/` - Temporary files and cache
- `~/.pandoc/templates/email.html` - Email template (optional)

## How it Works

1. **Email Trimming**: Removes quoted greetings, signatures, and excessive quote levels
2. **Markdown Processing**: Converts your Markdown reply to HTML
3. **Image Handling**: Automatically converts image links to CID attachments
4. **HTML Integration**: Embeds your reply into the original email structure
5. **Mutt Commands**: Generates appropriate mutt commands for MIME handling

## Configuration

The tool uses these temporary files:
- `original.msg` - Original email for reply context
- `mimelook.html` - Generated HTML content
- `mimelook-md` - Processed Markdown content
- `mutt_cmd` - Generated mutt commands

## Development

```bash
# Install in editable mode
uv tool install -e . --force

# Run linting
ruff check .

# Format code
ruff format .
```

## Credits

- [mu4e-mimelook](https://github.com/tausen/mu4e-mimelook) - Original inspiration
- [Konfekt/mutt-trim](https://github.com/Konfekt/mutt-trim) - Original Perl trimming logic
