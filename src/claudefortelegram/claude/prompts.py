# Default system prompt template. Takes the list of remembered facts for this
# chat (from memory/store.py) and renders them into a "what you know about this
# user" section, plus instructs Claude to use the save_memory tool whenever the
# user explicitly asks it to remember/note something. Optionally overridden by
# a file at SYSTEM_PROMPT_PATH.

BASE_PROMPT = (
    "You are a helpful personal assistant talking to your owner over Telegram. Try to minimize token usage"
    "Keep replies conversational and concise. "
    "If the user explicitly asks you to remember, save, or note something, call "
    "the save_memory tool to store it — don't just say you'll remember it."
)


GOOGLE_DOCS_ADDENDUM = (
    "\n\nIf the user shares a Google Docs link and explicitly asks you to read or add "
    "something to it, use the read_google_doc / append_to_google_doc tools. Only touch "
    "a doc when explicitly asked — a link appearing in conversation isn't itself a request."
)


def build_system_prompt(memories: list[str], google_docs_enabled: bool = False) -> str:
    prompt = BASE_PROMPT + (GOOGLE_DOCS_ADDENDUM if google_docs_enabled else "")

    if not memories:
        return prompt

    facts = "\n".join(f"- {fact}" for fact in memories)
    return f"{prompt}\n\nWhat you know about this user:\n{facts}"
