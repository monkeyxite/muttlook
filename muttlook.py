#!/usr/bin/env python3
"""This is a extra tool for mutt to reply outlook html mail with markdown power.

Extra depencies and usage refer to Readme.md.
"""

import base64
import html
import os
import re
import subprocess
import sys
import magic  # python-magic (for mimetypes)
import mailparser  # mail-parser
import markdown  # Markdown
from mailparser_reply import EmailReplyParser
import logging
import logging.handlers
import shortuuid
import shutil
import click

# due to some reason could not source mutt.cmd
muttlook_temp_folder = "/tmp/muttlook/"
commandsFile = "/tmp/muttlook/mutt_cmd"
markdownFile = "/tmp/muttlook/mimelook-md"
# orgMsg is generated everything when starting drafting reply via mutt-trim, configed via $editor in mutt  # noqa: E501
orgMsg = "/tmp/muttlook/original.msg"
htmlFile = "/tmp/muttlook/mimelook.html"
logFile = "/tmp/muttlook/mimelog.log"
newMailHTMLTemplate = "~/.pandoc/templates/email.html"
# TODO: add Swedish and Chinese later
languages = ["en", "de"]



# Configure the logging system
logging.basicConfig(
    level=logging.INFO,  # Set the desired log level (INFO, WARNING, ERROR, etc.)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Define the log message format
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=logFile,  # Specify the log file path
    filemode="w"  # 'w' for write mode, 'a' for append mode (optional, default is 'a')
    # Define the timestamp format
)

QUOTE_ESCAPE = "MIMELOOK_QUOTES"
mime = magic.Magic(mime=True)


def export_inline_attachments(message, dstdir):
    """Export the inlime attachement in the mail to reply into target dir."""
    # find inline attachments in plaintext version
    # inlines = re.findall("\[cid:.*?\]", message.body.split("--- mail_boundary ---")[0])
    # TODO: better match test like html detect part
    try:
        message_html = message.body.split("--- mail_boundary ---")[1]
    except IndexError as e:
        logging.error(f"org message does not have mail_boundary: {e} :( )\n")
        message_html = message.body
    else:
        logging.info("org message has mail_boundary :) \n")
    # .. or html version (probably safer?):
    inlines = re.findall('src="cid:.*?"', message_html)

    # return list of tuples: (attachment id, exported file)
    ret = []

    for inline in inlines:
        # find filename
        name_match = re.search("cid:.*@", inline)

        # find content id
        id_match = re.search("@.*", inline)
        attachment_id = inline[id_match.start() + 1 : -1] if id_match else inline.replace('"','').replace('src=cid:', '')

        # find corresponding attachment in the message
        attachment_name = inline[name_match.start() + 4 : name_match.end() - 1] if name_match else inline[9:-1]
        attachment = [
            x
            for x in message.attachments
            # if x["content-id"].startswith(f"<{attachment_name}@{attachment_id}")
            if x["content-id"].find(f"{attachment_id}".replace("cid:",""))!=-1
        ]
        # assert len(attachment) >= 1, f"Could not find {attachment_id}: {attachment_name}"
        if len(attachment)>=1:
            attachment = attachment[0]
        else:
            logging.error(f"{attachment_id} is not found in msg.attachements")
            break

        # base64 decode the file and place it in dstdir
        assert (
            attachment["content_transfer_encoding"] == "base64"
        ), "Only base64 currently supported"

        dstfile = os.path.join(dstdir, attachment_name)
        while os.path.exists(dstfile):
            base, ext = os.path.splitext(dstfile)
            dstfile = f"{base}_extra{ext}"

        b = base64.decodebytes(bytes(attachment["payload"], "ascii"))
        with open(dstfile, "wb") as f:
            f.write(b)

        # same attachment might occur multiple times - only add it once
        att = (f'{attachment_name}@{attachment_id}', dstfile)
        if att not in ret:
            ret.append(att)

    return ret


