# site_id -> site information
sites = {}

# key_hash -> {"owner_id": str, "revoked": bool} for in-memory mode
owner_api_keys = {}

# site_id -> connected visitors
visitors = {}

# site_id -> connected operator
operators = {}

# websocket -> visitor metadata
visitor_info = {}

# state -> OAuth login data
pending_oauth = {}

# client host -> site creation timestamps
site_creation_attempts = {}

# conversation_id -> conversation (metadata only, no message bodies)
conversations = {}

# site_id -> {integration_id -> record}
integrations = {}

# conversation_id -> [pending replies not yet delivered]
pending_replies = {}

# site_id -> privacy-safe counters
site_stats = {}

# per-key sliding-window rate limiter (in-process)
from server.services.ratelimit import SlidingWindowLimiter  # noqa: E402
limiter = SlidingWindowLimiter()
