from server.config import get_supabase_client
from server.services.security import hash_token
from server.state import owner_api_keys, sites


def get_owner_id_from_api_key(api_key):
    if not api_key:
        return None
    key_hash = hash_token(api_key)
    db = get_supabase_client()
    if db is not None:
        result = db.table("owner_api_keys").select(
            "owner_id"
        ).eq("key_hash", key_hash).is_(
            "revoked_at", None
        ).limit(1).execute()
        if result.data:
            return result.data[0]["owner_id"]
        return None
    record = owner_api_keys.get(key_hash)
    if record and not record.get("revoked"):
        return record["owner_id"]
    return None


def site_exists(site_id):
    db = get_supabase_client()
    if db is None:
        return site_id in sites
    result = db.table("sites").select("site_id").eq(
        "site_id", site_id
    ).limit(1).execute()
    return bool(result.data)


def get_site(site_id):
    db = get_supabase_client()
    if db is None:
        return sites.get(site_id)
    result = db.table("sites").select("*").eq(
        "site_id", site_id
    ).limit(1).execute()
    return result.data[0] if result.data else None


def insert_site(site_record):
    db = get_supabase_client()
    if db is not None:
        db.table("sites").insert(site_record).execute()
    else:
        sites[site_record["site_id"]] = site_record


def save_message(conversation_id, sender, message):
    db = get_supabase_client()
    if db is not None:
        db.table("messages").insert({
            "conversation_id": conversation_id,
            "sender": sender,
            "message": message,
        }).execute()


def create_conversation(conversation_id, site_id):
    db = get_supabase_client()
    if db is not None:
        db.table("conversations").insert({
            "conversation_id": conversation_id,
            "site_id": site_id,
        }).execute()


def update_conversation_visitor(conversation_id, visitor_id):
    db = get_supabase_client()
    if db is not None:
        db.table("conversations").update({
            "visitor_id": visitor_id,
        }).eq("conversation_id", conversation_id).execute()