# make "from: x, sent: d/m-y, to: z, ..." section in outlook style
# grabbed from what outlook webmail does
def format_insane_outlook_header(fromaddr, sent, to, cc, subject):
    """Format outlook head."""
    ret = """<hr style="display:inline-block;width:98%" tabindex="-1">
<div id="divRplyFwdMsg" dir="ltr"><font face="Calibri, sans-serif" style="font-size:11pt" color="#000000"><b>From:</b> {}<br>
<b>Sent:</b> {}<br>
""".format(
        fromaddr, sent
    )

    if to is not None:
        ret += f"<b>To:</b> {to}<br>\n"

    if cc is not None:
        ret += f"<b>Cc:</b> {cc}<br>\n"

    ret += f"""<b>Subject:</b> {subject}</font>
<div>&nbsp;</div>
</div>
"""

    return ret


# get message_from_pipemsg
def message_from_pipe(pipe):
    """Get message from pipe."""
    message = mailparser.parse_from_string(pipe)
    return message


# get message from id
def message_from_msgid(msgid):
    """Get message from msgid."""
    # mucmd = "mu find msgid:{} --fields 'l'".format(msgid)
    # using notmuch
    nm_cmd = f"notmuch search --output=files id:{msgid}"
    p = subprocess.Popen(nm_cmd.split(" "), stdout=subprocess.PIPE)
    messagefiles, _ = p.communicate()
    messagefiles = messagefiles.decode("utf-8").strip().split("\n")

    # check return code ok
    assert p.returncode == 0, "notmuch find failed"

    # expecting list of at least 1 message and one empty line
    assert len(messagefiles) > 1, "notmuch found no messages"

    # use first hit and strip surrounding -> using the last matching due to 1st has duplicated email folder...
    logging.info(f"Notmuch search results are: { messagefiles }")
    messagefile = messagefiles[-1]

    # parse message and grab HTML
    message = mailparser.parse_from_file(messagefile)

    return message


def format_outlook_reply(message, htmltoinsert):
    """Create crazy outlook-style html reply from message id and the desired html message.""" 
    # Restruct find html part via mail boundary
    pattern = r"--- mail_boundary ---"
    substrings = re.split(pattern, message.body, flags=re.IGNORECASE)
    if len(substrings) == 1:
        logging.info("org message does not have mail_boundary! ")
        message_html = message.body
    for _, substring in enumerate(
        substrings[1:], 1
    ):  # Skip the first element (before the first match)
        m = re.search("<body.*?>", substring)
        if m is not None:
            message_html = substring.strip()
            break
    else:
        message_html = substrings[-1].strip()
    # convert CRLF to LF
    message_html = message_html.replace("\r\n", "\n")

    # grab header info
    message_from = message.headers["From"]
    message_to = message.headers["To"] if "To" in message.headers else None
    message_subject = message.headers["Subject"]
    message_date = message.date.strftime("%d %B %Y %H:%M:%S")
    message_cc = message.headers["CC"] if "CC" in message.headers else None

    outlook_madness = format_insane_outlook_header(
        message_from, message_date, message_to, message_cc, message_subject
    )

    # find body tag in html
    m = re.search("<body.*?>", message_html)
    assert m is not None, "No body tag found in parent HTML"

    # format resulting html email:
    # ..<body> from email being replied to
    # reply message
    # "from yada yada" section
    # remainder of email being replied to
    html = "{}\n{}\n{}\n{}".format(
        message_html[: m.end()], htmltoinsert, outlook_madness, message_html[m.end() :]
    )

    return html


def escape_quotes(plaintext):
    """Convert "> "-style quotes into something else that passes untouched through html.escape().

    Escaped quotes look like this: [[MIMELOOK_QUOTES|X]] where X denotes the
    number of quotes that have been escaped.
    """
    ret = ""
    for line in plaintext.split("\n"):
        if line.startswith(">"):
            i = 0
            while i < len(line) and line[i] == ">":
                i += 1
            ret += f"[[{QUOTE_ESCAPE}|{i}]]"
            ret += line[i:] + "\n"
        else:
            ret += line + "\n"

    return ret


