#importing the necessary modules
import logging
import time

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from claudefortelegram.config import settings
from claudefortelegram.claude.client import get_reply
from claudefortelegram.bot.middleware import is_allowed
from claudefortelegram.bot.reply_context import build_reply_prefix
from claudefortelegram.bot import allowed_chats_store, group_support
from claudefortelegram.conversation import session
from claudefortelegram.memory import postgres_store
from claudefortelegram.usage import store as usage_store
from claudefortelegram.utils.telegram_formatting import (
    TELEGRAM_MAX_LENGTH,
    markdown_to_telegram_html,
    split_message,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

#defining the /usage command
async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    summary = await usage_store.get_usage_summary(chat_id)
    if summary["replies"] == 0:
        await update.message.reply_text("No usage recorded in the last 7 days.")
        return

    # Total prompt size = input + cache_read + cache_creation (input_tokens
    # alone is only the uncached remainder). Surfacing the hit rate makes a
    # silent caching regression visible instead of just a rising bill.
    prompt_tokens = (
        summary["input_tokens"] + summary["cache_read_input_tokens"] + summary["cache_creation_input_tokens"]
    )
    cache_hit_rate = (summary["cache_read_input_tokens"] / prompt_tokens * 100) if prompt_tokens else 0.0

    await update.message.reply_text(
        "Last 7 days:\n"
        f"Replies: {summary['replies']}\n"
        f"Input tokens: {summary['input_tokens']:,}\n"
        f"Output tokens: {summary['output_tokens']:,}\n"
        f"Cache read: {summary['cache_read_input_tokens']:,}\n"
        f"Cache write: {summary['cache_creation_input_tokens']:,}\n"
        f"Cache hit rate: {cache_hit_rate:.0f}%\n"
        f"Web searches: {summary['web_searches']}"
    )

#defining the /memories command
async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    memories = await postgres_store.list_memories(chat_id)
    if not memories:
        await update.message.reply_text("No memories saved yet.")
        return

    # Positional numbering (1, 2, 3, ...) instead of raw DB ids — otherwise
    # deleting an early memory leaves a gap and the list starts at, say, 2.
    lines = [f"{i}: {m['content']}" for i, m in enumerate(memories, start=1)]
    await update.message.reply_text("\n".join(lines))

#defining the /forget command
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /forget <number> (see /memories for numbers)")
        return

    # The number is a position in the current /memories listing, not the raw
    # DB id — resolve it against a fresh list so it always matches what the
    # user just saw, then delete by the real id underneath.
    position = int(context.args[0])
    memories = await postgres_store.list_memories(chat_id)
    if position < 1 or position > len(memories):
        await update.message.reply_text("No such memory number. Check /memories.")
        return

    memory_id = memories[position - 1]["id"]
    await postgres_store.forget_memory(chat_id, memory_id)
    await update.message.reply_text(f"Forgot memory {position}.")

#defining the /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Commands:\n"
        "/model <sonnet|opus|haiku> — view or switch the model for this chat\n"
        "/memories — list facts saved about you\n"
        "/forget <number> — delete a saved fact (see /memories for numbers)\n"
        "/usage — token usage summary for the last 7 days\n"
        "/help — show this list\n\n"
        "In groups: mention me (@) or reply to one of my messages to get a reply. "
        "I read the whole conversation for context, but only respond when addressed."
    )

