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
