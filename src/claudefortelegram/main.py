# Entrypoint. Wires together: config -> Postgres pool (memory/postgres_store.py,
# applies db/schema.sql if needed) -> in-memory session store -> Claude client
# -> Telegram bot, then starts long polling. Run with: python -m claudefortelegram.main
# On Railway this is the process started by the start command in railway.json.
