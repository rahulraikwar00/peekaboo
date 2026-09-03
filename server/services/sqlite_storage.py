import json
import secrets
import sqlite3
import threading

from server.config import (
    CONVERSATION_ID_BYTES,
    INTEGRATION_ID_BYTES,
)
from server.services.base_storage import Storage


def _conn(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
  site_id TEXT PRIMARY KEY,
  owner_id TEXT,
  operator_token_hash TEXT,
  allowed_origins TEXT,
  widget_config TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS owner_api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL,
  revoked_at TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS integrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  destination_id TEXT,
  credentials TEXT NOT NULL,
  webhook_secret TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  config TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  visitor_id TEXT,
  telegram_thread_id TEXT,
  created_at TEXT,
  last_activity_at TEXT
);
CREATE TABLE IF NOT EXISTS site_stats (
  site_id TEXT PRIMARY KEY,
  messages_received INTEGER NOT NULL DEFAULT 0,
  replies_sent INTEGER NOT NULL DEFAULT 0,
  last_message_at TEXT
);
CREATE TABLE IF NOT EXISTS pending_replies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL,
  reply TEXT NOT NULL,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_site ON conversations(site_id);
CREATE INDEX IF NOT EXISTS idx_conversations_thread ON conversations(telegram_thread_id);
CREATE INDEX IF NOT EXISTS idx_conversations_visitor ON conversations(visitor_id);
CREATE INDEX IF NOT EXISTS idx_integrations_site ON integrations(site_id);
CREATE INDEX IF NOT EXISTS idx_pending_replies_conv ON pending_replies(conversation_id);
"""


class SqliteStorage(Storage):
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.Lock()
        with self._lock:
            conn = _conn(db_path)
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    # --- owner api keys ---
    def owner_id_from_api_key(self, key_hash):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT owner_id FROM owner_api_keys "
                    "WHERE key_hash=? AND revoked_at IS NULL LIMIT 1",
                    (key_hash,),
                ).fetchone()
                return row["owner_id"] if row else None
            finally:
                conn.close()

    def insert_owner_api_key(self, owner_id, key_hash):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO owner_api_keys(owner_id, key_hash, created_at) VALUES (?,?,datetime('now'))",
                    (owner_id, key_hash),
                )
                conn.commit()
            finally:
                conn.close()

    def revoke_owner_api_key(self, key_hash) -> bool:
        with self._lock:
            conn = _conn(self.db_path)
            try:
                cur = conn.execute(
                    "UPDATE owner_api_keys SET revoked_at=datetime('now') "
                    "WHERE key_hash=? AND revoked_at IS NULL",
                    (key_hash,),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    # --- sites ---
    def site_exists(self, site_id) -> bool:
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT 1 FROM sites WHERE site_id=?", (site_id,)
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def get_site(self, site_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM sites WHERE site_id=?", (site_id,)
                ).fetchone()
                return self._site_dict(row)
            finally:
                conn.close()

    def insert_site(self, site_record):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                origin = site_record.get("allowed_origin")
                origins = site_record.get("allowed_origins")
                if origins is None and origin:
                    origins = [origin]
                conn.execute(
                    "INSERT INTO sites(site_id, owner_id, operator_token_hash, "
                    "allowed_origins, widget_config, created_at) "
                    "VALUES (?,?,?,?,?,datetime('now'))",
                    (
                        site_record["site_id"],
                        site_record.get("owner_id"),
                        site_record.get("operator_token_hash"),
                        json.dumps(origins) if origins else None,
                        json.dumps(site_record.get("widget_config"))
                        if site_record.get("widget_config")
                        else None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_sites(self, owner_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM sites WHERE owner_id=?", (owner_id,)
                ).fetchall()
                return [self._site_dict(r) for r in rows]
            finally:
                conn.close()

    def sites_for_owner(self, owner_id):
        return self.list_sites(owner_id)

    def increment_messages_received(self, site_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO site_stats(site_id, messages_received, last_message_at) "
                    "VALUES (?,1,datetime('now')) "
                    "ON CONFLICT(site_id) DO UPDATE SET "
                    "messages_received=messages_received+1, last_message_at=datetime('now')",
                    (site_id,),
                )
                conn.commit()
            finally:
                conn.close()

    def stats(self, site_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT messages_received, replies_sent, last_message_at "
                    "FROM site_stats WHERE site_id=?",
                    (site_id,),
                ).fetchone()
                if row:
                    return dict(row)
                return {"messages_received": 0, "replies_sent": 0, "last_message_at": None}
            finally:
                conn.close()

    # --- integrations ---
    def list_integrations(self, site_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM integrations WHERE site_id=?", (site_id,)
                ).fetchall()
                return [self._integration_dict(r) for r in rows]
            finally:
                conn.close()

    def get_integration(self, site_id, integration_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM integrations WHERE site_id=? AND id=?",
                    (site_id, integration_id),
                ).fetchone()
                return self._integration_dict(row) if row else None
            finally:
                conn.close()

    def insert_integration(self, record) -> str:
        with self._lock:
            conn = _conn(self.db_path)
            try:
                cur = conn.execute(
                    "INSERT INTO integrations(site_id, provider, destination_id, "
                    "credentials, webhook_secret, enabled, config, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
                    (
                        record["site_id"],
                        record["provider"],
                        record.get("destination_id"),
                        record["credentials"],
                        record.get("webhook_secret"),
                        1 if record.get("enabled", True) else 0,
                        json.dumps(record.get("config")) if record.get("config") else None,
                    ),
                )
                conn.commit()
                return str(cur.lastrowid)
            finally:
                conn.close()

    def delete_integration(self, site_id, integration_id) -> bool:
        with self._lock:
            conn = _conn(self.db_path)
            try:
                cur = conn.execute(
                    "DELETE FROM integrations WHERE site_id=? AND id=?",
                    (site_id, integration_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    # --- conversations ---
    def get_conversation(self, conversation_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id=?",
                    (conversation_id,),
                ).fetchone()
                return self._conversation_dict(row) if row else None
            finally:
                conn.close()

    def get_conversation_by_thread(self, site_id, thread_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE site_id=? AND telegram_thread_id=?",
                    (site_id, thread_id),
                ).fetchone()
                return self._conversation_dict(row) if row else None
            finally:
                conn.close()

    def get_or_create_conversation(self, site_id, visitor_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE site_id=? AND visitor_id=? "
                    "ORDER BY last_activity_at DESC LIMIT 1",
                    (site_id, visitor_id),
                ).fetchone()
                if row:
                    conv = self._conversation_dict(row)
                    conn.execute(
                        "UPDATE conversations SET last_activity_at=datetime('now') "
                        "WHERE conversation_id=?",
                        (conv["conversation_id"],),
                    )
                    conn.commit()
                    return conv
                conversation_id = "conv_" + secrets.token_urlsafe(CONVERSATION_ID_BYTES)
                conn.execute(
                    "INSERT INTO conversations(conversation_id, site_id, visitor_id, "
                    "created_at, last_activity_at) VALUES (?,?,?,datetime('now'),datetime('now'))",
                    (conversation_id, site_id, visitor_id),
                )
                conn.commit()
                return self._conversation_dict(
                    conn.execute(
                        "SELECT * FROM conversations WHERE conversation_id=?",
                        (conversation_id,),
                    ).fetchone()
                )
            finally:
                conn.close()

    def update_conversation_thread(self, conversation_id, thread_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "UPDATE conversations SET telegram_thread_id=?, last_activity_at=datetime('now') "
                    "WHERE conversation_id=?",
                    (thread_id, conversation_id),
                )
                conn.commit()
            finally:
                conn.close()

    def create_conversation(self, conversation_id, site_id, visitor_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO conversations(conversation_id, site_id, visitor_id, "
                    "created_at, last_activity_at) VALUES (?,?,?,datetime('now'),datetime('now'))",
                    (conversation_id, site_id, visitor_id),
                )
                conn.commit()
                return conversation_id
            finally:
                conn.close()

    # --- pending replies ---
    def enqueue_reply(self, conversation_id, reply):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO pending_replies(conversation_id, reply, created_at) "
                    "VALUES (?,?,datetime('now'))",
                    (conversation_id, reply),
                )
                conn.commit()
            finally:
                conn.close()

    def pending_replies(self, conversation_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT id, reply FROM pending_replies WHERE conversation_id=? "
                    "ORDER BY id",
                    (conversation_id,),
                ).fetchall()
                return [{"id": r["id"], "reply": r["reply"]} for r in rows]
            finally:
                conn.close()

    def delete_pending_reply(self, reply_id):
        with self._lock:
            conn = _conn(self.db_path)
            try:
                conn.execute(
                    "DELETE FROM pending_replies WHERE id=?", (reply_id,)
                )
                conn.commit()
            finally:
                conn.close()

    def purge_expired_pending_replies(self, older_than_iso) -> int:
        with self._lock:
            conn = _conn(self.db_path)
            try:
                cur = conn.execute(
                    "DELETE FROM pending_replies WHERE created_at < ?",
                    (older_than_iso,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    # --- helpers ---
    def _site_dict(self, row):
        if not row:
            return None
        d = dict(row)
        d["allowed_origins"] = json.loads(d.get("allowed_origins")) if d.get("allowed_origins") else None
        if d.get("widget_config"):
            d["widget_config"] = json.loads(d["widget_config"])
        return d

    def _integration_dict(self, row):
        if not row:
            return None
        d = dict(row)
        d["enabled"] = bool(d.get("enabled"))
        if d.get("config"):
            d["config"] = json.loads(d["config"])
        return d

    def _conversation_dict(self, row):
        return dict(row) if row else None
