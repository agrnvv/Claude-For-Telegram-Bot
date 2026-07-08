# Default system prompt template. Takes the list of remembered facts for this
# chat (from memory/store.py) and renders them into a "what you know about this
# user" section, plus instructs Claude to use the save_memory tool whenever the
# user explicitly asks it to remember/note something. Optionally overridden by
# a file at SYSTEM_PROMPT_PATH.

# the prompt is static at the point and will be improved in second stage of claude for telegram improvement
SYSTEM_PROMPT = (
    "You are a helpful personal assistant talking to your owner over Telegram. "
    "Keep replies conversational and concise."
)