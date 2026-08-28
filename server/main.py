from pathlib import Path
from collections import deque
import hashlib
import hmac
import json
import logging
import os
import shlex
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import secrets
from supabase import Client, create_client
from supabase_auth.helpers import generate_pkce_verifier, generate_pkce_challenge

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
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
echo "Installing Peekaboo CLI..."
mkdir -p "$install_dir"
mkdir -p "$app_dir/cli"

if [ ! -x "$app_dir/venv/bin/python" ]; then
    echo "Creating local environment..."
    python3 -m venv "$app_dir/venv"
fi
if ! "$app_dir/venv/bin/python" -c 'import websockets' >/dev/null 2>&1; then
    echo "Installing dependencies..."
    "$app_dir/venv/bin/python" -m pip install --disable-pip-version-check --quiet websockets
fi

echo "Downloading CLI files..."
base_url="https://raw.githubusercontent.com/rahulraikwar00/peekaboo/master/cli"
curl -fsSL "$base_url/init.py" -o "$app_dir/cli/init.py" &
pid_one=$!
curl -fsSL "$base_url/main.py" -o "$app_dir/cli/main.py" &
pid_two=$!
curl -fsSL "$base_url/peekaboo.py" -o "$app_dir/cli/peekaboo.py" &
pid_three=$!
wait "$pid_one" "$pid_two" "$pid_three"
echo "CLI ready."

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
    *) echo "Add it to PATH with: export PATH=\$HOME/.local/bin:\$PATH" ;;
