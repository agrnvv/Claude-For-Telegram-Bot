# Ephemeral, in-process short-term context — NOT persisted to any database.
# A dict keyed by chat_id -> capped deque of recent messages (MAX_SESSION_MESSAGES),
# used only to give Claude conversational continuity within a session. Lost on
# restart/redeploy by design: this is the "don't store everything" half of the
# memory model. Optionally evict chats idle longer than SESSION_IDLE_TIMEOUT
# to bound memory usage on long-running Railway deployments.
