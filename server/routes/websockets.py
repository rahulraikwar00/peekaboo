import hmac
import json
import secrets
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.config import (
    CONVERSATION_ID_BYTES,
    MAX_MESSAGE_BYTES,
    MAX_MESSAGES_PER_WINDOW,
    MAX_VISITORS_PER_SITE,
    RATE_WINDOW_SECONDS,
)
from server.services.security import hash_token
from server.services.storage import (
    create_conversation,
    get_site,
    save_message,
    site_exists,
    update_conversation_visitor,
)
from server.state import operators, visitor_info, visitors

print("server.state 🔥🔥🔥🔥🔥🔥", operators, visitor_info, visitors)

router = APIRouter()


def valid_origin(websocket, site_id):
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    site = get_site(site_id)
    site_origin = site.get("allowed_origin") if site else None
    print("💡💡💡💡💡💡", origin, site_origin)
    return bool(site_origin and origin == site_origin)


async def broadcast_owner_status(site_id: str, online: bool):
    status_payload = json.dumps({
        "type": "owner.status",
        "online": online,
    })
    stale = set()
    for visitor in visitors.get(site_id, set()):
        try:
            await visitor.send_text(status_payload)
        except Exception:
            stale.add(visitor)
    for visitor in stale:
        visitors[site_id].discard(visitor)
        visitor_info.pop(visitor, None)


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

    conversation_id = secrets.token_urlsafe(CONVERSATION_ID_BYTES)
    visitors[site_id].add(websocket)
    visitor_info[websocket] = {
        "conversation_id": conversation_id,
        "visitor_id": None,
        "messages": deque(),
    }
    create_conversation(conversation_id, site_id)

    print(f"Visitor connected to {site_id}")
    operator = operators.get(site_id)

    if operator:
        await operator.send_text(json.dumps({
            "type": "visitor.connected",
            "conversation_id": conversation_id,
            "site_id": site_id,
        }))
        await broadcast_owner_status(site_id, online=True)

    try:
        while True:
            message = await websocket.receive_text()
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                event = None
            if isinstance(event, dict) and event.get("type") == "visitor.connected":
                visitor_id = event.get("visitor_id")
                visitor_info[websocket]["visitor_id"] = visitor_id
                update_conversation_visitor(conversation_id, visitor_id)
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
            save_message(conversation_id, "visitor", message)

            print(f"Visitor [{site_id}]: {message!r}")
            operator = operators.get(site_id)

            if operator:
                await operator.send_text(json.dumps({
                    "type": "visitor.message",
                    "conversation_id": conversation_id,
                    "message": message,
                }))

    except WebSocketDisconnect:
        print(f"Visitor disconnected from {site_id}")

    finally:
        visitors[site_id].discard(websocket)
        visitor_info.pop(websocket, None)


@router.websocket("/ws/operator/{site_id}")
async def operator_socket(websocket: WebSocket, site_id: str, token: str):
    site = get_site(site_id)
    if not site:
        await websocket.close(code=1008)
        return

    expected_token_hash = site["operator_token_hash"]
    if not hmac.compare_digest(hash_token(token), expected_token_hash):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    operators[site_id] = websocket

    print(f"Operator connected to {site_id}")
    await broadcast_owner_status(site_id, online=True)

    try:
        while True:
            message = await websocket.receive_text()
            if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
                continue

            if not message.startswith("/reply "):
                continue
            parts = message.split(" ", 2)
            if len(parts) != 3:
                continue
            _, conversation_id, reply = parts
            recipients = [
                visitor for visitor in visitors.get(site_id, set())
                if visitor_info.get(visitor, {}).get("conversation_id")
                == conversation_id
            ]

            print(f"Operator [{site_id}]: {reply!r}")
            save_message(conversation_id, "operator", reply)

            for visitor in recipients:
                try:
                    await visitor.send_text(json.dumps({
                        "type": "owner.message",
                        "message": reply,
                    }))
                except Exception:
                    visitors[site_id].discard(visitor)
                    visitor_info.pop(visitor, None)

    except WebSocketDisconnect:
        print(f"Operator disconnected from {site_id}")

    finally:
        if operators.get(site_id) == websocket:
            del operators[site_id]
            await broadcast_owner_status(site_id, online=False)
