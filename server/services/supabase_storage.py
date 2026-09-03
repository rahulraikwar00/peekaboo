import json
import secrets

from server.services.base_storage import Storage


class SupabaseStorage(Storage):
    """Storage backend backed by Supabase (Postgres) via the service-role client."""

    def __init__(self, client):
        self.db = client

    # --- owner api keys ---
    def owner_id_from_api_key(self, key_hash):
        result = (
            self.db.table("owner_api_keys")
            .select("owner_id")
            .eq("key_hash", key_hash)
            .is_("revoked_at", None)
            .limit(1)
            .execute()
        )
        return result.data[0]["owner_id"] if result.data else None

    def insert_owner_api_key(self, owner_id, key_hash):
        self.db.table("owner_api_keys").insert(
            {"owner_id": owner_id, "key_hash": key_hash}
        ).execute()

    def revoke_owner_api_key(self, key_hash) -> bool:
        from datetime import datetime, timezone

        result = (
            self.db.table("owner_api_keys")
            .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
            .eq("key_hash", key_hash)
            .is_("revoked_at", None)
            .execute()
        )
        return bool(result.data)

    # --- sites ---
    def site_exists(self, site_id) -> bool:
        result = (
            self.db.table("sites").select("site_id").eq("site_id", site_id).limit(1).execute()
        )
        return bool(result.data)

    def get_site(self, site_id):
        result = (
            self.db.table("sites").select("*").eq("site_id", site_id).limit(1).execute()
        )
        return result.data[0] if result.data else None

    def insert_site(self, site_record):
        self.db.table("sites").insert(site_record).execute()

    def list_sites(self, owner_id):
        result = (
            self.db.table("sites").select("*").eq("owner_id", owner_id).execute()
        )
        return result.data or []

    def sites_for_owner(self, owner_id):
        return self.list_sites(owner_id)

    def increment_messages_received(self, site_id):
        self.db.rpc("increment_site_messages", {"p_site_id": site_id}).execute()

    def increment_replies_sent(self, site_id):
        self.db.rpc("increment_site_replies", {"p_site_id": site_id}).execute()

    # --- integrations ---
    def list_integrations(self, site_id):
        result = (
            self.db.table("integrations").select("*").eq("site_id", site_id).execute()
        )
        return [self._normalize_integration(r) for r in (result.data or [])]

    def get_integration(self, site_id, integration_id):
        result = (
            self.db.table("integrations")
            .select("*")
            .eq("site_id", site_id)
            .eq("id", integration_id)
            .limit(1)
            .execute()
        )
        return self._normalize_integration(result.data[0]) if result.data else None

    def find_integration_by_webhook_secret(self, secret):
        result = (
            self.db.table("integrations")
            .select("*")
            .eq("webhook_secret", secret)
            .limit(1)
            .execute()
        )
        return self._normalize_integration(result.data[0]) if result.data else None

    def insert_integration(self, record) -> str:
        integration_id = record.get(
            "integration_id", "itg_" + secrets.token_urlsafe(16)
        )
        row = dict(record)
        row["id"] = integration_id
        result = self.db.table("integrations").insert(
            {k: v for k, v in row.items() if k != "integration_id"}
        ).execute()
        return integration_id

    def delete_integration(self, site_id, integration_id) -> bool:
        result = (
            self.db.table("integrations")
            .delete()
            .eq("site_id", site_id)
            .eq("id", integration_id)
            .execute()
        )
        return bool(result.data)

    @staticmethod
    def _normalize_integration(row):
        if not row:
            return None
        d = dict(row)
        if "id" in d:
            d["integration_id"] = d.pop("id")
        return d

    # --- conversations ---
    def get_conversation(self, conversation_id):
        result = (
            self.db.table("conversations")
            .select("*")
            .eq("conversation_id", conversation_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_conversation_by_thread(self, site_id, thread_id):
        result = (
            self.db.table("conversations")
            .select("*")
            .eq("site_id", site_id)
            .eq("telegram_thread_id", thread_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_or_create_conversation(self, site_id, visitor_id):
        result = (
            self.db.table("conversations")
            .select("*")
            .eq("site_id", site_id)
            .eq("visitor_id", visitor_id)
            .order("last_activity_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            conv = result.data[0]
            self.db.table("conversations").update(
                {"last_activity_at": "now()"}
            ).eq("conversation_id", conv["conversation_id"]).execute()
            return conv
        return None

    def update_conversation_thread(self, conversation_id, thread_id):
        self.db.table("conversations").update(
            {"telegram_thread_id": thread_id}
        ).eq("conversation_id", conversation_id).execute()

    def create_conversation(self, conversation_id, site_id, visitor_id):
        self.db.table("conversations").insert(
            {
                "conversation_id": conversation_id,
                "site_id": site_id,
                "visitor_id": visitor_id,
            }
        ).execute()
        return conversation_id

    # --- pending replies ---
    def enqueue_reply(self, conversation_id, reply):
        self.db.table("pending_replies").insert(
            {"conversation_id": conversation_id, "reply": reply, "created_at": "now()"}
        ).execute()

    def pending_replies(self, conversation_id):
        result = (
            self.db.table("pending_replies")
            .select("id, reply")
            .eq("conversation_id", conversation_id)
            .order("id")
            .execute()
        )
        return result.data or []

    def delete_pending_reply(self, reply_id):
        self.db.table("pending_replies").delete().eq("id", reply_id).execute()

    def purge_expired_pending_replies(self, older_than_iso) -> int:
        result = (
            self.db.table("pending_replies")
            .delete()
            .lt("created_at", older_than_iso)
            .execute()
        )
        return len(result.data or [])
