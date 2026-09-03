import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from cli.connect import main as connect
from cli.init import main as setup

# Load the project .env so the CLI reads the same config as the server and no
# manual `export` is needed for PEEKABOO_SERVER_URL / Telegram credentials.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SERVER_URL = (os.getenv("PEEKABOO_SERVER_URL") or
              "https://peekaboo-477i.onrender.com").rstrip("/")


def logout():
    from cli.init import load_config, save_config

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
    elif command == "connect":
        connect()
    elif command == "logout":
        logout()
    else:
        print("Peekaboo commands:")
        print("  peekaboo setup    Create a site and print the embed code")
        print("  peekaboo connect  Connect your Telegram bot to the site")
        print("  peekaboo logout   Revoke the account API key")


if __name__ == "__main__":
    main()