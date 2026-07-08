-- The only table in the database. Holds explicit "remember this" facts only —
-- never raw conversation turns. Applied automatically on startup if missing.
CREATE TABLE IF NOT EXISTS memories (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_chat_id ON memories (chat_id);
