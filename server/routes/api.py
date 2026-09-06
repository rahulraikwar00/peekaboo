"""JSON API for the owner dashboard SPA.

Session-cookie authentication (peekaboo_session), unlike the legacy
X-API-Key routes. All responses are JSON so the React frontend can call
them directly.
"""

import json
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.config import INTEGRATION_ID_BYTES, SITE_ID_BYTES, public_base_url
from server.integrations import router as adapter_router
from server.services import storage
from server.services.crypto import encrypt_credentials
from server.services.session import clear_session_cookie, owner_from_request

router = APIRouter()

PROVIDER_LABELS = {
    "telegram": {"token": "Bot token", "destination": "Chat ID"},
    "discord": {"token": "Bot token", "destination": "Channel ID"},
    "slack": {"token": "Bot token", "destination": "Channel ID"},
}


def _require_owner(request: Request) -> str | None:
    return owner_from_request(request)


def _owns_site(owner_id: str, site_id: str) -> bool:
    site = storage.get_site(site_id)
    return bool(site and site.get("owner_id") == owner_id)


def _err(message: str, status: int):
    return JSONResponse({"error": message}, status_code=status)


def _visible_integration(record: dict) -> dict:
    return {
        "integration_id": record["integration_id"],
        "provider": record.get("provider"),
        "destination_id": record.get("destination_id"),
        "credentials_stored": bool(record.get("credentials")),
        "enabled": bool(record.get("enabled", True)),
    }


@router.get("/api/auth/providers")
async def auth_providers(request: Request):
    import os

    providers = []
    if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
        providers.append("google")
    if os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"):
        providers.append("github")
    return {"providers": providers}


@router.post("/api/auth/login")
async def auth_login_json(request: Request):
    """API-key login for the SPA. Sets the session cookie on success."""
    from server.services.session import make_session_cookie

    try:
        payload = await request.json()
    except ValueError:
        return _err("Invalid JSON body", 400)
    payload = payload if isinstance(payload, dict) else {}
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        return _err("API key is required", 400)
    owner_id = storage.get_owner_id_from_api_key(api_key)
    if not owner_id:
        return _err("Invalid API key", 401)
    return JSONResponse(
        {"ok": True, "owner_id": owner_id},
        headers={"Set-Cookie": make_session_cookie(owner_id)},
    )


@router.get("/api/me")
async def get_me(request: Request):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    return {"owner_id": owner_id}


@router.post("/api/auth/logout")
async def logout(request: Request):
    return JSONResponse(
        {"ok": True},
        headers={"Set-Cookie": clear_session_cookie()},
    )


@router.get("/api/sites")
async def list_sites(request: Request):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    sites = storage.list_sites(owner_id)
    return {"sites": sites}


@router.post("/api/sites")
async def create_site(request: Request):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}

    origins = payload.get("origins") or []
    if not isinstance(origins, list):
        origins = []
    site_id = "site_" + secrets.token_urlsafe(SITE_ID_BYTES)
    storage.insert_site({
        "site_id": site_id,
        "owner_id": owner_id,
        "allowed_origins": origins or None,
        "widget_config": None,
    })
    from server.state import visitors
    visitors[site_id] = set()
    return {"site_id": site_id}


