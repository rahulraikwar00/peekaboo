import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
WIDGET_ROOT = BASE_DIR / "widget"
SITE_ROOT = BASE_DIR / "site"

MAX_MESSAGE_BYTES = 4096
MAX_VISITORS_PER_SITE = 1000
MAX_MESSAGES_PER_WINDOW = 20
RATE_WINDOW_SECONDS = 10
MAX_SITE_CREATIONS_PER_WINDOW = 2
SITE_CREATION_WINDOW_SECONDS = 3600
SITE_ID_BYTES = 24
OPERATOR_TOKEN_BYTES = 48
CONVERSATION_ID_BYTES = 24

logger = logging.getLogger("peekaboo")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

supabase: Client | None = None
if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    logger.info("Supabase URL: %s", os.environ["SUPABASE_URL"])
    logger.info(
        "Supabase persistence enabled. url_host=%s",
        urlsplit(os.environ["SUPABASE_URL"]).netloc,
    )
else:
    logger.warning(
        "Supabase persistence DISABLED (SUPABASE_URL or SUPABASE_SECRET_KEY "
        "missing); running in-memory only."
    )


def public_base_url(request, server_url=None):
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    server_url = (server_url or "").strip()
    if server_url:
        return server_url.rstrip("/")
    if request is not None:
        logger.warning(
            "Neither PUBLIC_BASE_URL nor a server_url was provided; falling "
            "back to request base_url (%s). Set PUBLIC_BASE_URL to your public "
            "domain for correct OAuth redirects.",
            str(request.base_url).rstrip("/"),
        )
        return str(request.base_url).rstrip("/")
    raise RuntimeError("PUBLIC_BASE_URL or server_url is not set")


def get_supabase_client():
    main_module = sys.modules.get("server.main")
    if main_module is not None and hasattr(main_module, "supabase"):
        return main_module.supabase
    return supabase
