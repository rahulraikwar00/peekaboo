import asyncio
import json
import os
import re
import websockets

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
LEGACY_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), ".peekaboo", "config.json")



def convert_to_ws_url(url):
    """Convert any URL format to WebSocket format"""
    url = url.rstrip("/")
    
    # Already WebSocket
    if url.startswith(("ws://", "wss://")):
        return url
    
    # Convert HTTP to WebSocket
    if url.startswith("https://"):
        return url.replace("https://", "wss://", 1)
    elif url.startswith("http://"):
        return url.replace("http://", "ws://", 1)
    
    # No scheme, assume WebSocket
    return f"ws://{url}"


SERVER_URL = convert_to_ws_url(os.getenv("PEEKABOO_SERVER_URL", "wss://peekaboo-477i.onrender.com"))


def load_config():
    config_path = CONFIG_PATH
    if not os.path.exists(config_path):
        config_path = LEGACY_CONFIG_PATH

    with open(config_path) as f:
        return json.load(f)


async def receive_messages(websocket, state):
    try:
        async for message in websocket:
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                event = {"type": "message", "message": message}

            message_text = re.sub(
                r"[\x00-\x1f\x7f-\x9f]", "", event.get("message", message))
            conversation_id = event.get("conversation_id")
            if conversation_id:
                state["conversation_id"] = conversation_id
            prefix = f"[{conversation_id}] " if conversation_id else ""
            print(f"\nVisitor {prefix}{message_text}")
            print("> ", end="", flush=True)

    except websockets.ConnectionClosed:
        print("\n🔴 Server disconnected")


async def send_messages(websocket, state):
    while True:
        message = await asyncio.to_thread(input, "> ")

        if message.strip():
            if message.startswith("/reply "):
                await websocket.send(message)
                continue
            conversation_id = state.get("conversation_id")
            if not conversation_id:
                print("No visitor conversation is active yet.")
                continue
            await websocket.send(f"/reply {conversation_id} {message}")


async def main():
    print("Connecting to Peekaboo...")

    config = load_config()
    site_id = config["site_id"]
    token = config["operator_token"]

    server_url = f"{SERVER_URL}/ws/operator/{site_id}?token={token}"

    try:
        async with websockets.connect(server_url) as websocket:
            state = {}
            print(f"Connected to site: {site_id}")
            print("Waiting for visitors...\n")

            await asyncio.gather(
                receive_messages(websocket, state),
                send_messages(websocket, state),
            )

    except FileNotFoundError:
        print("❌ No site configured. Run `peekaboo setup` first.")
    except ConnectionRefusedError:
        print("❌ Could not connect to Peekaboo server.")
    except websockets.exceptions.InvalidStatus as error:
        if error.response.status_code == 403:
            print(
                "❌ Site rejected. The server may have restarted, or the "
                "site/token is invalid. Run `peekaboo setup` again."
            )
        else:
            print(
                f"❌ WebSocket connection rejected: {error.response.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
