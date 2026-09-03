import os

from dotenv import load_dotenv

load_dotenv()


def storage_backend() -> str:
    """Return the active storage backend: 'supabase' if configured, else 'sqlite'."""
    explicit = (os.getenv("STORAGE_BACKEND") or "").strip().lower()
    if explicit in {"supabase", "sqlite"}:
        return explicit
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        return "supabase"
    return "sqlite"


def storage_forced_supabase() -> bool:
    """True only when the operator explicitly requested Supabase via
    STORAGE_BACKEND=supabase. Used to fail loudly on the server instead of
    silently running in-memory when Supabase credentials are missing."""
    return (os.getenv("STORAGE_BACKEND") or "").strip().lower() == "supabase"


def sqlite_url() -> str:
    return os.getenv("DATABASE_URL") or "peekaboo.db"
