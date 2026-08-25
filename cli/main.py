import asyncio
import json
import os
import websockets

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".peekaboo", "config.json")
LEGACY_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), ".peekaboo", "config.json")
SERVER_URL = os.getenv("PEEKABOO_SERVER_URL", "ws://localhost:8000")


def load_config():
    config_path = CONFIG_PATH
    if not os.path.exists(config_path):
        config_path = LEGACY_CONFIG_PATH

    with open(config_path) as f:
        return json.load(f)


async def receive_messages(websocket):
    try:
        async for message in websocket:
            print(f"\n👀 {message}")
            print("> ", end="", flush=True)

    except websockets.ConnectionClosed:
        print("\n🔴 Server disconnected")


async def send_messages(websocket):
    while True:
        message = await asyncio.to_thread(input, "> ")

        if message.strip():
            await websocket.send(message)


async def main():
    print("Connecting to Peekaboo...")

    config = load_config()
    site_id = config["site_id"]
    token = config["operator_token"]

    server_url = f"{SERVER_URL}/ws/operator/{site_id}?token={token}"

    try:
        async with websockets.connect(server_url) as websocket:
            print(f"Connected to site: {site_id}")
            print("Waiting for visitors...\n")

            await asyncio.gather(
                receive_messages(websocket),
                send_messages(websocket),
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
