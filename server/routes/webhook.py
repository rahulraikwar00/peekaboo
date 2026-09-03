import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from server.services import storage
from server.state import visitor_info, visitors

router = APIRouter()

# Periodic GC of expired pending replies, run opportunistically on webhook calls.
PENDING_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


@router.post("/v1/telegram/webhook")
async def telegram_webhook(request: Request):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_token:
        return PlainTextResponse("Missing webhook secret", status_code=401)

    # GC expired pending replies opportunistically (privacy: purge undelivered bodies).
    _gc_pending()

    integration = storage.find_integration_by_webhook_secret(secret_token)
    if not integration:
        # Valid-looking header but nobody we issued a secret to.
        return PlainTextResponse("Unauthorized", status_code=401)
    stored_secret = integration.get("webhook_secret")
    if not stored_secret or not hmac.compare_digest(secret_token, stored_secret):
        return PlainTextResponse("Unauthorized", status_code=401)

    body = await request.body()
    if len(body) > 20000:
        return PlainTextResponse("Payload too large", status_code=413)
    try:
        update = json.loads(body)
    except json.JSONDecodeError:
        return PlainTextResponse("Bad request", status_code=400)

    # Dedup webhook retries (Telegram redelivers until you ack 'ok').
    update_id = update.get("update_id")
    if update_id is not None and storage.webhook_update_seen(update_id):
        return PlainTextResponse("ok")

    reply = _extract_reply(update)
    if reply is None:
        # e.g. non-message updates (edited, channel_post, callback) — acknowledge.
        return PlainTextResponse("ok")

    thread_id, text = reply
    site_id = integration["site_id"]
    integration_id = integration["integration_id"]
    conversation = storage.get_conversation_by_integration_thread(
        site_id, integration_id, thread_id
    )
    if not conversation:
        # Reply to a thread we don't manage — ignore to prevent routing abuse.
        return PlainTextResponse("Unknown thread", status_code=200)

    conversation_id = conversation["conversation_id"]
    delivered = await _push_to_visitor(site_id, conversation_id, text)
    if delivered:
        storage.increment_replies_sent(site_id)
    else:
        storage.enqueue_reply(conversation_id, text)
        storage.increment_replies_sent(site_id)

    return PlainTextResponse("ok")


def _extract_reply(update: dict):
    """Return (thread_id, text) for a message reply from an owner in a thread, else None."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    thread_id = message.get("message_thread_id")
    text = message.get("text")
    if thread_id is None or not text:
        return None
    return (thread_id, text)


async def _push_to_visitor(site_id: str, conversation_id: str, text: str) -> bool:
    """Deliver a reply to any live visitor socket for this conversation.

    Returns True if at least one socket was sent the message.
    """
    payload = json.dumps({"type": "owner.message", "message": text})
    sent = False
    stale = set()
    for ws in visitors.get(site_id, set()):
        info = visitor_info.get(ws, {})
        if info.get("conversation_id") != conversation_id:
            continue
        try:
            await ws.send_text(payload)
            sent = True
        except Exception:
            stale.add(ws)
    for ws in stale:
        visitors[site_id].discard(ws)
        visitor_info.pop(ws, None)
    return sent


def _gc_pending():
    from datetime import datetime, timedelta, timezone

    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=PENDING_TTL_SECONDS)
    ).isoformat()
    try:
        storage.purge_expired_pending_replies(cutoff)
    except Exception:
        pass
