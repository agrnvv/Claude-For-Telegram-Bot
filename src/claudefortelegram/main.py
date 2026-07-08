#importing the necessary modules
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from claudefortelegram.config import settings
from claudefortelegram.claude.client import get_reply
#defining the echo function
async def handlemessage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = await get_reply(update.message.text)
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