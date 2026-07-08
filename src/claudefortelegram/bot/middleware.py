# Access control: only respond to Telegram user IDs listed in ALLOWED_USER_IDS.
# Also: typing-indicator helper, per-chat rate limiting for message edits during streaming (TODO).

from telegram import Update

from claudefortelegram.config import settings


def is_allowed(update: Update) -> bool:
    """True if the message's sender is in ALLOWED_USER_IDS."""
    user = update.effective_user
    return user is not None and user.id in settings.allowed_user_ids
