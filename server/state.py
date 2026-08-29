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