#Telegram rejects an edit whose text is byte-identical to what's already
#shown (BadRequest: "Message is not modified") instead of just no-op'ing.
#That's harmless — it means the displayed text is already correct — so
#swallow only that specific error and let anything else propagate normally.
async def safe_edit(message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

#shared streaming logic: runs get_reply, streams the response into Telegram
#message edits, and appends the assistant turn to session history. Used by
#both the private-chat handler and the (triggered) group handler below.
async def _stream_claude_reply(update: Update, chat_id: int, max_messages: int | None = None) -> None:
    placeholder = await update.message.reply_text("…")

    full_reply = ""
    last_edit = time.monotonic()

    async for item in get_reply(chat_id, session.get_history(chat_id)):
        if item["type"] == "status":
            # Rare, meaningful state change (e.g. "searching the web") — show it
            # right away, don't wait for the throttle interval like text deltas.
            await safe_edit(placeholder, item["text"])
            last_edit = time.monotonic()
            continue

        full_reply += item["text"]
        now = time.monotonic()
        # Skip the live-edit once we're past Telegram's limit — Telegram would
        # reject the edit outright. The final flush below handles the overflow
        # properly by splitting into multiple messages.
        if now - last_edit >= EDIT_INTERVAL_SECONDS and len(full_reply) <= TELEGRAM_MAX_LENGTH:
            await safe_edit(placeholder, markdown_to_telegram_html(full_reply), parse_mode="HTML")
            last_edit = now

    chunks = split_message(full_reply)
    await safe_edit(placeholder, markdown_to_telegram_html(chunks[0]), parse_mode="HTML")
    for extra in chunks[1:]:
        await update.message.reply_text(markdown_to_telegram_html(extra), parse_mode="HTML")

    session.append(chat_id, "assistant", full_reply, max_messages=max_messages)

#defining the private-chat message handler
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return  # silently ignore anyone not in ALLOWED_USER_IDS
    chat_id = update.effective_chat.id
    reply_prefix = build_reply_prefix(update.message.reply_to_message, context.bot.id)
    session.append(chat_id, "user", reply_prefix + update.message.text)
    await _stream_claude_reply(update, chat_id)

#defining the group-chat message handler: every message is stored for
#context (with sender attribution), but Claude is only called when the bot
#is @-mentioned or the message replies directly to one of the bot's own
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not await allowed_chats_store.is_chat_allowed(chat_id):
        return  # not an authorized group — my_chat_member_handler should already have left it

    message = update.message
    reply_prefix = build_reply_prefix(message.reply_to_message, context.bot.id)
    triggered = group_support.is_mentioned(message, context.bot.username) or group_support.is_reply_to_bot(
        message, context.bot.id
    )
    # Strip the @mention token so Claude sees the actual question, not its
    # own name — only relevant when this message is what triggers a reply.
    text = group_support.strip_mention(message.text, context.bot.username) if triggered else message.text
    sender = group_support.display_name(message.from_user)

    # Store for every sender regardless of ALLOWED_USER_IDS — this is what
    # lets the bot "understand who wrote what" even for people who can't
    # trigger a reply themselves.
    session.append(
        chat_id,
        "user",
        f"{sender}: {reply_prefix}{text}",
        max_messages=settings.group_max_session_messages,
    )

    if not triggered:
        return  # visible context only — not addressed to the bot

    await _stream_claude_reply(update, chat_id, max_messages=settings.group_max_session_messages)

#runs when the bot's own membership status changes in a chat. Only a user in
#ALLOWED_USER_IDS may add the bot to a group; anyone else's invite is
#declined by leaving immediately, so a group is only ever "live" if an
#owner-approved person put the bot there.
async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.my_chat_member
    if result.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    joined_statuses = (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
    was_member = result.old_chat_member.status in joined_statuses
    is_member = result.new_chat_member.status in joined_statuses
    if was_member or not is_member:
        return  # not a "bot just got added" transition — ignore promotions, kicks, etc.

    chat_id = result.chat.id
    added_by = result.from_user.id
    if added_by in settings.allowed_user_ids:
        await allowed_chats_store.add_allowed_chat(chat_id, added_by)
        logger.info("Joined authorized group chat_id=%s added_by=%s", chat_id, added_by)
    else:
        logger.warning("Leaving unauthorized group chat_id=%s added_by=%s", chat_id, added_by)
        await context.bot.leave_chat(chat_id)

#runs once, after the Application is built but before polling starts —
#the right place to open the DB pool, since it needs a running event loop
async def post_init(application: Application) -> None:
    await postgres_store.init_pool()

#catches any exception raised in any handler above (Anthropic API errors,
#Telegram network errors, Postgres errors, ...) so one bad request just gets
#logged and reported to the user instead of leaving them stuck with no reply
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Something went wrong on my end — try again in a moment."
        )

#defining the main function
def main() -> None:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    #adding the handler for the /model command
    application.add_handler(CommandHandler("model", model_command))
    #adding the handlers for /memories and /forget
    application.add_handler(CommandHandler("memories", memories_command))
    application.add_handler(CommandHandler("forget", forget_command))
    #adding the handler for the /usage command
    application.add_handler(CommandHandler("usage", usage_command))
    #adding the handler for the /help command
    application.add_handler(CommandHandler("help", help_command))
    #adding the handler for private-chat messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_private_message)
    )
    #adding the handler for group-chat messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_message)
    )
    #adding the handler for the bot's own membership changes (added to / removed from a group)
    application.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    #catches exceptions from any of the handlers above
    application.add_error_handler(error_handler)
    #running the polling
    application.run_polling()

#running the main function
if __name__ == "__main__":
    main()