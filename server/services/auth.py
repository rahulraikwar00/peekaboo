import secrets
from datetime import datetime, timezone

from server.config import OPERATOR_TOKEN_BYTES, get_supabase_client
from server.services.security import hash_token
from server.services.storage import get_owner_id_from_api_key
from server.state import owner_api_keys


def mint_owner_api_key(owner_id):
    api_key = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)
    key_hash = hash_token(api_key)
    db = get_supabase_client()
    if db is not None:
        db.table("owner_api_keys").insert({
            "owner_id": owner_id,
            "key_hash": key_hash,
        }).execute()
    else:
        owner_api_keys[key_hash] = {"owner_id": owner_id, "revoked": False}
    return api_key


def require_owner(request):
    api_key = request.headers.get("X-API-Key")
    owner_id = get_owner_id_from_api_key(api_key) if api_key else None
    if not owner_id:
        return None
    return owner_id


def revoke_owner_api_key(api_key):
    key_hash = hash_token(api_key)
    db = get_supabase_client()
    if db is not None:
        result = db.table("owner_api_keys").update({
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        }).eq("key_hash", key_hash).is_("revoked_at", None).execute()
        return bool(result.data)

    record = owner_api_keys.get(key_hash)
    if not record:
        return False
    record["revoked"] = True
    return True
