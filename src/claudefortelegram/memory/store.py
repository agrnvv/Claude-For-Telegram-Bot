# Long-term memory interface, backed by Postgres — NOT the conversation transcript.
# get_memories(chat_id) -> facts to inject into the system prompt each request.
# save_memory(chat_id, content) -> called only when the "remember" tool is invoked.
# list_memories(chat_id) / forget_memory(chat_id, memory_id) -> for a /memories, /forget command.
