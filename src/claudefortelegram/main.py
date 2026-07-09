#importing the necessary modules
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from claudefortelegram.config import settings
from claudefortelegram.claude.client import get_reply
from claudefortelegram.bot.middleware import is_allowed
from claudefortelegram.conversation import session
from claudefortelegram.memory import postgres_store
from claudefortelegram.utils.telegram_formatting import (
    TELEGRAM_MAX_LENGTH,
    markdown_to_telegram_html,
    split_message,
)

EDIT_INTERVAL_SECONDS = 1.0

MODEL_ALIASES = {
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-4-8",
    "haiku": "claude-haiku-4-5",
}

#defining the /model command
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    if not context.args:
        current = session.get_model(chat_id)
        await update.message.reply_text(
            f"Current model: {current}\nUsage: /model <sonnet|opus|haiku>"
        )
        return

    choice = context.args[0].lower()
    if choice not in MODEL_ALIASES:
        await update.message.reply_text("Unknown model. Choose from: sonnet, opus, haiku")
        return

    session.set_model(chat_id, MODEL_ALIASES[choice])
    await update.message.reply_text(f"Model set to {MODEL_ALIASES[choice]}")

#defining the /memories command
async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    memories = await postgres_store.list_memories(chat_id)
    if not memories:
        await update.message.reply_text("No memories saved yet.")
        return

    lines = [f"{m['id']}: {m['content']}" for m in memories]
    await update.message.reply_text("\n".join(lines))

#defining the /forget command
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /forget <id> (see /memories for IDs)")
        return

    memory_id = int(context.args[0])
    await postgres_store.forget_memory(chat_id, memory_id)
    await update.message.reply_text(f"Forgot memory {memory_id}.")

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
    #adding the handler for the /model command
    application.add_handler(CommandHandler("model", model_command))
    #adding the handlers for /memories and /forget
    application.add_handler(CommandHandler("memories", memories_command))
    application.add_handler(CommandHandler("forget", forget_command))
    #adding the handler for the message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlemessage))
    #running the polling
    application.run_polling()

#running the main function
if __name__ == "__main__":
    main()