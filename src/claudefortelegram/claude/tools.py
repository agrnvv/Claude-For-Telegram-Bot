# Defines the "remember" custom tool schema (e.g. save_memory: {content: string})
# that Claude calls when the user asks it to remember something, plus the
# dispatch function the bot runs when that tool_use block comes back — writes
# to memory/store.py and returns a tool_result confirming what was saved.

from claudefortelegram.memory import postgres_store
from claudefortelegram.google_docs import client as google_docs_client

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


# Anthropic-hosted server tool — Claude runs the search itself, no dispatch
# function needed on our side. Just declaring it is enough to enable it.

# Models that support the dynamic-filtering mode of web_search (it's built on
# programmatic tool calling). Anything else — e.g. Haiku — needs
# allowed_callers=["direct"] or the API rejects the request outright.
MODELS_WITH_DYNAMIC_SEARCH_FILTERING = {
    "claude-opus-4-8",
    "claude-sonnet-5",
}


# Hard cap on searches per turn. This is a personal assistant, not a research
# agent — a question needing more than a handful of searches is rare, and
# capping this directly (rather than just limiting the blast radius after the
# fact via MAX_TOOL_ITERATIONS) cuts the chance of hitting the server's
# internal pause_turn limit, which is what caused the original token-burn
# incident (see plan.md Milestone 8).
WEB_SEARCH_MAX_USES = 3


def web_search_tool_for_model(model: str) -> dict:
    """Build the web_search tool definition, restricted to allowed_callers=["direct"]
    on models that don't support programmatic tool calling."""
    tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}
    if model not in MODELS_WITH_DYNAMIC_SEARCH_FILTERING:
        tool["allowed_callers"] = ["direct"]
    return tool


# Client-side tools for reading/appending a Google Doc, given its share
# link. Only exposed when Google OAuth credentials are configured (see
# google_docs_tools() below) — the feature is fully opt-in and off by
# default, with no effect on anything else when unconfigured.

READ_GOOGLE_DOC_TOOL = {
    "name": "read_google_doc",
    "description": (
        "Read the full text content of a Google Doc, given its share link. Use this "
        "when the user asks you to look at, summarize, or reference a specific Google "
        "Doc they've linked."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The Google Docs URL, e.g. https://docs.google.com/document/d/.../edit.",
            },
        },
        "required": ["url"],
    },
}

APPEND_GOOGLE_DOC_TOOL = {
    "name": "append_to_google_doc",
    "description": (
        "Add text to the end of a Google Doc, given its share link. Appends as a new "
        "paragraph — does not overwrite or replace any existing content. Call this "
        "ONLY when the user explicitly asks you to add, note, or save something into "
        "a specific Google Doc they've linked — not just because a link appears."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The Google Docs URL to append to.",
            },
            "text": {
                "type": "string",
                "description": "The text to add, as a new paragraph at the end of the document.",
            },
        },
        "required": ["url", "text"],
    },
}


async def handle_read_google_doc(_chat_id: int, tool_input: dict) -> str:
    """Runs when Claude emits a read_google_doc tool_use block. `chat_id` is
    unused — kept for a uniform dispatch signature with the other tools."""
    doc_id = google_docs_client.extract_doc_id(tool_input["url"])
    if doc_id is None:
        return "That doesn't look like a valid Google Docs URL."
    try:
        return await google_docs_client.read_doc(doc_id)
    except Exception as e:
        return f"Couldn't read the document: {e}"


async def handle_append_google_doc(_chat_id: int, tool_input: dict) -> str:
    """Runs when Claude emits an append_to_google_doc tool_use block."""
    doc_id = google_docs_client.extract_doc_id(tool_input["url"])
    if doc_id is None:
        return "That doesn't look like a valid Google Docs URL."
    try:
        await google_docs_client.append_to_doc(doc_id, tool_input["text"])
        return "Added to the document."
    except Exception as e:
        return f"Couldn't update the document: {e}"


def google_docs_tools() -> list[dict]:
    if not google_docs_client.is_configured():
        return []
    return [READ_GOOGLE_DOC_TOOL, APPEND_GOOGLE_DOC_TOOL]
