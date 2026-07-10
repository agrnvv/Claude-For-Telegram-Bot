# Postgres-backed implementation of the memory store interface (asyncpg pool,
# DATABASE_URL from Railway's Postgres plugin). Applies db/schema.sql on startup
# if the `memories` table doesn't exist yet. This is the ONLY table in the DB —
# raw conversation turns are never written here, only explicit "remember this" facts.
from pathlib import Path

import asyncpg

from claudefortelegram.config import settings

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent /"db"/"schema.sql"

_pool: asyncpg.Pool | None = None

async def init_pool() -> None:
    """Create the connection pool and apply db/schema.sql. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url)
    async with _pool.acquire() as conn:
        await conn.execute(_SCHEMA_PATH.read_text())
    
# Cap on facts injected into the system prompt on every single request. Without
# this, saving more memories over time makes every future message — even "hi" —
# a little more expensive forever, with no ceiling.
MAX_MEMORIES_IN_PROMPT = 50


async def get_memories(chat_id: int) -> list[str]:
    """Fact strings only — for injecting into the system prompt. Most recent
    MAX_MEMORIES_IN_PROMPT facts, oldest first so they still read naturally."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT content FROM memories WHERE chat_id = $1 "
            "ORDER BY created_at DESC LIMIT $2",
            chat_id,
            MAX_MEMORIES_IN_PROMPT,
        )
    return [row["content"] for row in reversed(rows)]
async def save_memory(chat_id: int, content: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO memories (chat_id, content) VALUES ($1, $2)",
            chat_id, content,
        )

async def list_memories(chat_id: int) -> list[dict]:
    """Full rows (id + content + created_at) â for the /memories command."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, created_at FROM memories WHERE chat_id = $1 ORDER BY created_at",
            chat_id,
        )
    return [dict(row) for row in rows]

async def forget_memory(chat_id: int, memory_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE id = $1 AND chat_id = $2",
            memory_id, chat_id,
        )