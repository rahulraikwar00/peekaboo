"""Storage facade: selects the active backend and exposes a stable module-level API.

Backend selection (see server.settings.storage_backend):
- If a Supabase client is configured -> SupabaseStorage (hosted).
- Else if STORAGE_BACKEND=sqlite (explicit) -> SqliteStorage (self-host).
- Else -> MemoryStorage (tests / in-memory local mode).

The backend is resolved per-call so tests can swap ``server.main.supabase`` between
requests. The SQLite instance (self-host only) is cached since it isn't swapped at runtime.
"""

from server import settings
from server.config import get_supabase_client
from server.services.memory_storage import MemoryStorage
from server.services.sqlite_storage import SqliteStorage
from server.services.supabase_storage import SupabaseStorage

_sqlite_instance = None


def get_storage():
    global _sqlite_instance
    client = get_supabase_client()
    if client is not None:
        return SupabaseStorage(client)
    if settings.storage_backend() == "sqlite":
        if _sqlite_instance is None:
            _sqlite_instance = SqliteStorage(settings.sqlite_url())
        return _sqlite_instance
    return MemoryStorage()


def reset_storage():
    """Force re-selection of the backend (used by tests)."""
    global _sqlite_instance
    _sqlite_instance = None


# --- owner api keys ---
def get_owner_id_from_api_key(api_key):
    if not api_key:
        return None
    from server.services.security import hash_token
    return get_storage().owner_id_from_api_key(hash_token(api_key))


def insert_owner_api_key(owner_id, key_hash):
    return get_storage().insert_owner_api_key(owner_id, key_hash)


def revoke_owner_api_key(key_hash):
    return get_storage().revoke_owner_api_key(key_hash)


# --- sites ---
def site_exists(site_id):
    return get_storage().site_exists(site_id)


def get_site(site_id):
    return get_storage().get_site(site_id)


def insert_site(site_record):
    return get_storage().insert_site(site_record)


def list_sites(owner_id):
    return get_storage().list_sites(owner_id)


def sites_for_owner(owner_id):
    return get_storage().sites_for_owner(owner_id)


def increment_messages_received(site_id):
    return get_storage().increment_messages_received(site_id)


def increment_replies_sent(site_id):
    return get_storage().increment_replies_sent(site_id)


def get_site_stats(site_id):
    if hasattr(get_storage(), "stats"):
        return get_storage().stats(site_id)
    return {"messages_received": 0, "replies_sent": 0, "last_message_at": None}


# --- integrations ---
def list_integrations(site_id):
    return get_storage().list_integrations(site_id)


def get_integration(site_id, integration_id):
    return get_storage().get_integration(site_id, integration_id)


def find_integration_by_webhook_secret(secret):
    return get_storage().find_integration_by_webhook_secret(secret)


def insert_integration(record) -> str:
    return get_storage().insert_integration(record)


def delete_integration(site_id, integration_id) -> bool:
    return get_storage().delete_integration(site_id, integration_id)


# --- conversations ---
def get_conversation(conversation_id):
    return get_storage().get_conversation(conversation_id)


def get_conversation_by_integration_thread(site_id, integration_id, thread_id):
    return get_storage().get_conversation_by_integration_thread(
        site_id, integration_id, thread_id
    )


def get_or_create_conversation(site_id, visitor_id, integration_id=None):
    return get_storage().get_or_create_conversation(site_id, visitor_id, integration_id)


def update_conversation_integration_ref(conversation_id, integration_id, thread_id):
    return get_storage().update_conversation_integration_ref(
        conversation_id, integration_id, thread_id
    )


def create_conversation(conversation_id, site_id, visitor_id=None):
    return get_storage().create_conversation(conversation_id, site_id, visitor_id)


# --- telegram update dedup ---
def webhook_update_seen(update_id) -> bool:
    return get_storage().webhook_update_seen(update_id)


# --- pending replies ---
def enqueue_reply(conversation_id, reply):
    get_storage().enqueue_reply(conversation_id, reply)


def pending_replies(conversation_id):
    return get_storage().pending_replies(conversation_id)


def delete_pending_reply(reply_id):
    get_storage().delete_pending_reply(reply_id)


def purge_expired_pending_replies(older_than_iso) -> int:
    return get_storage().purge_expired_pending_replies(older_than_iso)


# --- legacy message persistence (no-op: message content is never stored) ---
def save_message(*args, **kwargs):
    # Privacy model: message bodies are never persisted. Forwarded transiently only.
    return None


def update_conversation_visitor(*args, **kwargs):
    return None
