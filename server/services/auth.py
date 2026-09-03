import secrets

from server.config import OPERATOR_TOKEN_BYTES
from server.services.security import hash_token
from server.services.storage import (
    get_owner_id_from_api_key,
    insert_owner_api_key,
    revoke_owner_api_key as _revoke,
)


def mint_owner_api_key(owner_id, db_client=None):
    api_key = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)
    key_hash = hash_token(api_key)
    if db_client is not None:
        # Isolated service-role client path used by the OAuth callback so the
        # auth-exchange client never touches owner API keys.
        db_client.table("owner_api_keys").insert({
            "owner_id": owner_id,
            "key_hash": key_hash,
        }).execute()
    else:
        insert_owner_api_key(owner_id, key_hash)
    return api_key


def require_owner(request):
    api_key = request.headers.get("X-API-Key")
    owner_id = get_owner_id_from_api_key(api_key) if api_key else None
    if not owner_id:
        return None
    return owner_id


def revoke_owner_api_key(api_key):
    key_hash = hash_token(api_key)
    return _revoke(key_hash)
