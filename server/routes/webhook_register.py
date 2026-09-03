import os
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from server.config import INTEGRATION_ID_BYTES
from server.integrations.telegram import TelegramAdapter
from server.services.auth import require_owner
from server.services.crypto import encrypt_credentials
from server.services.storage import get_site, insert_integration

router = APIRouter()


@router.post("/sites/{site_id}/webhook/register")
async def register_webhook(site_id: str, request: Request):
    owner_id = require_owner(request)
    if not owner_id:
        return PlainTextResponse("Invalid API key", status_code=401)

    site = get_site(site_id)
    if not site:
        return PlainTextResponse("Site not found", status_code=404)
    if site.get("owner_id") != owner_id:
        return PlainTextResponse("Site not owned by this owner", status_code=403)

    try:
        payload = await request.json()
    except ValueError:
        return PlainTextResponse("Invalid JSON body", status_code=400)
    payload = payload if isinstance(payload, dict) else {}

    token = str(payload.get("token") or "").strip()
    chat_id = str(payload.get("chat_id") or "").strip()
    if not token or not chat_id:
        return PlainTextResponse("token and chat_id are required", status_code=400)

    public_base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not public_base:
        return PlainTextResponse(
            "PUBLIC_BASE_URL is not configured on the server", status_code=500
        )

    integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
    webhook_secret = secrets.token_urlsafe(32)

    record = {
        "integration_id": integration_id,
        "site_id": site_id,
        "provider": "telegram",
        "destination_id": chat_id,
        "credentials": encrypt_credentials(token),
        "webhook_secret": webhook_secret,
        "enabled": True,
    }
    insert_integration(record)

    adapter = TelegramAdapter(record)
    configured = await adapter.set_webhook(
        f"{public_base}/v1/telegram/webhook", webhook_secret
    )
    if not configured:
        # Roll back the stored integration so a failed setup doesn't linger.
        from server.services.storage import delete_integration

        delete_integration(site_id, integration_id)
        return PlainTextResponse(
            "Could not register the Telegram webhook. Check the bot token "
            "and add the bot to a topics-enabled group chat.",
            status_code=502,
        )

    return {
        "integration_id": integration_id,
        "webhook_url": f"{public_base}/v1/telegram/webhook",
        "configured": True,
    }