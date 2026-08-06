# Helpers for group-chat message handling: detecting whether the bot was
# @-mentioned, stripping that mention token before the text reaches Claude,
# and picking a display name to attribute a group message to its sender.
import re


def is_mentioned(message, bot_username: str) -> bool:
    """True if the message contains a Telegram "mention" entity matching the
    bot's own @username. Does not match plain substring occurrences of the
    username in prose — only an actual Telegram mention entity counts."""
    if not bot_username or not message.entities or not message.text:
        return False
    needle = f"@{bot_username}".lower()
    for entity in message.entities:
        if entity.type == "mention":
            mention_text = message.text[entity.offset : entity.offset + entity.length]
            if mention_text.lower() == needle:
                return True
    return False


def is_reply_to_bot(message, bot_id: int) -> bool:
    """True if this message is a reply to a message the bot itself sent —
    counts as an implicit mention, same as @-tagging it."""
    target = message.reply_to_message
    return target is not None and target.from_user is not None and target.from_user.id == bot_id


def strip_mention(text: str, bot_username: str) -> str:
    """Remove the "@botusername" token so Claude sees the actual question,
    not its own name. Leaves the rest of the message untouched."""
    if not bot_username or not text:
        return text
    pattern = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
    return pattern.sub("", text).strip()


def display_name(user) -> str:
    """Best-effort human-readable name for attributing a group message —
    first_name is usually set; username is the fallback for the rare account
    that only has one."""
    if user is None:
        return "someone"
    return user.first_name or user.username or "someone"
