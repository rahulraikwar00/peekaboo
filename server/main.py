from pathlib import Path
import shlex
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
import secrets

app = FastAPI()

WIDGET_ROOT = Path(__file__).resolve().parent / "widget"
app.mount(
    "/widget",
    StaticFiles(directory=WIDGET_ROOT),
    name="widget",
)


@app.get("/install.sh", response_class=PlainTextResponse)
async def install_script():
    python_executable = shlex.quote(sys.executable)

    return f'''#!/bin/sh
set -eu

install_dir="$HOME/.local/bin"
mkdir -p "$install_dir"

cat > "$install_dir/peekaboo" <<'PEEKABOO_COMMAND'
#!/bin/sh
exec {python_executable} -m cli.peekaboo "$@"
PEEKABOO_COMMAND

chmod +x "$install_dir/peekaboo"
echo "Peekaboo CLI installed at $install_dir/peekaboo"
case ":$PATH:" in
    *":$install_dir:"*) ;;
    *) echo "Add it to PATH with: export PATH=\$HOME/.local/bin:\\$PATH" ;;
esac
'''

# site_id -> site information
sites = {}

# site_id -> connected visitors
visitors = {}

# site_id -> connected operator
operators = {}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sites")
async def create_site():
    site_id = "site_" + secrets.token_urlsafe(8)
    operator_token = secrets.token_urlsafe(32)

    sites[site_id] = {
        "operator_token": operator_token
    }

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
    if site_id not in sites:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    visitors.setdefault(site_id, set())
    visitors[site_id].add(websocket)

    print(f"Visitor connected to {site_id}")

    operator = operators.get(site_id)

    if operator:
        await operator.send_text(
            f"👀 New visitor on {site_id}"
        )

    try:
        while True:
            message = await websocket.receive_text()

            print(f"Visitor [{site_id}]: {message}")

            operator = operators.get(site_id)

            if operator:
                await operator.send_text(message)

    except WebSocketDisconnect:
        print(f"Visitor disconnected from {site_id}")

    finally:
        visitors[site_id].discard(websocket)


@app.websocket("/ws/operator/{site_id}")
async def operator_socket(
    websocket: WebSocket,
    site_id: str,
    token: str
):
    if site_id not in sites:
        await websocket.close(code=1008)
        return

    expected_token = sites[site_id]["operator_token"]

    if token != expected_token:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    operators[site_id] = websocket

    print(f"Operator connected to {site_id}")

    try:
        while True:
            message = await websocket.receive_text()

            print(f"Operator [{site_id}]: {message}")

            for visitor in visitors.get(site_id, set()):
                await visitor.send_text(message)

    except WebSocketDisconnect:
        print(f"Operator disconnected from {site_id}")

    finally:
        if operators.get(site_id) == websocket:
            del operators[site_id]
