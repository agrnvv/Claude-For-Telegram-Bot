# Postgres-backed group allowlist. A group chat only becomes "active" when
# an allowed user (ALLOWED_USER_IDS) adds the bot to it — see the
# my_chat_member handler in main.py, which is the only place add_allowed_chat
# is called. Reuses the shared pool from memory/postgres_store.py.
from claudefortelegram.memory import postgres_store


async def is_chat_allowed(chat_id: int) -> bool:
    pool = postgres_store.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM allowed_chats WHERE chat_id = $1", chat_id)
    return row is not None


async def add_allowed_chat(chat_id: int, added_by: int) -> None:
    pool = postgres_store.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO allowed_chats (chat_id, added_by) VALUES ($1, $2) "
            "ON CONFLICT (chat_id) DO NOTHING",
            chat_id,
            added_by,
        )
