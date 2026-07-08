# claudefortelegram

A personal Telegram bot that relays your messages to Claude via the Anthropic API and
replies in the chat. Python, long polling, SQLite for conversation history, Claude
Sonnet 5 by default.

## Project layout

```
claudefortelegram/
├── .env.example                 # copy to .env and fill in secrets/config
├── .gitignore
├── requirements.txt
├── src/claudefortelegram/
│   ├── main.py                  # entrypoint: wires everything together, starts long polling
│   ├── config.py                # loads/validates environment variables
│   ├── bot/
│   │   ├── handlers.py          # /start, /reset, /model, and the main on_message flow
│   │   └── middleware.py        # user allowlist check, typing indicator, edit-rate limiting
│   ├── claude/
│   │   ├── client.py            # Anthropic SDK wrapper — builds request, streams response
│   │   └── prompts.py           # default system prompt (or load from SYSTEM_PROMPT_PATH)
│   ├── history/
│   │   ├── store.py             # storage interface (get/append/reset/trim history)
│   │   └── sqlite_store.py      # SQLite implementation, one row per message
│   └── utils/
│       └── telegram_formatting.py  # Markdown->Telegram formatting, 4096-char message splitting
├── data/                        # data/conversations.sqlite3 created here at runtime (gitignored)
├── tests/
└── scripts/run.sh               # launcher for systemd/pm2/screen
```

## Architecture

### Data flow (one message, end to end)

1. **Telegram → bot process.** `python-telegram-bot` long-polls the Telegram Bot API
   (`getUpdates`) — no public server or HTTPS cert needed. An `Update` arrives for each
   message sent to the bot.
2. **Access control.** `bot/middleware.py` checks the sender's Telegram user ID against
   `ALLOWED_USER_IDS`. Anyone else is ignored — this is a personal bot, not a public one.
3. **Load context.** `bot/handlers.py` calls `history/store.py` to load the recent
   conversation for that `chat_id` from SQLite.
4. **Call Claude.** The message history + new user message go to `claude/client.py`,
   which calls `client.messages.stream(...)` against the Anthropic API with:
   - `model = claude-sonnet-5` (from `CLAUDE_MODEL`)
   - adaptive thinking + `effort` (from `CLAUDE_EFFORT`, default `high`)
   - the system prompt from `claude/prompts.py`
5. **Stream back to Telegram.** Telegram has no token-level streaming API and rate-limits
   `editMessageText` (roughly ~1 edit/second per chat). So the bot sends a placeholder
   message immediately, buffers streamed text deltas, and edits that message every
   ~0.7–1s (or every N characters) until the response is complete — giving a
   "live-typing" feel without hitting rate limits.
6. **Persist the turn.** Once the full reply is generated, both the user message and
   Claude's reply are appended to the SQLite history for that chat.
7. **Formatting & chunking.** `utils/telegram_formatting.py` converts Claude's Markdown
   into Telegram's MarkdownV2/HTML and splits any reply over 4096 characters into
   multiple messages.

### Model selection

Default is **Claude Sonnet 5** (`claude-sonnet-5`) — the best cost/quality balance for a
daily-driver personal assistant, with adaptive thinking and `effort: high`. `/model` can
be added as a command to switch to `claude-opus-4-8` (hardest reasoning tasks) or
`claude-haiku-4-5` (fastest/cheapest) per chat, stored alongside the chat's history.

### Streaming

Handled entirely in `claude/client.py` (Anthropic side, via `messages.stream()`) and
`bot/handlers.py` (Telegram side, via throttled `editMessageText` calls). This is the
one part of the architecture that's inherently a compromise: Claude streams token-by-token,
but Telegram is edit-a-full-message, so the bot buffers and coalesces.

### Conversation history / context management

- **Storage:** SQLite (`data/conversations.sqlite3`), one row per message
  (`chat_id`, `role`, `content`, `created_at`). Simple, zero-ops, fine for single-user or
  small-group use — no separate database server to run.
- **Context window per request:** `history/store.py` returns the last
  `MAX_HISTORY_MESSAGES` (default 40) messages for the chat, not the entire history —
  keeps latency and cost predictable as conversations grow.
- **Reset:** a `/reset` command clears a chat's history when you want a clean slate.
- **Future upgrade path:** for long-running conversations that outgrow a fixed message
  cutoff, Claude's server-side compaction (beta) can replace the fixed-window trim with
  automatic summarization of older turns — a drop-in change in `claude/client.py` and
  `history/store.py`, not a redesign.

### Configuration

Everything environment-driven via `.env` (see `.env.example`): bot token, API key,
allowed user IDs, model name, effort level, history window size, optional custom system
prompt file. Nothing is hardcoded, nothing secret is committed (`.gitignore` excludes
`.env` and the SQLite file).

### Deployment

Long polling means the bot is just a long-running process — no inbound networking,
firewall rules, or TLS cert needed. Run `scripts/run.sh` under `systemd`, `pm2`, `screen`,
or a Docker container with a restart policy, on a Raspberry Pi, a small VPS, or your own
machine.

## Setup (once code is implemented)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS
./scripts/run.sh
```
