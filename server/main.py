from pathlib import Path
from collections import deque
import hashlib
import hmac
import json
import os
import shlex
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import secrets
from supabase import Client, create_client

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

WIDGET_ROOT = Path(__file__).resolve().parent / "widget"
SITE_ROOT = Path(__file__).resolve().parent / "site"
app.mount(
    "/widget",
    StaticFiles(directory=WIDGET_ROOT),
    name="widget",
)
app.mount(
    "/site",
    StaticFiles(directory=SITE_ROOT),
    name="site",
)


@app.get("/install.sh", response_class=PlainTextResponse)
async def install_script(request: Request):
    server_url = shlex.quote(str(request.base_url).rstrip("/"))

    return fr'''#!/bin/sh
set -eu

command -v curl >/dev/null 2>&1 || {{ echo "curl is required" >&2; exit 1; }}
command -v python3 >/dev/null 2>&1 || {{ echo "python3 is required" >&2; exit 1; }}

install_dir="$HOME/.local/bin"
app_dir="$HOME/.peekaboo"
cat <<'PEEKABOO_BANNER'
                 _         _                 
 _ __   ___  ___| | ____ _| |__   ___   ___  
| '_ \ / _ \/ _ \ |/ / _` | '_ \ / _ \ / _ \ 
| |_) |  __/  __/   < (_| | |_) | (_) | (_) |
| .__/ \___|\___|_|\_\__,_|_.__/ \___/ \___/ 
|_|                                          
PEEKABOO_BANNER
echo "Peekaboo installer"
echo "[1/4] Preparing local directories..."
mkdir -p "$install_dir"
mkdir -p "$app_dir/cli"

echo "[2/4] Creating a private Python environment..."
python3 -m venv "$app_dir/venv"
echo "[3/4] Installing CLI dependencies..."
"$app_dir/venv/bin/python" -m pip install --disable-pip-version-check --quiet websockets

echo "[4/4] Downloading the Peekaboo CLI..."
curl -fsSL https://raw.githubusercontent.com/rahulraikwar00/peekaboo/master/cli/init.py -o "$app_dir/cli/init.py"
curl -fsSL https://raw.githubusercontent.com/rahulraikwar00/peekaboo/master/cli/main.py -o "$app_dir/cli/main.py"
curl -fsSL https://raw.githubusercontent.com/rahulraikwar00/peekaboo/master/cli/peekaboo.py -o "$app_dir/cli/peekaboo.py"

cat > "$install_dir/peekaboo" <<'PEEKABOO_COMMAND'
#!/bin/sh
set -eu
app_dir="$HOME/.peekaboo"
server_url={server_url}
case "${{1:-}}" in
    listen) server_url="wss://${{server_url#https://}}" ;;
    *) server_url="$server_url" ;;
esac
PEEKABOO_SERVER_URL="$server_url" PYTHONPATH="$app_dir" exec "$app_dir/venv/bin/python" -m cli.peekaboo "$@"
PEEKABOO_COMMAND

chmod +x "$install_dir/peekaboo"
echo "Peekaboo CLI installed at $install_dir/peekaboo"
case ":$PATH:" in
    *":$install_dir:"*) ;;
    *) echo "Add it to PATH with: export PATH=\\$HOME/.local/bin:\\$PATH" ;;
esac
'''

# site_id -> site information
sites = {}

# site_id -> connected visitors
visitors = {}

# site_id -> connected operator
operators = {}
visitor_info = {}

MAX_MESSAGE_BYTES = 4096
MAX_VISITORS_PER_SITE = 1000
MAX_MESSAGES_PER_WINDOW = 20
RATE_WINDOW_SECONDS = 10
MAX_SITE_CREATIONS_PER_WINDOW = 5
SITE_CREATION_WINDOW_SECONDS = 60
SITE_ID_BYTES = 24
OPERATOR_TOKEN_BYTES = 48
CONVERSATION_ID_BYTES = 24
allowed_origins = {
    origin.strip()
    for origin in os.getenv("PEEKABOO_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
site_creation_attempts = {}
supabase: Client | None = None
if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def valid_origin(websocket, site_id):
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    if supabase is not None:
        result = supabase.table("sites").select("allowed_origin").eq(
            "site_id", site_id
        ).limit(1).execute()
        site_origin = result.data[0].get(
            "allowed_origin") if result.data else None
        if site_origin:
            return origin == site_origin
    elif site_id in sites and sites[site_id].get("allowed_origin"):
        return origin == sites[site_id]["allowed_origin"]
    return not allowed_origins or origin in allowed_origins


def site_exists(site_id):
    if supabase is None:
        return site_id in sites
    result = supabase.table("sites").select("site_id").eq(
        "site_id", site_id
    ).limit(1).execute()
    return bool(result.data)


def save_message(conversation_id, sender, message):
    if supabase is not None:
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "sender": sender,
            "message": message,
        }).execute()


@app.get("/")
async def root():
    page = (SITE_ROOT / "index.html").read_text()
    return HTMLResponse(page)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sites/{site_id}/status")
async def site_status(site_id: str):
    if not site_exists(site_id):
        return PlainTextResponse("Site not found", status_code=404)
    return {"operator_online": site_id in operators}


@app.post("/sites")
async def create_site(request: Request):
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
    allowed_origin = payload.get(
        "origin") if isinstance(payload, dict) else None
    if allowed_origin:
        parsed_origin = urlsplit(allowed_origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            return PlainTextResponse("Invalid website origin", status_code=400)
        allowed_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"

    site_id = "site_" + secrets.token_urlsafe(SITE_ID_BYTES)
    operator_token = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)

    site_record = {
        "site_id": site_id,
        "operator_token_hash": hash_token(operator_token),
        "allowed_origin": allowed_origin,
    }
    if supabase is not None:
        supabase.table("sites").insert(site_record).execute()
    else:
        sites[site_id] = site_record

    visitors[site_id] = set()

    return {
        "site_id": site_id,
        "operator_token": operator_token
    }


@app.websocket("/ws/visitor/{site_id}")
async def visitor_socket(
    websocket: WebSocket,
    site_id: str
):
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
    if supabase is not None:
        supabase.table("conversations").insert({
            "conversation_id": conversation_id,
            "site_id": site_id,
        }).execute()

    print(f"Visitor connected to {site_id}")

    operator = operators.get(site_id)

    if operator:
        await operator.send_text(json.dumps({
            "type": "visitor.connected",
            "conversation_id": conversation_id,
            "site_id": site_id,
        }))

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
                if supabase is not None:
                    supabase.table("conversations").update({
                        "visitor_id": visitor_id,
                    }).eq("conversation_id", conversation_id).execute()
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


@app.websocket("/ws/operator/{site_id}")
async def operator_socket(
    websocket: WebSocket,
    site_id: str,
    token: str
):
    if not site_exists(site_id):
        await websocket.close(code=1008)
        return

    if supabase is not None:
        site_result = supabase.table("sites").select(
            "operator_token_hash"
        ).eq("site_id", site_id).limit(1).execute()
        expected_token_hash = site_result.data[0]["operator_token_hash"]
    else:
        expected_token_hash = sites[site_id]["operator_token_hash"]

    if not hmac.compare_digest(hash_token(token), expected_token_hash):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    operators[site_id] = websocket

    print(f"Operator connected to {site_id}")

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
