# claudefortelegram

A Telegram bot that relays messages to Claude via the Anthropic API and replies in the
chat. Python, long polling, deployable on Railway in a few minutes. Claude Sonnet 5 by
default. Only facts you explicitly ask it to remember are persisted — everything else
lives in memory for the life of the process.

This is an open-source personal-assistant bot: anyone can clone this repo and deploy
their **own** copy with their **own** bot token and API key (see [License](#license)).
Deploying this repo doesn't give anyone access to *your* bot — each deployment is its
own isolated instance.

## Using the bot in Telegram

**Just chat normally.** Send it any message and it replies via Claude. It remembers
the conversation while the process is running (so follow-up questions work), but that
short-term context is lost on restart — that's by design, see the memory model below.

**To make it remember something long-term, just ask in plain language** — e.g. "remember
that I'm allergic to peanuts" or "note that my flight is on the 14th." There's no special
command for this: Claude itself decides when something you said is worth saving
permanently, and stores it via a tool call. From then on, that fact is loaded back in on
every future conversation, even after a restart.

**Commands:**

| Command | What it does |
| --- | --- |
| `/model` | Shows which model this chat is currently using. |
| `/model sonnet` \| `/model opus` \| `/model haiku` | Switches this chat to Claude Sonnet 5 (default, best balance), Opus 4.8 (hardest reasoning), or Haiku 4.5 (fastest/cheapest). This choice is per-chat and resets on restart. |
| `/memories` | Lists every fact currently saved for this chat, each with a numeric ID. |
| `/forget <id>` | Deletes one saved fact by its ID (get the ID from `/memories` first). |
| `/usage` | Token usage summary (input/output/cache tokens, web searches) for this chat over the last 7 days. |
| `/help` | Lists all commands. |

In a private chat, only messages from Telegram user IDs listed in `ALLOWED_USER_IDS`
get a response — everyone else is silently ignored.

**In a group chat**, the bot only replies when you @-mention it or reply directly to
one of its own messages — otherwise it just reads along, so it has context when it
*is* addressed. It attributes messages to whoever sent them ("Alice: ...") and keeps a
shorter rolling window than in private chats, since groups generate a lot more volume.
A group is only ever active if a user in `ALLOWED_USER_IDS` was the one who added the
bot to it — if anyone else adds it, the bot leaves immediately. Within an authorized
group, anyone can @-mention the bot and get a reply (not just allowlisted users).

Note: group support requires **privacy mode disabled** for your bot — message
[@BotFather](https://t.me/BotFather), `/setprivacy`, pick your bot, choose **Disable**.
Without this, Telegram only forwards @mentions/replies/commands to the bot, not the
rest of the conversation, and it won't have real context to work with.

**Google Docs (optional):** if configured (see [Configuration](#configuration)), ask
the bot to read or add to a Google Doc by pasting the link — e.g. "read this doc:
`<link>` and summarize it" or "add this to `<link>`: ...". Off by default; nothing
else changes if you don't set it up.

## Getting your own bot running

### 1. What you'll need

- **A Telegram bot token** — message [@BotFather](https://t.me/BotFather) on Telegram,
  send `/newbot`, follow the prompts. You'll get a token like `123456:ABC-...`.
- **An Anthropic API key** — create one at the
  [Anthropic Console](https://console.anthropic.com).
- **Your Telegram user ID** — message [@userinfobot](https://t.me/userinfobot), it
  replies with your numeric ID. This goes in `ALLOWED_USER_IDS` so only you (and anyone
  else you add) can use the bot.

### 2. Deploy to Railway (recommended)

1. Fork this repository to your own GitHub account.
2. Go to [railway.app](https://railway.app) and sign in with GitHub.
3. **New Project → Deploy from GitHub repo** → select your fork.
   The first deploy will fail — that's expected, there's no database or config yet.
4. In the project canvas, click **+ New → Database → Add PostgreSQL** to add a Postgres
   service alongside your bot.
5. Click your **bot's** service card → **Variables** tab, and add:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `ALLOWED_USER_IDS`
   - `DATABASE_URL` — Railway usually offers to link this from the Postgres service
     automatically; if not, set it to `${{Postgres.DATABASE_URL}}` (use your Postgres
     service's actual name if it's not called `Postgres`).
6. Redeploy the bot service. Check the **Deployments/Logs** tab — no errors means it's
   running and long-polling Telegram.
7. Message your bot on Telegram. It should reply.

`railway.json` in this repo already defines the build and start command — you don't
need to configure anything else on Railway itself.

### 3. Or run it locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS, DATABASE_URL
./scripts/run.sh
```

Locally you need your own Postgres instance running (e.g. `docker run -p 5432:5432 -e
POSTGRES_PASSWORD=postgres postgres`) and its connection string in `DATABASE_URL`.

## Configuration

Environment-driven via `.env` locally / Railway variables in production (see
`.env.example`): bot token, API key, allowed user IDs, model, effort, `DATABASE_URL`,
in-memory session caps (`MAX_SESSION_MESSAGES` for private chats,
`GROUP_MAX_SESSION_MESSAGES` for groups), idle eviction timeout
(`SESSION_IDLE_TIMEOUT_MINUTES`), optional custom system prompt file, and the optional
Google Docs trio (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN`
— run `scripts/google_oauth_setup.py` once to mint the refresh token; see that script's
docstring for the one-time GCP setup).

## Project layout

```
claudefortelegram/
├── railway.json                 # Railway build/start/restart config
├── db/schema.sql                 # memories, usage_log, allowed_chats tables
├── .env.example                  # copy to .env and fill in secrets/config
├── .gitignore
├── requirements.txt
├── src/claudefortelegram/
│   ├── main.py                   # entrypoint + all command/message handlers, group routing
│   ├── config.py                 # loads/validates environment variables
│   ├── bot/
│   │   ├── middleware.py         # user allowlist check (is_allowed)
│   │   ├── reply_context.py      # builds the "[Replying to X: ...]" quoted-context prefix
│   │   ├── group_support.py      # mention detection, mention stripping, sender display name
│   │   └── allowed_chats_store.py  # which groups the bot is authorized to be active in
│   ├── claude/
│   │   ├── client.py             # Anthropic SDK wrapper — request building, streaming, tool-use loop
│   │   ├── prompts.py            # system prompt template (injects remembered facts)
│   │   └── tools.py              # tool schemas + dispatch: save_memory, Google Docs read/append
│   ├── memory/                   # LONG-TERM, persisted, explicit-only
│   │   ├── store.py              # interface: get/save/list/forget memories
│   │   └── postgres_store.py     # Postgres implementation (Railway Postgres plugin, asyncpg)
│   ├── conversation/              # SHORT-TERM, ephemeral, never persisted
│   │   └── session.py            # in-process capped history per chat_id, for context only
│   ├── usage/
│   │   └── store.py              # per-reply token usage log + /usage summary query
│   ├── google_docs/
│   │   └── client.py             # Docs API read/append over httpx, OAuth refresh-token auth
│   └── utils/
│       └── telegram_formatting.py  # Markdown->Telegram formatting, 4096-char message splitting
├── tests/
└── scripts/
    ├── run.sh                    # local launcher (Railway itself uses railway.json's startCommand)
    └── google_oauth_setup.py     # one-time script to mint GOOGLE_REFRESH_TOKEN
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
3. **Load context.** `main.py` pulls the short-term history for this `chat_id` from
   `conversation/session.py` (in-memory); `claude/client.py` separately loads the
   long-term facts from `memory/postgres_store.py` (Postgres).
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

## License

[MIT](./LICENSE) — do whatever you want with this code, including running your own
copy of the bot. No warranty.
