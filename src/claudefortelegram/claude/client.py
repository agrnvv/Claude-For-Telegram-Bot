# Thin wrapper around the Anthropic SDK. Builds the request (model, system prompt
# with injected long-term memories, short-term session history, the "remember" tool
# from claude/tools.py) and drives the tool-use loop: streams text deltas back to
# the caller for incremental Telegram edits, and on a save_memory tool_use block,
# dispatches to claude/tools.py before continuing the stream.
