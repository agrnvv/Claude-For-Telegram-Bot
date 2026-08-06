-- The only table in the database. Holds explicit "remember this" facts only —
-- never raw conversation turns. Applied automatically on startup if missing.
CREATE TABLE IF NOT EXISTS memories (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_chat_id ON memories (chat_id);

-- One row per user-facing reply (not per tool-loop iteration). Lets us see
-- real token spend per chat/model instead of guessing, and query cumulative
-- cost over time via /usage instead of grepping logs.
CREATE TABLE IF NOT EXISTS usage_log (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model TEXT NOT NULL,
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    cache_read_input_tokens INT NOT NULL,
    cache_creation_input_tokens INT NOT NULL,
    tool_iterations INT NOT NULL,
    web_search_used BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_log_chat_id_created_at ON usage_log (chat_id, created_at);

-- Groups the bot is allowed to be active in. Only populated when an allowed
-- user (ALLOWED_USER_IDS) adds the bot to a group/supergroup — see the
-- my_chat_member handler in main.py. If a non-allowed user adds the bot, it
-- leaves immediately and no row is ever written here.
CREATE TABLE IF NOT EXISTS allowed_chats (
    chat_id BIGINT PRIMARY KEY,
    added_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
