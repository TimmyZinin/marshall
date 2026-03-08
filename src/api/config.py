import json
import os

_DB_HOST = os.getenv("DB_HOST", "localhost")
_DB_PORT = os.getenv("DB_PORT", "5432")
_DB_NAME = os.getenv("DB_NAME", "marshall")
_DB_USER = os.getenv("DB_USER", "marshall")
_DB_PASS = os.getenv("DB_PASS", "changeme")
_DEFAULT_DSN = "://".join(["postgresql", f"{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"])
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DSN)
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Telegram Bot API
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_ALLOWED_CHATS = [int(x) for x in os.getenv("TG_ALLOWED_CHATS", "").split(",") if x.strip()]

# Telegram MTProto (for DM listening)
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
# JSON array of dispatcher sessions: [{"session_string": "...", "dispatcher_name": "Диспетчер 1"}]
TG_DISPATCHER_SESSIONS = os.getenv("TG_DISPATCHER_SESSIONS", "")
MTPROTO_LISTEN_GROUPS = os.getenv("MTPROTO_LISTEN_GROUPS", "false").lower() == "true"

# LLM API keys
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# STT (Speech-to-Text) — uses GROQ_API_KEY for Whisper API (free tier)
STT_ENABLED = os.getenv("STT_ENABLED", "true").lower() == "true"


def parse_dispatcher_sessions() -> list[dict]:
    """Parse TG_DISPATCHER_SESSIONS from env (JSON array)."""
    raw = TG_DISPATCHER_SESSIONS.strip()
    if not raw:
        return []
    try:
        sessions = json.loads(raw)
        if isinstance(sessions, list):
            return sessions
    except json.JSONDecodeError:
        pass
    return []
