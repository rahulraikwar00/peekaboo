import json
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.config import (
    MAX_MESSAGE_BYTES,
    MAX_MESSAGES_PER_WINDOW,
    MAX_VISITORS_PER_SITE,
    RATE_WINDOW_SECONDS,
)
from server.services.domain import origin_allowed
from server.services.signing import verify_visitor_token
from server.services.storage import (
    delete_pending_reply,
    get_or_create_conversation,
    get_site,
    pending_replies,
    site_exists,
)
from server.state import visitor_info, visitors

router = APIRouter()


def valid_origin(websocket, site_id):
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    site = get_site(site_id)
    allowed = (site.get("allowed_origins") if site else None) or (
        [site["allowed_origin"]] if site and site.get("allowed_origin") else None
    )
    return origin_allowed(origin, allowed)


@router.websocket("/ws/visitor/{site_id}")
async def visitor_socket(websocket: WebSocket, site_id: str):
    if not site_exists(site_id):
        await websocket.close(code=1008)
        return
    if not valid_origin(websocket, site_id):
        await websocket.close(code=1008)
        return

    visitors.setdefault(site_id, set())
    if len(visitors[site_id]) >= MAX_VISITORS_PER_SITE:
        await websocket.close(code=1013)
        return

    await websocket.accept()

    visitors.setdefault(site_id, set())
    visitors[site_id].add(websocket)
    visitor_info[websocket] = {
        "conversation_id": None,
        "visitor_id": None,
        "messages": deque(),
    }

    print(f"Visitor connected to {site_id}")

    try:
        while True:
            message = await websocket.receive_text()
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                event = None
            if isinstance(event, dict) and event.get("type") == "visitor.connected":
                # Resolve the visitor from its signed token, never from a raw id
                # field. A visitor can only subscribe to their own conversation.
                visitor_id = verify_visitor_token(
                    site_id, event.get("visitor_token") or ""
                )
                if visitor_id is None:
                    await websocket.close(code=1008)
                    return
                visitor_info[websocket]["visitor_id"] = visitor_id
                conv = get_or_create_conversation(site_id, visitor_id, None)
                visitor_info[websocket]["conversation_id"] = conv["conversation_id"]
                # Deliver any replies the visitor missed while offline.
                for pr in pending_replies(conv["conversation_id"]):
                    await websocket.send_text(json.dumps({
                        "type": "owner.message",
                        "message": pr["reply"],
                        "pending": True,
                    }))
                    delete_pending_reply(pr["id"])
                continue
            if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009)
                return

            now = time.monotonic()
            timestamps = visitor_info[websocket]["messages"]
            while timestamps and now - timestamps[0] > RATE_WINDOW_SECONDS:
                timestamps.popleft()
            if len(timestamps) >= MAX_MESSAGES_PER_WINDOW:
                await websocket.close(code=1008)
                return
            timestamps.append(now)

            # Visitor messages are sent over POST /v1/messages, not here. Any other
            # frame is ignored.
            print(f"Visitor [{site_id}]: non-connected frame ignored")

    except WebSocketDisconnect:
        print(f"Visitor disconnected from {site_id}")

    finally:
        visitors[site_id].discard(websocket)
        visitor_info.pop(websocket, None)