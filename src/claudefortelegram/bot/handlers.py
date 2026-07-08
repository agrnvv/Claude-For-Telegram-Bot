# Telegram command/message handlers:
# - /start, /reset (clear this chat's history), /model (switch model)
# - on_message: the main flow -> load history, call claude.client, stream reply, save turn