def unescape_quotes(string):
    """Convert previously escaped "> "-style quotes back to their original form.""" 
    retstr = ""
    i = 0

    while i < len(string):
        # find start position of next escaped quote group
        p = string[i:].find(f"[[{QUOTE_ESCAPE}|")

        if p < 0:
            # no more escaped quotes - grab the rest of the string and return
            retstr += string[i:]
            break

        # found some escaped quotes, grab content of string upto them
        retstr += string[i : i + p]

        # find end of the escaped quote tag
        tag_end_pos = string[i + p :].find("]]")

        # grab the number from the tag
        nquotes = int(string[i + p + 2 + len(QUOTE_ESCAPE) + 1 : i + p + tag_end_pos])

        # append that number of quotes
        retstr += ">" * nquotes

        # advance to the character just after the tag
        i += p + tag_end_pos + 2

    return retstr


def escape_signature_linebreaks(plaintext):
    """Escape signature linebreaks."""
    m = re.search("^-- ", plaintext, re.MULTILINE)
    if m is not None:
        content = plaintext[: m.start()]
        signature = plaintext[m.start() :]
        signature = signature.replace("\n", "  \n")
        return content + signature
    else:
        return plaintext


def find_mime_parts(plaintext):
    """Find MIME parts in the plaintext.

    Returns plaintext without parts and list of parts
    Warning: assumes only valid <#part...><#/part> tags after the first occurence of "<#part" !
    """
    parts = re.findall("<#part.*?<#/part>", plaintext, re.DOTALL)
    m = re.search("<#part.*?<#/part>", plaintext, re.DOTALL)
    if m is not None:
        text = plaintext[: m.start()]
    else:
        text = plaintext
    return text, parts


def html_escape(text):
    """Escape HTML.

    Don't escape lines that start with four spaces, since
    these will be wrapped by <pre> tags by the Markdown-to-html
    conversion.
    """
    ret = ""
    for line in text.split("\n"):
        if not line.startswith("    "):
            ret += html.escape(line) + "\n"
        else:
            ret += line + "\n"

    return ret


