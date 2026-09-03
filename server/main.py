from server.app import create_app
from server.config import (
    CONVERSATION_ID_BYTES,
    MAX_MESSAGE_BYTES,
    MAX_MESSAGES_PER_WINDOW,
    MAX_SITE_CREATIONS_PER_WINDOW,
    MAX_VISITORS_PER_SITE,
    OPERATOR_TOKEN_BYTES,
    RATE_WINDOW_SECONDS,
    SITE_CREATION_WINDOW_SECONDS,
    SITE_ID_BYTES,
    SITE_ROOT,
    WIDGET_ROOT,
    logger,
    public_base_url as _public_base_url,
    supabase,
)
from server.routes.websockets import valid_origin
from server.services.auth import mint_owner_api_key, require_owner
from server.services.security import hash_token
from server.services.storage import get_owner_id_from_api_key, save_message, site_exists
from server.state import (
    conversations,
    integrations,
    owner_api_keys,
    pending_oauth,
    pending_replies,
    site_creation_attempts,
    site_stats,
    sites,
    telegram_updates,
    visitor_info,
    visitors,
)

app = create_app()
