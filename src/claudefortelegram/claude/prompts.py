# Default system prompt template. Takes the list of remembered facts for this
# chat (from memory/store.py) and renders them into a "what you know about this
# user" section, plus instructs Claude to use the save_memory tool whenever the
# user explicitly asks it to remember/note something. Optionally overridden by
# a file at SYSTEM_PROMPT_PATH.

BASE_PROMPT = (
    "You are a helpful personal assistant talking to your owner over Telegram. "
    "Keep replies conversational and concise. "
    "If the user explicitly asks you to remember, save, or note something, call "
    "the save_memory tool to store it — don't just say you'll remember it."
)


def build_system_prompt(memories: list[str]) -> str:
    if not memories:
        return BASE_PROMPT

    facts = "\n".join(f"- {fact}" for fact in memories)
    return f"{BASE_PROMPT}\n\nWhat you know about this user:\n{facts}"
