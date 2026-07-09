#importing the necessary modules
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from claudefortelegram.config import settings
from claudefortelegram.claude.client import get_reply
from claudefortelegram.bot.middleware import is_allowed
from claudefortelegram.conversation import session
from claudefortelegram.utils.telegram_formatting import (
    TELEGRAM_MAX_LENGTH,
    markdown_to_telegram_html,
    split_message,
)

EDIT_INTERVAL_SECONDS = 1.0

#defining the echo function
async def handlemessage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return  # silently ignore anyone not in ALLOWED_USER_IDS
    chat_id = update.effective_chat.id
    session.append(chat_id, "user", update.message.text)

    placeholder = await update.message.reply_text("…")

    full_reply = ""
    last_edit = time.monotonic()

    async for chunk in get_reply(chat_id, session.get_history(chat_id)):
        full_reply += chunk
        now = time.monotonic()
        # Skip the live-edit once we're past Telegram's limit — Telegram would
        # reject the edit outright. The final flush below handles the overflow
        # properly by splitting into multiple messages.
        if now - last_edit >= EDIT_INTERVAL_SECONDS and len(full_reply) <= TELEGRAM_MAX_LENGTH:
            await placeholder.edit_text(markdown_to_telegram_html(full_reply), parse_mode="HTML")
            last_edit = now

    chunks = split_message(full_reply)
    await placeholder.edit_text(markdown_to_telegram_html(chunks[0]), parse_mode="HTML")
    for extra in chunks[1:]:
        await update.message.reply_text(markdown_to_telegram_html(extra), parse_mode="HTML")

    session.append(chat_id, "assistant", full_reply)

#defining the main function
def main() -> None:
    application = Application.builder().token(settings.telegram_bot_token).build()
    #adding the handler for the message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlemessage))
    #running the polling
    application.run_polling()

#running the main function
if __name__ == "__main__":
    main()