@router.get("/api/sites/{site_id}")
async def get_site(request: Request, site_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    site = storage.get_site(site_id)
    return {
        "site_id": site["site_id"],
        "allowed_origins": site.get("allowed_origins"),
        "widget_config": site.get("widget_config"),
        "created_at": site.get("created_at"),
        "stats": storage.get_site_stats(site_id),
        "widget_fragment": (f'<script src="{public_base_url(request)}/widget/pboo.bundle.js" '
                            f'data-site="{site_id}"></script>'),
    }


@router.get("/api/sites/{site_id}/stats")
async def get_stats(request: Request, site_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    return {"stats": storage.get_site_stats(site_id)}


@router.get("/api/sites/{site_id}/integrations")
async def list_integrations(request: Request, site_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    return {
        "integrations": [
            _visible_integration(r) for r in storage.list_integrations(site_id)
        ]
    }


@router.post("/api/sites/{site_id}/integrations")
async def add_integration(request: Request, site_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    try:
        payload = await request.json()
    except ValueError:
        return _err("Invalid JSON body", 400)
    payload = payload if isinstance(payload, dict) else {}

    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in adapter_router.ADAPTERS:
        return _err("Unsupported provider", 400)
    if provider not in {"telegram", "discord", "slack"}:
        return _err("Unsupported provider", 400)

    integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
    base = public_base_url(request)

    if provider == "telegram":
        token = str(payload.get("token") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        if not token or not chat_id:
            return _err("Bot token and chat ID are required", 400)
        if not base.startswith("https://"):
            from server.integrations.telegram import webhook_error_hint

            return _err(webhook_error_hint("webhook URL must use HTTPS"), 400)
        webhook_secret = secrets.token_urlsafe(32)
        record = {
            "integration_id": integration_id,
            "site_id": site_id,
            "provider": provider,
            "destination_id": chat_id,
            "credentials": encrypt_credentials(token),
            "webhook_secret": webhook_secret,
            "enabled": True,
        }
        adapter = adapter_router.build_adapter(record)
        if adapter is None or not await adapter.set_webhook(
            f"{base}/v1/telegram/webhook", webhook_secret
        ):
            from server.integrations.telegram import webhook_error_hint

            detail = webhook_error_hint(
                getattr(adapter, "last_error", None) if adapter is not None else None
            )
            return _err(f"Telegram webhook setup failed. {detail}", 400)
        storage.insert_integration(record)
        return {
            "integration_id": integration_id,
            "provider": "telegram",
            "destination_id": chat_id,
            "enabled": True,
            "webhook_url": f"{base}/v1/telegram/webhook",
            "webhook_secret": webhook_secret,
            "instructions": (
                "Telegram webhook registered. Send a test message to the bot to verify."
            ),
        }

    if provider == "discord":
        bot_token = str(payload.get("token") or "").strip()
        channel_id = str(payload.get("channel_id") or "").strip()
        public_key = str(payload.get("public_key") or "").strip()
        if not bot_token or not channel_id or not public_key:
            return _err("Bot token, channel ID, and public key are required", 400)
        creds = encrypt_credentials(json.dumps({
            "bot_token": bot_token,
            "public_key": public_key,
        }))
        storage.insert_integration({
            "integration_id": integration_id,
            "site_id": site_id,
            "provider": "discord",
            "destination_id": channel_id,
            "credentials": creds,
            "webhook_secret": "",
            "enabled": True,
        })
        return {
            "integration_id": integration_id,
            "provider": "discord",
            "destination_id": channel_id,
            "enabled": True,
            "webhook_url": f"{base}/v1/discord/webhook",
            "instructions": (
                "Channel added. Set your bot's Interactions Endpoint URL to "
                f"{base}/v1/discord/webhook in the Discord developer portal."
            ),
        }

    # slack
    bot_token = str(payload.get("token") or "").strip()
    signing_secret = str(payload.get("signing_secret") or "").strip()
    channel_id = str(payload.get("channel_id") or "").strip()
    if not bot_token or not signing_secret or not channel_id:
        return _err("Bot token, signing secret, and channel ID are required", 400)
    creds = encrypt_credentials(json.dumps({
        "bot_token": bot_token,
        "signing_secret": signing_secret,
        "channel_id": channel_id,
    }))
    storage.insert_integration({
        "integration_id": integration_id,
        "site_id": site_id,
        "provider": "slack",
        "destination_id": channel_id,
        "credentials": creds,
        "webhook_secret": "",
        "enabled": True,
    })
    return {
        "integration_id": integration_id,
        "provider": "slack",
        "destination_id": channel_id,
        "enabled": True,
        "webhook_url": f"{base}/v1/slack/webhook",
        "instructions": (
            "Channel added. Set your Slack app's Event Subscriptions Request URL "
            f"to {base}/v1/slack/webhook."
        ),
    }


@router.post("/api/sites/{site_id}/integrations/{integration_id}/enabled")
async def toggle_integration(request: Request, site_id: str, integration_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    try:
        payload = await request.json()
    except ValueError:
        return _err("Invalid JSON body", 400)
    enabled = bool(payload.get("enabled")) if isinstance(payload, dict) else False
    updated = storage.update_integration(site_id, integration_id, {"enabled": enabled})
    if not updated:
        return _err("Integration not found", 404)
    return {"integration_id": integration_id, "enabled": enabled}


@router.delete("/api/sites/{site_id}/integrations/{integration_id}")
async def remove_integration(request: Request, site_id: str, integration_id: str):
    owner_id = _require_owner(request)
    if not owner_id:
        return _err("Not signed in", 401)
    if not _owns_site(owner_id, site_id):
        return _err("Site not found", 404)
    if not storage.delete_integration(site_id, integration_id):
        return _err("Integration not found", 404)
    return {"ok": True}