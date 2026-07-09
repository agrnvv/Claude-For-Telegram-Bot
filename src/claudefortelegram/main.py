#importing the necessary modules
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from claudefortelegram.config import settings
from claudefortelegram.claude.client import get_reply
from claudefortelegram.bot.middleware import is_allowed
from claudefortelegram.conversation import session
#defining the echo function
async def handlemessage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return  # silently ignore anyone not in ALLOWED_USER_IDS
    chat_id = update.effective_chat.id
    session.append(chat_id, "user", update.message.text)

    reply = await get_reply(chat_id, session.get_history(chat_id))

    session.append(chat_id, "assistant", reply)
    await update.message.reply_text(reply)

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