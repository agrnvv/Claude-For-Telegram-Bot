# Telegram command/message handlers:
# - /start, /model (switch model), /memories (list saved facts), /forget <id>
# - on_message: load short-term context from conversation/session.py, load
#   long-term memories from memory/store.py, call claude/client.py (streaming +
#   tool loop), edit the Telegram message as deltas arrive, then append the
#   turn to the in-memory session only (never to Postgres).
