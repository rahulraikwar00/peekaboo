import secrets

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from server.config import INTEGRATION_ID_BYTES
from server.services.auth import require_owner
from server.services.crypto import encrypt_credentials
from server.services.storage import (
    delete_integration,
    get_site,
    insert_integration,
    list_integrations,
)

router = APIRouter()

ALLOWED_PROVIDERS = {"telegram"}


def _assert_owns_site(request: Request, site_id: str):
    owner_id = require_owner(request)
    if not owner_id:
        raise PermissionError("Invalid API key")
    site = get_site(site_id)
    if not site:
        raise LookupError("Site not found")
    if site.get("owner_id") != owner_id:
        raise PermissionError("Site not owned by this owner")
    return owner_id


@router.get("/sites/{site_id}/integrations")
async def list_site_integrations(site_id: str, request: Request):
    try:
        _assert_owns_site(request, site_id)
    except PermissionError as exc:
        return PlainTextResponse(str(exc), status_code=401)
    except LookupError as exc:
        return PlainTextResponse(str(exc), status_code=404)

    out = []
    for record in list_integrations(site_id):
        out.append({
            "integration_id": record["integration_id"],
            "provider": record["provider"],
            "destination_id": record.get("destination_id"),
            "credentials_stored": bool(record.get("credentials")),
            "enabled": bool(record.get("enabled", True)),
        })
    return {"integrations": out}


@router.post("/sites/{site_id}/integrations")
async def create_site_integration(site_id: str, request: Request):
    try:
        _assert_owns_site(request, site_id)
    except PermissionError as exc:
        return PlainTextResponse(str(exc), status_code=401)
    except LookupError as exc:
        return PlainTextResponse(str(exc), status_code=404)

    try:
        payload = await request.json()
    except ValueError:
        return PlainTextResponse("Invalid JSON body", status_code=400)
    payload = payload if isinstance(payload, dict) else {}

    provider = payload.get("provider")
    if provider not in ALLOWED_PROVIDERS:
        return PlainTextResponse("Unsupported provider", status_code=400)

    token = str(payload.get("token") or "").strip()
    chat_id = str(payload.get("chat_id") or "").strip()
    if not token or not chat_id:
        return PlainTextResponse(
            "token and chat_id are required", status_code=400
        )

    integration_id = "int_" + secrets.token_urlsafe(INTEGRATION_ID_BYTES)
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
    insert_integration(record)

    return {
        "integration_id": integration_id,
        "webhook_secret": webhook_secret,
        "message": "Register this path in Telegram: "
        "POST /v1/telegram/webhook with the X-Telegram-Bot-Api-Secret-Token "
        "header set to the webhook_secret.",
    }


@router.delete("/sites/{site_id}/integrations/{integration_id}")
async def delete_site_integration(site_id: str, integration_id: str, request: Request):
    try:
        _assert_owns_site(request, site_id)
    except PermissionError as exc:
        return PlainTextResponse(str(exc), status_code=401)
    except LookupError as exc:
        return PlainTextResponse(str(exc), status_code=404)

    deleted = delete_integration(site_id, integration_id)
    if not deleted:
        return PlainTextResponse("Integration not found", status_code=404)
    return PlainTextResponse("ok")