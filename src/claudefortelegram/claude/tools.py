# Defines the "remember" custom tool schema (e.g. save_memory: {content: string})
# that Claude calls when the user asks it to remember something, plus the
# dispatch function the bot runs when that tool_use block comes back — writes
# to memory/store.py and returns a tool_result confirming what was saved.

from claudefortelegram.memory import postgres_store

SAVE_MEMORY_TOOL = {
    "name": "save_memory",
    "description": (
        "Save a fact about the user for future conversations. Call this ONLY when "
        "the user explicitly asks you to remember, save, or note something — not for "
        "facts that just come up in casual conversation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The fact to remember, written as a standalone statement.",
            },
        },
        "required": ["content"],
    },
}


async def handle_save_memory(chat_id: int, tool_input: dict) -> str:
    """Runs when Claude emits a save_memory tool_use block. Returns the tool_result text."""
    content = tool_input["content"]
    await postgres_store.save_memory(chat_id, content)
    return f"Saved: {content}"
