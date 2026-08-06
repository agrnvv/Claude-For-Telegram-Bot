# Postgres-backed token usage log. One row per user-facing reply (not per
# tool-loop iteration) — lets /usage and future cost dashboards show real
# spend instead of the guesswork that let the original 900k-token incident
# go unnoticed for two days. Reuses the shared pool from memory/postgres_store.py.
from datetime import datetime, timedelta, timezone

from claudefortelegram.memory import postgres_store

DEFAULT_SUMMARY_WINDOW_DAYS = 7


async def record_usage(
    chat_id: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int,
    cache_creation_input_tokens: int,
    iterations: int,
    web_search_used: bool,
) -> None:
    """Record one row for a completed reply. Token counts are totals summed
    across every pass of the tool loop that made up this reply, not just the
    final pass."""
    pool = postgres_store.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO usage_log "
            "(chat_id, model, input_tokens, output_tokens, "
            " cache_read_input_tokens, cache_creation_input_tokens, "
            " tool_iterations, web_search_used) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            chat_id,
            model,
            input_tokens,
            output_tokens,
            cache_read_input_tokens,
            cache_creation_input_tokens,
            iterations,
            web_search_used,
        )


async def get_usage_summary(chat_id: int, days: int = DEFAULT_SUMMARY_WINDOW_DAYS) -> dict:
    """Aggregate token usage for this chat over the last `days` days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pool = postgres_store.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT "
            "  COUNT(*) AS replies, "
            "  COALESCE(SUM(input_tokens), 0) AS input_tokens, "
            "  COALESCE(SUM(output_tokens), 0) AS output_tokens, "
            "  COALESCE(SUM(cache_read_input_tokens), 0) AS cache_read_input_tokens, "
            "  COALESCE(SUM(cache_creation_input_tokens), 0) AS cache_creation_input_tokens, "
            "  COALESCE(SUM(CASE WHEN web_search_used THEN 1 ELSE 0 END), 0) AS web_searches "
            "FROM usage_log WHERE chat_id = $1 AND created_at >= $2",
            chat_id,
            since,
        )
    return dict(row)
