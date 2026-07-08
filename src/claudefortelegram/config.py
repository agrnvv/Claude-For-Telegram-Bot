import os
import dotenv
dotenv.load_dotenv()
"""
Loads and validates settings from environment variables (see .env.example):
TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_USER_IDS, CLAUDE_MODEL,
CLAUDE_EFFORT, DATABASE_URL (injected by Railway's Postgres plugin),
MAX_SESSION_MESSAGES (in-memory context cap), SESSION_IDLE_TIMEOUT_MINUTES,
SYSTEM_PROMPT_PATH.
"""

class Config:
    def __init__(self):
        # Required, no default -> bracket access on os.environ raises
        # KeyError automatically if missing. That's the "fail loudly at
        # startup" behavior we wanted instead of silently getting None.
        self.telegram_bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]
        self.database_url = os.environ["DATABASE_URL"]

        # Required, but also needs parsing: "111,222" -> [111, 222]
        raw_ids = os.environ["ALLOWED_USER_IDS"]
        self.allowed_user_ids = [
            int(uid.strip()) for uid in raw_ids.split(",") if uid.strip()
        ]

        # Optional -> safe to use getenv with a default instead of raising
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
        self.claude_effort = os.getenv("CLAUDE_EFFORT", "high")
        self.system_prompt_path = os.getenv("SYSTEM_PROMPT_PATH", "")

        # Optional, but need to be ints, not strings
        self.max_session_messages = int(os.getenv("MAX_SESSION_MESSAGES") or 20)
        self.session_idle_timeout_minutes = int(
            os.getenv("SESSION_IDLE_TIMEOUT_MINUTES") or 30
        )


# One shared instance the rest of the app imports:
#   from claudefortelegram.config import settings
settings = Config()