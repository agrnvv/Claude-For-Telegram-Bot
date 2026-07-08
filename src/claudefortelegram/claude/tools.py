# Defines the "remember" custom tool schema (e.g. save_memory: {content: string})
# that Claude calls when the user asks it to remember something, plus the
# dispatch function the bot runs when that tool_use block comes back — writes
# to memory/store.py and returns a tool_result confirming what was saved.
