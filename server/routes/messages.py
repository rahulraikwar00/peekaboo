import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from server.config import MAX_MESSAGE_BYTES
from server.integrations.router import deliver_to_site
from server.services import storage
from server.services.domain import origin_allowed
from server.services.ratelimit import (
    MSG_PER_IP,
    MSG_PER_SITE,
    MSG_PER_VISITOR,
    MSG_IP_WINDOW,
    MSG_SITE_WINDOW,
    MSG_VISITOR_WINDOW,
)
from server.services.signing import sign_visitor_token
from server.state import limiter

router = APIRouter()

# Limits enforced before reading the body (JSONResponse to avoid parsing huge bodies).
MAX_BODY_BYTES = 8192


class MessageIn(BaseModel):
    site_id: str = Field(min_length=1, max_length=128)
    visitor_id: str = Field(default="", max_length=128)
    visitor_name: str = Field(default="", max_length=200)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_BYTES)
    page: str = Field(default="", max_length=2048)
    referrer: str = Field(default="", max_length=2048)
    # Honeypot: a real human never fills this hidden field; bots do.
    website: str = Field(default="", max_length=200)


@router.post("/v1/messages")
async def receive_message(request: Request):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        return PlainTextResponse("Payload too large", status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return PlainTextResponse("Payload too large", status_code=413)

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return PlainTextResponse("Invalid JSON", status_code=400)

    try:
        payload = MessageIn(**data)
    except ValidationError:
        return PlainTextResponse("Invalid message", status_code=400)

    # Honeypot
    if payload.website:
        return JSONResponse({"ok": True}, status_code=200)

    site = storage.get_site(payload.site_id)
    if not site:
        return PlainTextResponse("Unknown site", status_code=404)

    # Origin verification (convenience boundary, not sole security)
    origin = request.headers.get("origin")
    allowed = site.get("allowed_origins") or (
        [site["allowed_origin"]] if site.get("allowed_origin") else None
    )
    if not origin_allowed(origin, allowed):
        return PlainTextResponse("Origin not allowed", status_code=403)

    client_ip = request.client.host if request.client else "unknown"
    visitor_key = payload.visitor_id or client_ip
    if not limiter.allow(f"ip:{client_ip}", MSG_PER_IP, MSG_IP_WINDOW):
        return PlainTextResponse("Rate limited", status_code=429)
    if not limiter.allow(
        f"site:{payload.site_id}", MSG_PER_SITE, MSG_SITE_WINDOW
    ):
        return PlainTextResponse("Rate limited", status_code=429)
    if not limiter.allow(
        f"visitor:{payload.site_id}:{visitor_key}",
        MSG_PER_VISITOR,
        MSG_VISITOR_WINDOW,
    ):
        return PlainTextResponse("Rate limited", status_code=429)

    event = {
        "event": "message.created",
        "site_id": payload.site_id,
        "message": payload.message,
        "visitor_name": payload.visitor_name,
        "visitor_id": visitor_key,
        "page": payload.page,
        "referrer": payload.referrer,
    }

    result = await deliver_to_site(payload.site_id, event, visitor_key)
    storage.increment_messages_received(payload.site_id)

    # Never echo message content back; only status.
    if result["delivered"] == 0 and result["failed"] > 0:
        return JSONResponse({"ok": False, "error": "delivery_failed"}, status_code=502)
    visitor_token = sign_visitor_token(payload.site_id, visitor_key)
    return JSONResponse({
        "ok": True,
        "visitor_token": visitor_token,
        "subscribe_path": f"/ws/visitor/{payload.site_id}",
    })


@router.get("/v1/widget/config/{site_id}")
async def widget_config(site_id: str):
    site = storage.get_site(site_id)
    if not site:
        return PlainTextResponse("Unknown site", status_code=404)
    cfg = site.get("widget_config") or {}
    # Whitelist only non-secret, public widget settings.
    allowed_keys = {"title", "subtitle", "color", "placeholder", "branding", "greeting"}
    safe = {k: cfg[k] for k in allowed_keys if k in cfg}
    safe["site_id"] = site_id
    return JSONResponse(safe)
