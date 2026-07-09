# Helpers to convert Claude's Markdown output into Telegram-safe MarkdownV2/HTML,
# and to split messages longer than Telegram's 4096-character limit into chunks.

import re

TELEGRAM_MAX_LENGTH = 4096


def markdown_to_telegram_html(text: str) -> str:
    """Escape HTML special chars, then convert a few common Markdown patterns
    (fenced code, inline code, bold) into the HTML tags Telegram's
    parse_mode="HTML" understands. Not a full Markdown parser — good enough
    for typical Claude output, not bulletproof for deeply nested formatting.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = re.sub(r"```(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    return text


def split_message(text: str, limit: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split text into chunks Telegram will accept, breaking on the last
    newline before the limit when possible instead of mid-word."""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)
    return chunks
