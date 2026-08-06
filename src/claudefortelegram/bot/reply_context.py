# Builds the "[Replying to X: "..."]" prefix injected ahead of a user's
# message when it's a Telegram reply. Telegram hands us the full replied-to
# message (author + text) via update.message.reply_to_message regardless of
# whether it's still in our own MAX_SESSION_MESSAGES window, so this works
# even for a reply to something long since evicted from session history.
# Shared between private chats (main.py) and group mention-handling, since
# both need the same quoting behavior.

QUOTE_MAX_CHARS = 200


def build_reply_prefix(reply_to_message, bot_id: int) -> str:
    """Returns a quoted-context prefix (ending in a newline) to prepend to the
    new message's text, or "" if there's nothing to quote (not a reply, or
    the replied-to message has no text — e.g. a photo/sticker)."""
    if reply_to_message is None:
        return ""

    quoted_text = reply_to_message.text or reply_to_message.caption
    if not quoted_text:
        return ""

    if len(quoted_text) > QUOTE_MAX_CHARS:
        quoted_text = quoted_text[:QUOTE_MAX_CHARS] + "…"

    sender = reply_to_message.from_user
    if sender is not None and sender.id == bot_id:
        label = "the assistant"
    elif sender is not None:
        label = sender.first_name or sender.username or "someone"
    else:
        label = "someone"

    return f'[Replying to {label}: "{quoted_text}"]\n'
