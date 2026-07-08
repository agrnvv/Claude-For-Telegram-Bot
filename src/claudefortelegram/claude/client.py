# Thin wrapper around the Anthropic SDK: builds the request (model, system prompt,
# message history, adaptive thinking/effort), calls client.messages.stream(...),
# and yields text deltas back to the caller for incremental Telegram message edits.
