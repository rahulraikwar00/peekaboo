import secrets
from datetime import datetime, timezone

from server.config import CONVERSATION_ID_BYTES
from server.services.base_storage import Storage
from server.state import conversations, integrations, owner_api_keys, pending_replies, sites, site_stats


def _now():
    return datetime.now(timezone.utc).isoformat()


class MemoryStorage(Storage):
    """In-memory backend used for tests and local mode without external storage.
    Reads/writes the shared `server.state` dicts so existing test tooling keeps working."""

    # --- owner api keys ---
    def owner_id_from_api_key(self, key_hash):
        record = owner_api_keys.get(key_hash)
        if record and not record.get("revoked"):
            return record["owner_id"]
        return None

    def insert_owner_api_key(self, owner_id, key_hash):
        owner_api_keys[key_hash] = {"owner_id": owner_id, "revoked": False}

    def revoke_owner_api_key(self, key_hash) -> bool:
        record = owner_api_keys.get(key_hash)
        if not record:
            return False
        record["revoked"] = True
        return True

    # --- sites ---
    def site_exists(self, site_id) -> bool:
        return site_id in sites

    def get_site(self, site_id):
        return sites.get(site_id)

    def insert_site(self, site_record):
        sites[site_record["site_id"]] = dict(site_record)

    def list_sites(self, owner_id):
        return [s for s in sites.values() if s.get("owner_id") == owner_id]

    def sites_for_owner(self, owner_id):
        return self.list_sites(owner_id)

    def increment_messages_received(self, site_id):
        stat = site_stats.setdefault(site_id, {})
        stat["messages_received"] = stat.get("messages_received", 0) + 1
        stat["last_message_at"] = _now()

    def increment_replies_sent(self, site_id):
        stat = site_stats.setdefault(site_id, {})
        stat["replies_sent"] = stat.get("replies_sent", 0) + 1

    def stats(self, site_id):
        return site_stats.get(site_id, {
            "messages_received": 0, "replies_sent": 0, "last_message_at": None,
        })

    # --- integrations ---
    def list_integrations(self, site_id):
        return list(integrations.get(site_id, {}).values())

    def get_integration(self, site_id, integration_id):
        return integrations.get(site_id, {}).get(integration_id)

    def find_integration_by_webhook_secret(self, secret):
        for site_bucket in integrations.values():
            for record in site_bucket.values():
                if record.get("webhook_secret") == secret:
                    return record
        return None

    def insert_integration(self, record) -> str:
        integration_id = "itg_" + secrets.token_urlsafe(16)
        integrations.setdefault(record["site_id"], {})[integration_id] = dict(record)
        return integration_id

    def delete_integration(self, site_id, integration_id) -> bool:
        bucket = integrations.get(site_id, {})
        if integration_id in bucket:
            del bucket[integration_id]
            return True
        return False

    # --- conversations ---
    def get_conversation(self, conversation_id):
        return conversations.get(conversation_id)

    def get_conversation_by_thread(self, site_id, thread_id):
        for conv in conversations.values():
            if conv.get("site_id") == site_id and conv.get("telegram_thread_id") == thread_id:
                return conv
        return None

    def get_or_create_conversation(self, site_id, visitor_id):
        for conv in conversations.values():
            if (
                conv.get("site_id") == site_id
                and conv.get("visitor_id") == visitor_id
            ):
                conv["last_activity_at"] = _now()
                return conv
        conversation_id = "conv_" + secrets.token_urlsafe(CONVERSATION_ID_BYTES)
        conv = {
            "conversation_id": conversation_id,
            "site_id": site_id,
            "visitor_id": visitor_id,
            "telegram_thread_id": None,
            "created_at": _now(),
            "last_activity_at": _now(),
        }
        conversations[conversation_id] = conv
        return conv

    def update_conversation_thread(self, conversation_id, thread_id):
        conv = conversations.get(conversation_id)
        if conv:
            conv["telegram_thread_id"] = thread_id

    def create_conversation(self, conversation_id, site_id, visitor_id=None):
        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "site_id": site_id,
            "visitor_id": visitor_id,
            "telegram_thread_id": None,
            "created_at": _now(),
            "last_activity_at": _now(),
        }
        return conversation_id

    # --- pending replies ---
    def enqueue_reply(self, conversation_id, reply):
        pending_replies.setdefault(conversation_id, []).append(
            {"id": _seq(), "reply": reply, "conversation_id": conversation_id}
        )

    def pending_replies(self, conversation_id):
        return list(pending_replies.get(conversation_id, []))

    def delete_pending_reply(self, reply_id):
        for conv_id, replies in list(pending_replies.items()):
            pending_replies[conv_id] = [
                r for r in replies if r["id"] != reply_id
            ]

    def purge_expired_pending_replies(self, older_than_iso) -> int:
        count = 0
        for conv_id in list(pending_replies.keys()):
            before = len(pending_replies[conv_id])
            pending_replies[conv_id] = [
                r for r in pending_replies[conv_id]
                if r["created_at"] >= older_than_iso
            ]
            count += before - len(pending_replies[conv_id])
        return count


_seq_counter = [0]


def _seq():
    _seq_counter[0] += 1
    return _seq_counter[0]
