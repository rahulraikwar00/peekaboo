import secrets
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from server.config import (
    MAX_SITE_CREATIONS_PER_WINDOW,
    OPERATOR_TOKEN_BYTES,
    SITE_CREATION_WINDOW_SECONDS,
    SITE_ID_BYTES,
)
from server.services.auth import require_owner
from server.services.security import hash_token
from server.services.storage import insert_site, site_exists
from server.state import site_creation_attempts, visitors

router = APIRouter()


@router.get("/sites/{site_id}/status")
async def site_status(site_id: str):
    if not site_exists(site_id):
        return PlainTextResponse("Site not found", status_code=404)
    from server.state import operators

    return {"operator_online": site_id in operators}


@router.post("/sites")
async def create_site(request: Request):
    owner_id = require_owner(request)
    if not owner_id:
        return PlainTextResponse("Invalid API key", status_code=401)

    client_host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = site_creation_attempts.setdefault(client_host, deque())
    while attempts and now - attempts[0] > SITE_CREATION_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= MAX_SITE_CREATIONS_PER_WINDOW:
        return PlainTextResponse("Too many site creation requests", status_code=429)
    attempts.append(now)

    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    allowed_origin = payload.get("origin") if isinstance(payload, dict) else None
    if allowed_origin:
        parsed_origin = urlsplit(allowed_origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            return PlainTextResponse("Invalid website origin", status_code=400)
        allowed_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"

    site_id = "site_" + secrets.token_urlsafe(SITE_ID_BYTES)
    operator_token = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)
    site_record = {
        "site_id": site_id,
        "owner_id": owner_id,
        "operator_token_hash": hash_token(operator_token),
        "allowed_origin": allowed_origin,
    }
    insert_site(site_record)
    visitors[site_id] = set()

    return {
        "site_id": site_id,
        "operator_token": operator_token,
    }
