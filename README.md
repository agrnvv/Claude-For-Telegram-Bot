# claudefortelegram

A personal Telegram bot that relays your messages to Claude via the Anthropic API and
replies in the chat. Python, long polling, deployed on Railway. Claude Sonnet 5 by
default. Only facts you explicitly ask it to remember are persisted — everything else
lives in memory for the life of the process.

## Project layout

```
claudefortelegram/
├── railway.json                 # Railway build/start/restart config
├── db/schema.sql                 # the ONE table: memories (chat_id, content, created_at)
├── .env.example                  # copy to .env and fill in secrets/config
├── .gitignore
├── requirements.txt
├── src/claudefortelegram/
│   ├── main.py                   # entrypoint: wires everything together, starts long polling
│   ├── config.py                 # loads/validates environment variables
│   ├── bot/
│   │   ├── handlers.py           # /start, /model, /memories, /forget, and the main on_message flow
│   │   └── middleware.py         # user allowlist check, typing indicator, edit-rate limiting
│   ├── claude/
│   │   ├── client.py             # Anthropic SDK wrapper — request building, streaming, tool-use loop
│   │   ├── prompts.py            # system prompt template (injects remembered facts)
│   │   └── tools.py              # the "remember" tool schema + dispatch to memory/store.py
│   ├── memory/                   # LONG-TERM, persisted, explicit-only
│   │   ├── store.py              # interface: get/save/list/forget memories
│   │   └── postgres_store.py     # Postgres implementation (Railway Postgres plugin, asyncpg)
│   ├── conversation/              # SHORT-TERM, ephemeral, never persisted
│   │   └── session.py            # in-process capped history per chat_id, for context only
│   └── utils/
│       └── telegram_formatting.py  # Markdown->Telegram formatting, 4096-char message splitting
├── tests/
└── scripts/run.sh                # local launcher (Railway itself uses railway.json's startCommand)
```

## Architecture

### The core change from the first draft: two-tier memory, not one big log

The earlier version stored the entire conversation transcript in a database. Instead:

- **Short-term context** (`conversation/session.py`) — an in-process, capped list of
  recent messages per chat, kept only so Claude has continuity within a session. It is
  **never written to Postgres** and disappears on restart/redeploy. This is what most of
  a day-to-day chat consists of, and none of it needs to outlive the process.
- **Long-term memory** (`memory/` + Postgres) — a single `memories` table that is written
  to **only** when you explicitly ask Claude to remember something ("remember that I'm
  allergic to peanuts"). This is modeled as a Claude **tool call**, not a heuristic: the
  bot exposes a `save_memory` tool (`claude/tools.py`), and Claude decides when to invoke
  it based on your system prompt instructions. Everything in that table gets loaded back
  in on every request and folded into the system prompt, so Claude always "knows" it —
  but the raw back-and-forth that led to it is not what's stored.

This means: restart the bot and it forgets what you were just talking about (by design),
but it never forgets your birthday once you've told it to remember it.

### Data flow (one message, end to end)

1. **Telegram → bot process.** `python-telegram-bot` long-polls the Telegram Bot API —
   no public server or HTTPS cert needed, which also keeps the Railway deployment simple
   (a worker process, not a web service).
2. **Access control.** `bot/middleware.py` checks the sender's Telegram user ID against
   `ALLOWED_USER_IDS`.
3. **Load context.** `bot/handlers.py` pulls the short-term history for this `chat_id`
   from `conversation/session.py` (in-memory) and the long-term facts from
   `memory/store.py` (Postgres).
4. **Call Claude.** `claude/client.py` calls `client.messages.stream(...)` with:
   - `model = claude-sonnet-5` (from `CLAUDE_MODEL`), adaptive thinking, `effort: high`
   - a system prompt rendered with the loaded long-term facts
   - the `save_memory` tool declared in `claude/tools.py`
5. **Tool loop.** If Claude emits a `save_memory` tool_use block, the handler writes the
   fact to Postgres via `memory/store.py`, returns a `tool_result`, and the stream
   continues — all within the same turn.
6. **Stream back to Telegram.** Telegram has no token-level streaming API and
   rate-limits `editMessageText` (~1 edit/second per chat), so the bot buffers streamed
   text deltas and edits a placeholder message periodically until the reply is complete.
7. **Persist only the session.** The turn is appended to the in-memory session (for
   continuity) — not to Postgres. Only explicit `save_memory` calls touch the database.
8. **Formatting & chunking.** `utils/telegram_formatting.py` converts Markdown to
   Telegram's format and splits replies over 4096 characters.

### Model selection

Default is **Claude Sonnet 5** (`claude-sonnet-5`), adaptive thinking, `effort: high` —
best cost/quality balance for daily personal use. `/model` can switch a chat to
`claude-opus-4-8` (hardest reasoning) or `claude-haiku-4-5` (fastest/cheapest).

### Deployment on Railway

- The bot runs as a **long-running worker** using long polling — no public domain,
  webhook route, or TLS cert needed, which is the simplest thing to run on Railway.
- `railway.json` defines the Nixpacks build and the start command
  (`python -m claudefortelegram.main`), with auto-restart on failure.
- Add Railway's **Postgres plugin** to the project; it injects `DATABASE_URL` into the
  environment automatically — `memory/postgres_store.py` reads it directly, and applies
  `db/schema.sql` on startup if the `memories` table doesn't exist yet.
- Set `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, and `ALLOWED_USER_IDS` as Railway
  environment variables (same names as `.env.example`) — no `.env` file is deployed.

### Configuration

Environment-driven via `.env` locally / Railway variables in production (see
`.env.example`): bot token, API key, allowed user IDs, model, effort, `DATABASE_URL`,
in-memory session cap (`MAX_SESSION_MESSAGES`), idle eviction timeout
(`SESSION_IDLE_TIMEOUT_MINUTES`), optional custom system prompt file.

## Setup (once code is implemented)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS, DATABASE_URL
./scripts/run.sh
```

On Railway: create a project, add the Postgres plugin, set the three secrets above as
variables, and deploy — `railway.json` handles the rest.
