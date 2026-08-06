# Ephemeral, in-process short-term context — NOT persisted to any database.
# A dict keyed by chat_id -> capped deque of recent messages (MAX_SESSION_MESSAGES),
# used only to give Claude conversational continuity within a session. Lost on
# restart/redeploy by design: this is the "don't store everything" half of the
# memory model. Optionally evict chats idle longer than SESSION_IDLE_TIMEOUT
# to bound memory usage on long-running Railway deployments.
from collections import deque
from claudefortelegram.config import settings
# chat_id -> deque of {"role": ..., "content": ...} dicts, capped at
# settings.max_session_messages. Lives only in process memory.
_sessions: dict[int, deque] = {}

def get_history(chat_id: int) -> list[dict]:
    return list(_sessions.get(chat_id, []))

def append(chat_id: int, role: str, content: str, max_messages: int | None = None) -> None:
    # max_messages only takes effect the first time this chat_id is seen —
    # a deque's maxlen is fixed at creation. Callers for a given chat_id
    # should pass a consistent value (private chats: default/omitted; group
    # chats: settings.group_max_session_messages) since a chat's type never
    # changes mid-conversation.
    if chat_id not in _sessions:
        _sessions[chat_id] = deque(maxlen=max_messages or settings.max_session_messages)
    _sessions[chat_id].append({"role": role, "content": content})


# Per-chat model override, set via /model. Separate from _sessions since it's
# a different kind of state (a preference, not conversation history).
_model_overrides: dict[int, str] = {}


def set_model(chat_id: int, model: str) -> None:
    _model_overrides[chat_id] = model


def get_model(chat_id: int) -> str:
    return _model_overrides.get(chat_id, settings.claude_model)