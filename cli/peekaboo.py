import asyncio
import json
import os
import sys
import urllib.request

from cli.init import ensure_api_key, load_config, save_config
from cli.init import main as setup
from cli.main import main as listen

SERVER_URL = os.getenv("PEEKABOO_SERVER_URL", "http://localhost:8000")


def logout():
    config = load_config()
    api_key = config.get("owner_api_key")
    if api_key:
        try:
            request = urllib.request.Request(
                f"{SERVER_URL}/auth/logout",
                method="POST",
                headers={"X-API-Key": api_key},
            )
            urllib.request.urlopen(request)
        except Exception:
            pass
        config.pop("owner_api_key", None)
        save_config(config)
        print("Logged out. Account key revoked.")
    else:
        print("No account key found. Nothing to do.")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "help"

    if command == "setup":
        setup()
    elif command == "listen":
        asyncio.run(listen())
    elif command == "logout":
        logout()
    else:
        print("Peekaboo commands:")
        print("  peekaboo setup   Create a site and print the embed code")
        print("  peekaboo listen  Connect to the site as its operator")
        print("  peekaboo logout  Revoke the account API key")


if __name__ == "__main__":
    main()