esac
'''

# site_id -> site information
sites = {}

# key_hash -> {"owner_id": str, "revoked": bool} for in-memory (non-supabase) mode
owner_api_keys = {}

# site_id -> connected visitors
visitors = {}

# site_id -> connected operator
operators = {}
visitor_info = {}

# state -> {"api_key": str} for pending OAuth logins
pending_oauth = {}

MAX_MESSAGE_BYTES = 4096
MAX_VISITORS_PER_SITE = 1000
MAX_MESSAGES_PER_WINDOW = 20
RATE_WINDOW_SECONDS = 10
MAX_SITE_CREATIONS_PER_WINDOW = 2
SITE_CREATION_WINDOW_SECONDS = 3600
SITE_ID_BYTES = 24
OPERATOR_TOKEN_BYTES = 48
CONVERSATION_ID_BYTES = 24
site_creation_attempts = {}
logger = logging.getLogger("peekaboo")
supabase: Client | None = None
if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    secret = os.environ["SUPABASE_SECRET_KEY"]
    prefix = secret.split(".")[0]
    logger.info(
        "Supabase persistence enabled. url_host=%s key_prefix=%s",
        urlsplit(os.environ["SUPABASE_URL"]).netloc,
        prefix[:20],
    )
else:
    logger.warning(
        "Supabase persistence DISABLED (SUPABASE_URL or SUPABASE_SECRET_KEY "
        "missing); running in-memory only."
    )

def _public_base_url(request):
    base_url = os.getenv("PUBLIC_BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    if request is not None:
        logger.warning(
            "PUBLIC_BASE_URL is not set; falling back to request base_url "
            "(%s). Set PUBLIC_BASE_URL to your public domain for correct "
            "OAuth redirects.",
            str(request.base_url).rstrip("/"),
        )
        return str(request.base_url).rstrip("/")
    raise RuntimeError("PUBLIC_BASE_URL is not set")


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_owner_api_key(owner_id):
    api_key = secrets.token_urlsafe(OPERATOR_TOKEN_BYTES)
    key_hash = hash_token(api_key)
    if supabase is not None:
        supabase.table("owner_api_keys").insert({
            "owner_id": owner_id,
            "key_hash": key_hash,
        }).execute()
    else:
        owner_api_keys[key_hash] = {"owner_id": owner_id, "revoked": False}
    return api_key


def get_owner_id_from_api_key(api_key):
    if not api_key:
        return None
    key_hash = hash_token(api_key)
    if supabase is not None:
        result = supabase.table("owner_api_keys").select(
            "owner_id"
        ).eq("key_hash", key_hash).eq(
            "revoked_at", None
        ).limit(1).execute()
        if result.data:
            return result.data[0]["owner_id"]
        return None
    record = owner_api_keys.get(key_hash)
    if record and not record.get("revoked"):
        return record["owner_id"]
    return None


def require_owner(request):
    api_key = request.headers.get("X-API-Key")
    owner_id = get_owner_id_from_api_key(api_key) if api_key else None
    if not owner_id:
        return None
    return owner_id


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
        return bool(site_origin and origin == site_origin)
    if site_id not in sites or not sites[site_id].get("allowed_origin"):
        return False
    return origin == sites[site_id]["allowed_origin"]


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


@app.get("/oauth/consent", response_class=HTMLResponse)
async def oauth_consent_page(request: Request):
    base_url = _public_base_url(request)
    provider = request.query_params.get("provider", "")
    state = request.query_params.get("state", "")
    redirect_to = request.query_params.get("redirect_to", "")

    start_url = f"{base_url}/auth/oauth/start?provider={provider or 'github'}"
    if state:
        start_url += f"&state={state}"
    if redirect_to:
        start_url += f"&redirect_to={redirect_to}"

    provider_label = {"google": "Google", "github": "GitHub"}.get(provider, "your account")
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Authorize · Peekaboo</title>
    <style>
      body {{ font-family: system-ui, -apple-system, sans-serif; background:#f5f6f8; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }}
      .card {{ background:#fff; padding:40px; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,.08); width:360px; text-align:center; }}
      .logo {{ width:56px; height:56px; margin:0 auto 16px; border-radius:14px; background:#f0f4f8; display:flex; align-items:center; justify-content:center; font-size:28px; }}
      h1 {{ margin:0 0 8px; font-size:22px; }}
      p {{ color:#4b5563; margin:0 0 24px; line-height:1.5; }}
      .btn {{ display:block; padding:12px; border-radius:8px; color:#fff; text-decoration:none; font-weight:600; }}
      .btn.primary {{ background:#111827; }}
      .btn span.provider {{ color:#34d399; }}
      .hint {{ color:#9ca3af; font-size:12px; margin-top:12px; }}
    </style>
  </head>
  <body>
    <div class="card">
      <div class="logo">🐰</div>
      <h1>Peekaboo</h1>
      <p>Continue to authorize with <b>{provider_label}</b> to connect your chat account.</p>
      <a class="btn primary" href="{start_url}">Continue with <span class="provider">{provider_label}</span></a>
      <div class="hint">This is a secure authorization step. You'll return here when done.</div>
    </div>
  </body>
</html>"""


@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page():
    base_url = os.getenv("PUBLIC_BASE_URL", "")
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Log in to Peekaboo</title>
    <style>
      body {{ font-family: system-ui, -apple-system, sans-serif; background:#f5f6f8; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }}
      .card {{ background:#fff; padding:40px; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,.08); width:320px; text-align:center; }}
      h1 {{ margin:0 0 6px; font-size:24px; }}
      p {{ color:#666; margin:0 0 24px; }}
      a.btn {{ display:block; margin:10px 0; padding:12px; border-radius:8px; color:#fff; text-decoration:none; font-weight:600; }}
      a.google {{ background:#4285F4; }}
      a.github {{ background:#fff; color:#333; border:1px solid #ddd; }}
      .alt {{ margin-top:8px; font-size:12px; color:#999; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Peekaboo</h1>
      <p>Log in to continue in your terminal.</p>
      <a class="btn google" href="{base_url}/auth/oauth/start?provider=google">Continue with Google</a>
      <div class="alt">Prefer GitHub?</div>
      <a class="btn github" href="{base_url}/auth/oauth/start?provider=github">Continue with GitHub</a>
    </div>
  </body>
</html>"""


@app.get("/auth/oauth/start")
async def oauth_start(request: Request, provider: str):
    if supabase is None:
        return PlainTextResponse("Server not configured", status_code=500)
    if provider not in {"google", "github"}:
        return PlainTextResponse("Unsupported provider", status_code=400)

    state = request.query_params.get("state") or secrets.token_urlsafe(24)
    existing = pending_oauth.get(state)
    if existing and "code_verifier" in existing:
        code_verifier = existing["code_verifier"]
    else:
        code_verifier = generate_pkce_verifier()
        pending_oauth[state] = {
            "api_key": None,
            "code_verifier": code_verifier,
        }
    code_challenge = generate_pkce_challenge(code_verifier)

    base_url = _public_base_url(request)
    redirect_to = base_url + f"/auth/oauth/callback?state={state}"

    from urllib.parse import urlencode
    auth_url = (
        f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/authorize"
        + "?" + urlencode({
            "provider": provider,
            "redirect_to": redirect_to,
            "code_challenge": code_challenge,
            "code_challenge_method": "s256",
        })
    )
    return {"url": auth_url, "state": state}


@app.get("/auth/oauth/callback")
async def oauth_callback(request: Request):
    if supabase is None:
        return PlainTextResponse("Server not configured", status_code=500)
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("Missing authorization code", status_code=400)
    entry = pending_oauth.get(state or "")
    if not entry:
        return PlainTextResponse("Unknown or expired login attempt", status_code=400)
    if "code_verifier" not in entry:
        return PlainTextResponse("Code verifier missing", status_code=400)
    code_verifier = entry["code_verifier"]

    base_url = _public_base_url(request)
    redirect_to = base_url + f"/auth/oauth/callback?state={state}"
    try:
        session = supabase.auth.exchange_code_for_session({
            "auth_code": code,
            "code_verifier": code_verifier,
            "redirect_to": redirect_to,
        })
        owner_id = session.user.id
    except Exception as exc:
        logger.exception("OAuth token exchange failed")
        return PlainTextResponse(f"OAuth callback error: {exc}", status_code=400)

    try:
        api_key = mint_owner_api_key(owner_id)
    except Exception as exc:
        logger.exception("Failed to mint owner API key for owner_id=%r", owner_id)
        return PlainTextResponse(
            f"Login failed: could not save account ({exc})", status_code=500)

    if state and state in pending_oauth:
        pending_oauth[state]["api_key"] = api_key

    return RedirectResponse(
        url=f"/auth/success",
        status_code=303,
    )


@app.get("/auth/success", response_class=HTMLResponse)
async def auth_success_page():
    return """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Logged in · Peekaboo</title>
    <style>
      body { font-family: system-ui, -apple-system, sans-serif; background:#f0f4f8; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
      .card { background:#fff; padding:48px 40px; border-radius:16px; box-shadow:0 12px 32px rgba(0,0,0,.08); width:360px; text-align:center; }
      .check { width:64px; height:64px; margin:0 auto 20px; border-radius:50%; background:#d1fae5; color:#059669; display:flex; align-items:center; justify-content:center; font-size:32px; }
      h1 { margin:0 0 8px; font-size:22px; color:#111827; }
      p { color:#4b5563; font-size:15px; line-height:1.5; margin:0 0 8px; }
      .cli { margin-top:20px; padding:12px 16px; background:#111827; color:#34d399; border-radius:8px; font-family:ui-monospace,monospace; font-size:13px; }
      .hint { color:#9ca3af; font-size:12px; margin-top:16px; }
    </style>
  </head>
  <body>
    <div class="card">
      <div class="check">&#10003;</div>
      <h1>You're logged in!</h1>
      <p>Your login was successful.</p>
      <div class="cli">Go back to your terminal — Peekaboo is ready 🐰</div>
      <div class="hint">You can close this tab now.</div>
    </div>
  </body>
</html>"""


@app.get("/auth/cli/status")
async def auth_cli_status(request: Request):
    state = request.query_params.get("state")
    if not state or state not in pending_oauth:
        return PlainTextResponse("Invalid state", status_code=404)
    api_key = pending_oauth[state].get("api_key")
    if api_key:
        del pending_oauth[state]
        return {"owner_api_key": api_key}
    return {"pending": True}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return PlainTextResponse("Missing API key", status_code=401)
    key_hash = hash_token(api_key)
    if supabase is not None:
        result = supabase.table("owner_api_keys").update({
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        }).eq("key_hash", key_hash).eq("revoked_at", None).execute()
        if not result.data:
            return PlainTextResponse("API key not found", status_code=404)
    else:
        record = owner_api_keys.get(key_hash)
        if not record:
            return PlainTextResponse("API key not found", status_code=404)
        record["revoked"] = True
    return {"status": "revoked"}


@app.post("/sites")
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
        "owner_id": owner_id,
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