def plain2fancy(msg):
    """Format plaintext to outlook-style reply.

    Take desired plaintext message and id of message being replied to and format a multipart message with sane plaintext section and
    insane outlook-style html section. The plaintext message is converted
    to HTML supporting markdown syntax.
    """
    reply = EmailReplyParser(languages=languages).read(text=msg)
    latest_reply = reply.latest_reply
    if latest_reply is not None:
        # plaintext is converted to html, supporting markdown syntax
        # loosely inspired by http://webcache.googleusercontent.com/search?q=cache:R1RQkhWqwEgJ:tess.oconnor.cx/2008/01/html-email-composition-in-emacs
        text2html = markdown.markdown(latest_reply)
    else:
        latest_reply = ""
        text2html = ""

    # Q&D way to get msg_id of the orignal msg to reply,  refer orgMsg def
    org_reply_msg = mailparser.parse_from_file(orgMsg)

    if "In-Reply-To" in org_reply_msg.headers.keys():
        reply_to_id = org_reply_msg.headers["In-Reply-To"][1:-1]
        message = message_from_msgid(reply_to_id)
        # insane outlook-style html reply
        madness = format_outlook_reply(message, text2html)
        # logging.info("formated message:\n{}\n".format(madness))

        # find inline attachments and export them to a temporary dir
        if not os.path.isdir(attdir):
            os.mkdir(attdir)
        # attachments from mail to be replied
        attachments = export_inline_attachments(message, attdir) 
    else:
        reply_to_id = "Message-Radom-ID"
        madness = ''
        pandoc_command = [
                "pandoc",
                "-f", "markdown",
                "-t", "html5", "--standalone",
                "--template", newMailHTMLTemplate
                ]
        try:
            # Run the pandoc command and pass the markdown content as input
            #pandoc -f markdown -t html5 --standalone --template ~/.pandoc/templates/email.html "$markdownFile" > "$htmlFile"
            madness = subprocess.run(pandoc_command, input=latest_reply, capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Error generating HTML: {e}")
        attachments = []

    # Find inline attachment in reply and change md
    # re: !\[([^]]*)\]\(([^)]+)\)
    # logging.info("reply text after htmlize is: {}\n".format(text2html))
    link_pattern = r"!\[.*?\]\((.*?)\)"
    matches = re.findall(link_pattern, latest_reply)
    # Replace in-line links with CID attachments and modify original links
    cid_mapping = {}
    new_reply = latest_reply

    for link in matches:
        filename = os.path.basename(link).replace(" ","_")
        destination_path = os.path.join(attdir, filename)
        try:
            os.makedirs(attdir, exist_ok=True)
            shutil.copy(link, destination_path)
            logging.info(f"File copied to: {destination_path}")
        except Exception as e:
            logging.error(f"Error copying file: {e}")
        # Generate cid acc to Outlook style: filename@uuid
        cid = f"{filename}@{shortuuid.uuid(name=filename)}"
        # FIX attach the destination link not orignal link!
        cid_mapping[cid] = destination_path
        new_reply = new_reply.replace(link, f"cid:{cid}")
        # TODO: Seems gmail OK but outlook could not render the inline by using this way, need to fix
        madness = madness.replace(link, f"cid:{cid}") 

    if matches:
        new_msg = msg.replace(latest_reply, new_reply) 
        logging.info(f"matches:\n{type(attachments)}\n")
        attachments +=  list(cid_mapping.items()) if attachments else cid_mapping.items()
        logging.info(f"matches:\n{str(attachments)}\n")
    else:
        new_msg = msg

    logging.info(f"Final attachments:\n{str(attachments)}\n")

    # build string of <#part type=x filename=y disposition=inline><#/part> for each
    # attachment, separated by newlines
    attachment_str = ""
    if attachments:
        for attachment in attachments:
            attachment_str += "<attach-file>'{}'<enter><toggle-disposition><edit-content-id>^u'{}'<enter><tag-entry>".format(
                attachment[1], attachment[0]
            )
    # write html message to file for inspection before sending
    with open(htmlFile, "w") as f:
        f.write(madness)

    with open(markdownFile, "w") as f:
        f.write(new_msg)

    if attachment_str:
        mutt_cmd = "push <attach-file>'{}'<enter><toggle-disposition><toggle-unlink><first-entry><detach-file><attach-file>'{}'<enter><toggle-disposition><toggle-unlink><tag-entry><previous-entry><tag-entry><group-alternatives>{}<first-entry><tag-entry><group-related>".format(
            markdownFile, htmlFile, attachment_str
        )
    else:
        mutt_cmd = "push <attach-file>'{}'<enter><toggle-disposition><toggle-unlink><tag-entry><previous-entry><tag-entry><group-alternatives>".format(
            htmlFile
        )
    with open(commandsFile, "w") as f:
        f.write(mutt_cmd)
    # return madness

def send_hook_cleaner(path):
    """Clean the temp files by called by send hook."""
    muttlook_temp_folder = path
    for root, dirs, files in os.walk(muttlook_temp_folder, topdown=False):
        for file in files :
            file_path = os.path.join(root, file)
            # keep log
            if ".log" not in file and "_cmd" not in file and "original" not in file:
                os.remove(file_path)
            logging.info (f"Deleted file: {file_path}")
        
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            shutil.rmtree(dir_path)
            logging.info(f"Deleted folder: {dir_path}")


@click.command()
@click.option("--action", type=click.Choice(["clean", "draft"]), help="Specify the action to perform.", required=True)
def main(action):
    """Wrap with click to have both draft and clean func."""
    if action == "clean":
        send_hook_cleaner(muttlook_temp_folder)
    elif action == "draft":
        stdin = sys.stdin.read()
        msg = stdin
        plain2fancy(msg)

if __name__ == "__main__":
    # stdin from pipe-message is full drafted msg
    # TODO: let mutt do the hook action, org message is kept...
    send_hook_cleaner(muttlook_temp_folder)

    try:
        main()
    except Exception as e:
        # logging.info("final message:\n{}\n".format(e))
        raise e
